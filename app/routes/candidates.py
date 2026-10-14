from flask import Blueprint, jsonify
bp = Blueprint("candidates", __name__, url_prefix="/staff/candidates")

@bp.post("/approve")
def approve_candidates():
    return jsonify(error="not_implemented"), 501
