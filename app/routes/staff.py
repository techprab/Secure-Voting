from datetime import date, timedelta

from flask import Blueprint, g, jsonify
from .. import db
from ..models import Staff
from ..security.staff_guard import require_staff, audited
bp = Blueprint("staff", __name__, url_prefix="/staff")

@bp.post("/login")
def staff_login():
    return jsonify(error="not_implemented"), 501

@bp.post("/mfa")
def staff_mfa():
    return jsonify(error="not_implemented"), 501

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
