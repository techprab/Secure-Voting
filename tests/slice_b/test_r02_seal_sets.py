"""R-02  Ballots leave the pending buffer only in sets of 20 or more.
Source: Jaewook SR-02 · Slice B · Issue #3
"""
import secrets
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app import models
from app.security.crypto import chain_hash, verify_chain
from app.services import ballots
from app.services.ballots import commit_with_seal, flush_pending, force_seal_after_close, sealed_ballots

DIV = "TEST-DIV"
OTHER = "OTHER-DIV"
GENESIS = "0" * 64


def _add_pending(n, division=DIV, start=0):
    rows = [models.PendingBallot(division=division, blob=f"{division}-{i:02d}".encode())
            for i in range(start, start + n)]
    db.session.add_all(rows)
    db.session.commit()
    return [r.blob for r in rows]


def _sealed(division=DIV):
    return (db.session.query(models.Ballot).filter_by(division=division)
            .order_by(models.Ballot.id).all())


def _pending(division=DIV):
    return db.session.query(models.PendingBallot).filter_by(division=division).count()


class ReversingRng:
    """Stands in for SystemRandom so the sealing order is predictable in a test."""
    def shuffle(self, items):
        items.reverse()


# --- the rule: nothing below 20, everything at 20 ---------------------------------------

def test_r02_ballot_table_has_no_voter_or_time_column():
    columns = {c.name for c in models.Ballot.__table__.columns}
    assert columns == {"id", "division", "blob", "prev_hash", "hash", "batch_id"}
    assert not models.Ballot.__table__.foreign_keys


def test_r02_19_ballots_none_sealed(app):
    _add_pending(19)
    assert commit_with_seal(DIV) == 0
    assert len(_sealed()) == 0
    assert _pending() == 19


def test_r02_20th_ballot_seals_20(app):
    _add_pending(20)
    assert commit_with_seal(DIV) == 20
    rows = _sealed()
    assert len(rows) == 20
    assert _pending() == 0
    assert len({b.batch_id for b in rows}) == 1


def test_r02_counting_sees_only_sealed_ballots(app):
    _add_pending(19)
    commit_with_seal(DIV)
    assert sealed_ballots(DIV) == []


# --- shuffling (deterministic) ----------------------------------------------------------

def test_r02_sealing_order_comes_from_the_shuffle(app, monkeypatch):
    monkeypatch.setattr(ballots, "_rng", ReversingRng())
    submitted = _add_pending(20)
    commit_with_seal(DIV)
    assert [b.blob for b in _sealed()] == list(reversed(submitted))


def test_r02_shuffle_uses_a_cryptographic_rng():
    assert isinstance(ballots._rng, secrets.SystemRandom)


# --- hash chain, several divisions, repeated sealing ------------------------------------

def test_r02_first_set_starts_from_genesis(app):
    _add_pending(20)
    commit_with_seal(DIV)
    assert _sealed()[0].prev_hash == GENESIS


def test_r02_divisions_are_sealed_independently(app):
    _add_pending(20, DIV)
    _add_pending(19, OTHER)
    assert commit_with_seal(DIV) == 20
    assert commit_with_seal(OTHER) == 0
    assert len(_sealed(DIV)) == 20 and _pending(DIV) == 0
    assert len(_sealed(OTHER)) == 0 and _pending(OTHER) == 19


def test_r02_one_chain_runs_across_divisions(app):
    _add_pending(20, OTHER)
    commit_with_seal(OTHER)
    tip = _sealed(OTHER)[-1].hash

    _add_pending(20, DIV)
    commit_with_seal(DIV)
    rows = _sealed(DIV)
    assert rows[0].prev_hash == tip
    for earlier, later in zip(rows, rows[1:]):
        assert later.prev_hash == earlier.hash
    for row in rows:
        assert row.hash == chain_hash(row.prev_hash, row.blob)
    assert verify_chain() is True


