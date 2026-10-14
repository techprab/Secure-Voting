from flask import Blueprint, jsonify
bp = Blueprint("audit_ballots", __name__, url_prefix="/audit/ballots")

@bp.post("/verify")
def verify_ballots():
    return jsonify(error="not_implemented"), 501
