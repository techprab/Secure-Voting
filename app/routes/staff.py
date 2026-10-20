
from datetime import timedelta
from datetime import datetime, timedelta, timezone
from flask_jwt_extended import create_access_token
import pyotp
from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)
from werkzeug.security import check_password_hash

from .. import db
from ..models import Staff

bp = Blueprint("staff", __name__, url_prefix="/staff")

@bp.post("/login")
def staff_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="unauthorized"), 401

    staff = Staff.query.filter_by(username=username).first()

    if staff is None or not check_password_hash(
        staff.password_hash, password
    ):
        return jsonify(error="unauthorized"), 401

    token = create_access_token(
        identity=str(staff.id),
        additional_claims={
            "type": "staff",
            "role": staff.role,
            "mfa": False,
        },
        expires_delta=timedelta(minutes=5),
    )

    return jsonify(access_token=token, mfa_required=True), 200



@bp.post("/mfa")
def staff_mfa():
    verify_jwt_in_request()
    claims = get_jwt()

    # Only a staff token from the password stage may proceed.
    if claims.get("type") != "staff" or claims.get("mfa") is not False:
        return jsonify(error="unauthorized"), 401

    staff = db.session.get(Staff, get_jwt_identity())
    if staff is None:
        return jsonify(error="unauthorized"), 401

    data = request.get_json(silent=True) or {}
    code = data.get("code")

    if not isinstance(code, str) or not (
        len(code) == 6 and code.isdigit()
    ):
        return jsonify(error="unauthorized"), 401

    if not pyotp.TOTP(staff.totp_secret).verify(code, valid_window=1):
        return jsonify(error="unauthorized"), 401

    token = create_access_token(
        identity=str(staff.id),
        additional_claims={
            "type": "staff",
            "role": staff.role,
            "mfa": True,
        },
        expires_delta=timedelta(minutes=15),
    )

    return jsonify(access_token=token, mfa_required=False), 200


@bp.post("/<int:staff_id>/recertify")
def recertify(staff_id):
    return jsonify(error="not_implemented"), 501

def test_r11_mfa_rejects_already_authenticated_staff_token(
    app, client, staff_token
):
    token = staff_token(role="auditor", mfa=True)

    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401

def test_r11_mfa_rejects_voter_token(app, client, voter_token):
    token = voter_token(voter_id=1)

    response = client.post(
        "/staff/mfa",
        json={"code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401

def test_r11_mfa_rejects_expired_password_stage_token(
    app, client, staff_token
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
