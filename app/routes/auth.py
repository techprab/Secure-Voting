from flask import Blueprint, jsonify
bp = Blueprint("auth", __name__, url_prefix="/auth")

@bp.post("/login")
def login():
    # STUB — Dev owns authentication implementation.
    return jsonify(error="not_implemented"), 501
