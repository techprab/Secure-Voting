from datetime import date, timedelta

import bcrypt
import pyotp
from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    verify_jwt_in_request,
)

from .. import db
from ..models import Staff
from ..security.staff_guard import require_staff, audited

bp = Blueprint("staff", __name__, url_prefix="/staff")


@bp.post("/login")
def staff_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="unauthorized"), 401

    staff = Staff.query.filter_by(username=username).first()

    if staff is None:
        return jsonify(error="unauthorized"), 401

    try:
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"),
            staff.password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError, AttributeError):
        password_matches = False

    if not password_matches:
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
@require_staff("admin")
@audited("recertify")
def recertify(staff_id):
    staff = db.session.get(Staff, staff_id)

    if staff is None:
        return jsonify(error="staff_not_found"), 404

    # Prevent an administrator from renewing their own recertification.
    if staff_id == g.staff.id:
        return jsonify(error="self_recertification_not_allowed"), 403

    previous_date = staff.recertified_until
    staff.recertified_until = date.today() + timedelta(days=90)
    g.audit_before = {
        "staff_id": staff.id,
        "recertified_until": (
            previous_date.isoformat() if previous_date else None
        ),
    }
    g.audit_after = {
        "staff_id": staff.id,
        "recertified_until": staff.recertified_until.isoformat(),
    }

    db.session.commit()

    return jsonify(
        staff_id=staff.id,
        recertified_until=staff.recertified_until.isoformat(),
    ), 200
