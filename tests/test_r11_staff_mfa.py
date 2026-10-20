from datetime import date, timedelta
import uuid

import bcrypt
import pyotp
from flask_jwt_extended import create_access_token, decode_token

from app import db, models


def create_staff():
    """Create a staff account for an authentication test."""
    password_hash = bcrypt.hashpw(
        b"CorrectPassword123!",
        bcrypt.gensalt(),
    ).decode("utf-8")

    staff = models.Staff(
        username=f"auditor-{uuid.uuid4().hex[:8]}",
        role="auditor",
        password_hash=password_hash,
        totp_secret="JBSWY3DPEHPK3PXP",
        recertified_until=date.today() + timedelta(days=30),
    )
    db.session.add(staff)
    db.session.commit()
    return staff


def test_r11_staff_login_success(app, client):
    with app.app_context():
        staff = create_staff()
        staff_id = staff.id
        username = staff.username

    response = client.post(
        "/staff/login",
        json={"username": username, "password": "CorrectPassword123!"},
    )

    assert response.status_code == 200
    assert response.get_json()["mfa_required"] is True

    with app.app_context():
        claims = decode_token(response.get_json()["access_token"])
        assert claims["sub"] == str(staff_id)
        assert claims["type"] == "staff"
        assert claims["role"] == "auditor"
        assert claims["mfa"] is False


def test_r11_staff_login_wrong_password(app, client):
    with app.app_context():
        staff = create_staff()
        username = staff.username

    response = client.post(
        "/staff/login",
        json={"username": username, "password": "WrongPassword!"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_r11_staff_login_unknown_username(client):
    response = client.post(
        "/staff/login",
        json={
            "username": "missing-user",
            "password": "CorrectPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_r11_staff_login_token_expires_in_five_minutes(app, client):
    with app.app_context():
        staff = create_staff()
        username = staff.username

    response = client.post(
        "/staff/login",
        json={"username": username, "password": "CorrectPassword123!"},
    )

    assert response.status_code == 200

    with app.app_context():
        claims = decode_token(response.get_json()["access_token"])
        lifetime_seconds = claims["exp"] - claims["iat"]

    assert lifetime_seconds == 300


def test_r11_valid_totp_issues_mfa_token(app, client):
    with app.app_context():
        staff = create_staff()
        staff_id = staff.id
        username = staff.username
        secret = staff.totp_secret

    login = client.post(
        "/staff/login",
        json={"username": username, "password": "CorrectPassword123!"},
    )
    assert login.status_code == 200

    code = pyotp.TOTP(secret).now()

    response = client.post(
        "/staff/mfa",
        json={"code": code},
        headers={
            "Authorization": f"Bearer {login.get_json()['access_token']}"
        },
    )

    assert response.status_code == 200
    assert response.get_json()["mfa_required"] is False

    with app.app_context():
        claims = decode_token(response.get_json()["access_token"])
        assert claims["sub"] == str(staff_id)
        assert claims["type"] == "staff"
        assert claims["role"] == "auditor"
        assert claims["mfa"] is True


def test_r11_invalid_totp_is_rejected(app, client):
    with app.app_context():
        staff = create_staff()
        username = staff.username

    login = client.post(
        "/staff/login",
        json={"username": username, "password": "CorrectPassword123!"},
    )
    assert login.status_code == 200

    response = client.post(
        "/staff/mfa",
        json={"code": "000000"},
        headers={
            "Authorization": f"Bearer {login.get_json()['access_token']}"
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_r11_mfa_rejects_missing_token(client):
    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
    )

    assert response.status_code == 401


def test_r11_mfa_rejects_already_authenticated_staff_token(
    app, client, staff_token
):
    with app.app_context():
        staff = create_staff()
        token = staff_token(
            role="auditor",
            mfa=True,
            staff_id=staff.id,
        )

    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_r11_mfa_rejects_voter_token(client, voter_token):
    token = voter_token(voter_id=1)

    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_r11_mfa_rejects_expired_password_stage_token(
    app, client
):
    with app.app_context():
        token = create_access_token(
            identity="1",
            additional_claims={
                "type": "staff",
                "role": "auditor",
                "mfa": False,
            },
            expires_delta=timedelta(seconds=-1),
        )

    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
