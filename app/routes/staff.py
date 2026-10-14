from flask import Blueprint, jsonify
bp = Blueprint("staff", __name__, url_prefix="/staff")

@bp.post("/login")
def staff_login():
    return jsonify(error="not_implemented"), 501

@bp.post("/mfa")
def staff_mfa():
    return jsonify(error="not_implemented"), 501

@bp.post("/<int:staff_id>/recertify")
def recertify(staff_id):
    return jsonify(error="not_implemented"), 501
