
from flask import Blueprint, jsonify

from ..security.staff_guard import require_staff
from ..services.audit_log import verify_audit_log_details

bp = Blueprint("audit_log", __name__, url_prefix="/audit/log")


@bp.get("/verify")
@require_staff("auditor")
def verify_log():
    return jsonify(verify_audit_log_details()), 200
