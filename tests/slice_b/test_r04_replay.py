"""R-04 tests using the existing ballot integration fixtures."""
import logging
import uuid

import pytest

from app import db
from app.models import UsedNonce
from app.errors import ReplayError
from app.security.voter_guard import consume_nonce


def test_r04_identical_submission_rejected(
    division, client, auth, preview, counts, caplog
):
    voter = division["voters"][0]
    preferences = division["candidates"]
    response = preview(voter, preferences)
    assert response.status_code == 200

    nonce = str(uuid.uuid4())
    payload = {
        "preferences": preferences,
        "preview_token": response.get_json()["preview_token"],
        "confirm": True,
        "nonce": nonce,
    }
    first = client.post(
        "/ballot/submit", json=payload, headers=auth(voter_id=voter)
    )
    assert first.status_code == 201
    before = counts()
    assert before["pending"] + before["sealed"] == 1
    assert before["participation"] == 1

    with caplog.at_level(logging.WARNING):
        replay = client.post(
            "/ballot/submit", json=payload,
            headers=auth(voter_id=voter),
        )

    assert replay.status_code == 409
    assert replay.get_json() == {"error": "replay"}
    assert counts() == before
    assert db.session.query(UsedNonce).count() == 1
    assert "R-04: replay submission rejected" in caplog.text
    assert "X-Session-Token" not in replay.headers


def test_r04_nonce_reuse_by_another_voter_rejected(
    division, cast, counts
):
    nonce = str(uuid.uuid4())
    first = cast(
        division["voters"][0], division["candidates"],
        body={"nonce": nonce},
    )
    assert first.status_code == 201
    before = counts()

    second = cast(
        division["voters"][1], division["candidates"],
        body={"nonce": nonce},
    )
    assert second.status_code == 409
    assert second.get_json() == {"error": "replay"}
    assert counts() == before


def test_r04_distinct_nonces_allow_distinct_voters(
    division, cast, counts
):
    for voter in division["voters"][:2]:
        response = cast(
            voter, division["candidates"],
            body={"nonce": str(uuid.uuid4())},
        )
        assert response.status_code == 201
    result = counts()
    assert result["pending"] + result["sealed"] == 2
    assert result["participation"] == 2


def test_r04_database_rejects_duplicate_and_session_recovers(app):
    with app.app_context():
        nonce = str(uuid.uuid4())
        consume_nonce(nonce)
        db.session.commit()

        with pytest.raises(ReplayError):
            consume_nonce(nonce)

        assert db.session.query(UsedNonce).count() == 1
        consume_nonce(str(uuid.uuid4()))
        db.session.commit()
        assert db.session.query(UsedNonce).count() == 2


def test_r04_nonce_reservation_rolls_back_with_transaction(app):
    with app.app_context():
        nonce = str(uuid.uuid4())
        consume_nonce(nonce)
        assert db.session.get(UsedNonce, nonce) is not None

        db.session.rollback()
        assert db.session.get(UsedNonce, nonce) is None

        consume_nonce(nonce)
        db.session.commit()
        assert db.session.query(UsedNonce).count() == 1
