from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from flask_jwt_extended import create_access_token, decode_token

from app import db
from app.models import Voter
from app.security.voter_guard import require_voter


@pytest.fixture()
def session_setup(app):
    app.config["WINDOW_CLOSE"] = "2099-01-01T00:00:00+00:00"

    @app.get("/_test/session")
    @require_voter
    def session_probe():
        return {"ok": True}, 200

    @app.get("/_test/session-error")
    @require_voter
    def session_error():
        return {"error": "test_error"}, 400

    @app.get("/_test/session-204")
    @require_voter
    def session_no_content():
        return "", 204

    @app.get("/_test/session-raise")
    @require_voter
    def session_raises():
        raise RuntimeError("simulated route failure")

    with app.app_context():
        voter = Voter(
            name="r03_voter",
            division="Test Division",
            eligible=True,
            overseas=False,
            password_hash=bcrypt.hashpw(
                b"test-password", bcrypt.gensalt(rounds=4)
            ).decode(),
        )
        db.session.add(voter)
        db.session.commit()
        return voter.id


def login(client):
    return client.post("/auth/login", json={
        "username": "r03_voter",
        "password": "test-password",
    })


def token_for(app, voter_id, kind="voter", seconds=900):
    with app.app_context():
        return create_access_token(
            identity=str(voter_id),
            additional_claims={
                "type": kind,
                "division": "Test Division",
            },
            expires_delta=timedelta(seconds=seconds),
        )


def headers(token):
    return {"Authorization": "Bearer " + token}


def test_r03_login_token_lasts_15_minutes(client, app, session_setup):
    response = login(client)
    assert response.status_code == 200
    with app.app_context():
        claims = decode_token(response.get_json()["token"])
    assert claims["sub"] == str(session_setup)
    assert claims["type"] == "voter"
    assert 899 <= claims["exp"] - claims["iat"] <= 900


def test_r03_expired_token_rejected(client, app, session_setup):
    token = token_for(app, session_setup, seconds=-1)
    response = client.get("/_test/session", headers=headers(token))
    assert response.status_code == 401
    assert "X-Session-Token" not in response.headers


@pytest.mark.parametrize("kind", ["staff", "ballot_preview"])
def test_r03_nonvoter_token_rejected(client, app, session_setup, kind):
    token = token_for(app, session_setup, kind=kind)
    response = client.get("/_test/session", headers=headers(token))
    assert response.status_code == 403


def test_r03_success_renews_and_returns_usable_token(
    client, app, session_setup
):
    old_token = token_for(app, session_setup, seconds=60)
    response = client.get("/_test/session", headers=headers(old_token))
    assert response.status_code == 200
    new_token = response.headers["X-Session-Token"]
    with app.app_context():
        old = decode_token(old_token)
        new = decode_token(new_token)
    assert new["exp"] > old["exp"]
    assert 899 <= new["exp"] - new["iat"] <= 900
    assert new["sub"] == str(session_setup)
    assert client.get(
        "/_test/session", headers=headers(new_token)
    ).status_code == 200


def test_r03_failed_request_does_not_renew(client, app, session_setup):
    token = token_for(app, session_setup)
    response = client.get("/_test/session-error", headers=headers(token))
    assert response.status_code == 400
    assert "X-Session-Token" not in response.headers


def test_r03_login_and_renewal_capped_at_close(
    client, app, session_setup
):
    close = datetime.now(timezone.utc) + timedelta(minutes=2)
    app.config["WINDOW_CLOSE"] = close.isoformat()
    response = login(client)
    assert response.status_code == 200
    token = response.get_json()["token"]
    with app.app_context():
        assert decode_token(token)["exp"] == int(close.timestamp())
    response = client.get("/_test/session", headers=headers(token))
    assert response.status_code == 200
    with app.app_context():
        renewed = decode_token(response.headers["X-Session-Token"])
    assert renewed["exp"] == int(close.timestamp())


def test_r03_closed_window_blocks_login_and_existing_token(
    client, app, session_setup
):
    token = token_for(app, session_setup)
    app.config["WINDOW_CLOSE"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    assert login(client).status_code == 401
    response = client.get("/_test/session", headers=headers(token))
    assert response.status_code == 401
    assert "X-Session-Token" not in response.headers


def test_r03_ineligible_voter_blocked(client, app, session_setup):
    token = token_for(app, session_setup)
    with app.app_context():
        db.session.get(Voter, session_setup).eligible = False
        db.session.commit()
    assert login(client).status_code == 403
    assert client.get(
        "/_test/session", headers=headers(token)
    ).status_code == 403


@pytest.mark.parametrize("deadline", [None, "invalid-date"])
def test_r03_invalid_window_fails_closed(
    client, app, session_setup, deadline
):
    token = token_for(app, session_setup)
    app.config["WINDOW_CLOSE"] = deadline
    assert login(client).status_code == 503
    assert client.get(
        "/_test/session", headers=headers(token)
    ).status_code == 503


def test_r03_no_content_success_also_renews(client, app, session_setup):
    token = token_for(app, session_setup)
    response = client.get("/_test/session-204", headers=headers(token))
    assert response.status_code == 204
    assert response.headers["X-Session-Token"]


def test_r03_route_exception_does_not_renew(client, app, session_setup):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    token = token_for(app, session_setup)
    response = client.get("/_test/session-raise", headers=headers(token))
    assert response.status_code == 500
    assert "X-Session-Token" not in response.headers
