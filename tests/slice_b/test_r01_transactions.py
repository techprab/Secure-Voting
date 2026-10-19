import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Participation, UsedNonce
from app.routes import ballot as ballot_routes


def test_r01_second_vote_with_fresh_nonce_rejected(
    division, cast, counts
):
    voter = division["voters"][0]
    first = cast(voter, division["candidates"])
    assert first.status_code == 201
    before = counts()
    fresh_nonce = str(uuid.uuid4())

    second = cast(
        voter, division["candidates"], body={"nonce": fresh_nonce}
    )
    assert second.status_code == 409
    assert second.get_json() == {"error": "already_voted"}
    assert counts() == before
    assert db.session.get(UsedNonce, fresh_nonce) is None


def test_r01_database_enforces_one_participation(division, cast):
    voter = division["voters"][0]
    assert cast(voter, division["candidates"]).status_code == 201

    db.session.add(Participation(
        voter_id=voter,
        code=uuid.uuid4().hex,
        voted_hour="2026-10-19 10",
    ))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()

    assert Participation.query.filter_by(voter_id=voter).count() == 1


def test_r01_failed_submission_rolls_back_and_can_retry(
    division, cast, counts, monkeypatch
):
    voter = division["voters"][0]
    nonce = str(uuid.uuid4())
    before = counts()

    def broken_encryption(_preferences):
        raise RuntimeError("simulated encryption failure")

    with monkeypatch.context() as patch:
        patch.setattr(ballot_routes, "seal_ballot", broken_encryption)
        with pytest.raises(RuntimeError, match="simulated encryption failure"):
            cast(voter, division["candidates"], body={"nonce": nonce})

    # No manual rollback here: the route must have cleaned up.
    assert counts() == before
    assert db.session.get(UsedNonce, nonce) is None

    retry = cast(voter, division["candidates"], body={"nonce": nonce})
    assert retry.status_code == 201
    after = counts()
    assert after["participation"] == before["participation"] + 1
    assert after["pending"] + after["sealed"] == (
        before["pending"] + before["sealed"] + 1
    )