def test_r02_repeated_sealing_never_seals_twice(app):
    _add_pending(20)
    assert commit_with_seal(DIV) == 20
    assert commit_with_seal(DIV) == 0
    assert len(_sealed()) == 20

    _add_pending(20, start=20)
    assert commit_with_seal(DIV) == 20
    rows = _sealed()
    assert len(rows) == 40
    assert len({b.blob for b in rows}) == 40
    assert len({b.batch_id for b in rows}) == 2
    assert verify_chain() is True


# --- force seal after the window, with time zones ---------------------------------------

def test_r02_force_seals_fewer_than_20(app):
    _add_pending(5)
    assert flush_pending(DIV, force=True) == 5
    db.session.commit()
    assert len(_sealed()) == 5
    assert _pending() == 0


@pytest.mark.parametrize("window_close, close_utc", [
    ("2099-01-01T00:00:00", datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)),         # no zone = UTC
    ("2099-01-01T00:00:00Z", datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)),
    ("2099-01-01T00:00:00+00:00", datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)),
    ("2099-01-01T11:00:00+11:00", datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc)),   # Melbourne (AEDT)
])
def test_r02_force_seal_waits_60_minutes_in_any_time_zone(app, window_close, close_utc):
    app.config["WINDOW_CLOSE"] = window_close
    _add_pending(5)
    assert force_seal_after_close(now=close_utc + timedelta(minutes=59)) == 0
    assert _pending() == 5
    assert force_seal_after_close(now=close_utc + timedelta(minutes=60)) == 5
    assert _pending() == 0


def test_r02_force_seal_accepts_naive_now_as_utc(app):
    app.config["WINDOW_CLOSE"] = "2099-01-01T11:00:00+11:00"
    _add_pending(5)
    assert force_seal_after_close(now=datetime(2099, 1, 1, 0, 59)) == 0
    assert force_seal_after_close(now=datetime(2099, 1, 1, 1, 0)) == 5


def test_r02_invalid_window_close_seals_nothing(app):
    app.config["WINDOW_CLOSE"] = "not-a-date"
    _add_pending(5)
    with pytest.raises(ValueError):
        force_seal_after_close()
    assert _pending() == 5


# --- concurrency and rollback -----------------------------------------------------------

def test_r02_sealing_waits_for_the_lock(app):
    _add_pending(20)
    result = {}

    def other_request():
        with app.app_context():
            result["sealed"] = commit_with_seal(DIV)

    with ballots._seal_lock:
        worker = threading.Thread(target=other_request)
        worker.start()
        worker.join(timeout=0.3)
        assert worker.is_alive(), "sealing must wait while another request holds the lock"
        assert len(_sealed()) == 0
        db.session.rollback()  # end this read before the other request uses the connection
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert result["sealed"] == 20
    assert len(_sealed()) == 20


def test_r02_failed_seal_rolls_back_the_vote_too(division, cast, counts, monkeypatch):
    candidates = division["candidates"]
    for voter_id in division["voters"][:19]:
        assert cast(voter_id, candidates).status_code == 201

    def broken_chain_hash(prev_hash, blob):
        raise RuntimeError("simulated failure while sealing")
    monkeypatch.setattr(ballots, "chain_hash", broken_chain_hash)

    with pytest.raises(RuntimeError):
        cast(division["voters"][19], candidates)
    assert counts() == {"pending": 19, "sealed": 0, "participation": 19}

    monkeypatch.undo()
    assert cast(division["voters"][19], candidates).status_code == 201
    assert counts() == {"pending": 0, "sealed": 20, "participation": 20}


def test_r02_submit_buffers_until_the_20th_vote(division, cast, counts):
    candidates = division["candidates"]
    for voter_id in division["voters"][:19]:
        assert cast(voter_id, candidates).status_code == 201
    assert counts() == {"pending": 19, "sealed": 0, "participation": 19}

    assert cast(division["voters"][19], candidates).status_code == 201
    assert counts() == {"pending": 0, "sealed": 20, "participation": 20}
