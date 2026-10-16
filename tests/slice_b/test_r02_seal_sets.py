"""R-02  Ballots leave the pending buffer only in sets of 20 or more.
Source: Jaewook SR-02 · Slice B · Issue #3
"""
from datetime import datetime, timedelta

from app import db
from app import models
from app.security.crypto import chain_hash, verify_chain
from app.services.ballots import flush_pending, force_seal_after_close, sealed_ballots

DIV = "TEST-DIV"
GENESIS = "0" * 64


def _add_pending(n, division=DIV):
    rows = [models.PendingBallot(division=division, blob=f"ballot-{i:02d}".encode()) for i in range(n)]
    db.session.add_all(rows)
    db.session.commit()
    return [r.blob for r in rows]


def _sealed(division=DIV):
    return (db.session.query(models.Ballot).filter_by(division=division)
            .order_by(models.Ballot.id).all())


def _pending(division=DIV):
    return db.session.query(models.PendingBallot).filter_by(division=division).count()


def test_r02_ballot_table_has_no_voter_or_time_column():
    columns = {c.name for c in models.Ballot.__table__.columns}
    assert columns == {"id", "division", "blob", "prev_hash", "hash", "batch_id"}
    assert not models.Ballot.__table__.foreign_keys


def test_r02_19_ballots_none_sealed(app):
    _add_pending(19)
    assert flush_pending(DIV) == 0
    assert len(_sealed()) == 0
    assert _pending() == 19


def test_r02_20th_ballot_seals_20(app):
    _add_pending(20)
    assert flush_pending(DIV) == 20
    rows = _sealed()
    assert len(rows) == 20
    assert _pending() == 0
    assert len({b.batch_id for b in rows}) == 1


def test_r02_sealed_order_differs_from_submission_order(app):
    submitted = _add_pending(20)
    flush_pending(DIV)
    sealed = [b.blob for b in _sealed()]
    assert sorted(sealed) == sorted(submitted)
    # Chance of a false failure: 1 in 20! (about 4e-19)
    assert sealed != submitted


def test_r02_sealed_rows_continue_the_hash_chain(app):
    _add_pending(20, division="OTHER-DIV")
    flush_pending("OTHER-DIV")
    tip = _sealed("OTHER-DIV")[-1].hash

    _add_pending(20)
    flush_pending(DIV)
    rows = _sealed()
    assert rows[0].prev_hash == tip
    for earlier, later in zip(rows, rows[1:]):
        assert later.prev_hash == earlier.hash
    for row in rows:
        assert row.hash == chain_hash(row.prev_hash, row.blob)
    assert verify_chain() is True


def test_r02_first_set_starts_from_genesis(app):
    _add_pending(20)
    flush_pending(DIV)
    assert _sealed()[0].prev_hash == GENESIS


def test_r02_force_seals_fewer_than_20(app):
    _add_pending(5)
    assert flush_pending(DIV, force=True) == 5
    assert len(_sealed()) == 5
    assert _pending() == 0


def test_r02_force_seal_waits_60_minutes_after_close(app):
    _add_pending(5)
    close = datetime.fromisoformat(app.config["WINDOW_CLOSE"])
    assert force_seal_after_close(now=close + timedelta(minutes=59)) == 0
    assert _pending() == 5
    assert force_seal_after_close(now=close + timedelta(minutes=60)) == 5
    assert _pending() == 0


def test_r02_counting_sees_only_sealed_ballots(app):
    _add_pending(19)
    flush_pending(DIV)
    assert sealed_ballots(DIV) == []


def test_r02_submit_buffers_until_the_20th_vote(division, cast, counts):
    candidates = division["candidates"]
    for voter_id in division["voters"][:19]:
        assert cast(voter_id, candidates).status_code == 201
    assert counts() == {"pending": 19, "sealed": 0, "participation": 19}

    assert cast(division["voters"][19], candidates).status_code == 201
    assert counts() == {"pending": 0, "sealed": 20, "participation": 20}
