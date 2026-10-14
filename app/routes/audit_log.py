from flask import Blueprint, jsonify
bp = Blueprint("audit_log", __name__, url_prefix="/audit/log")

@bp.post("/verify")
def verify_log():
    return jsonify(error="not_implemented"), 501
