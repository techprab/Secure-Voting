from flask import Blueprint, jsonify
bp = Blueprint("ballot", __name__)

@bp.get("/ballot")
def ballot_home():
    return jsonify(error="not_implemented"), 501

@bp.post("/ballot/preview")
def ballot_preview():
    return jsonify(error="not_implemented"), 501

@bp.post("/ballot/submit")
def ballot_submit():
    return jsonify(error="not_implemented"), 501

@bp.get("/participation/<code>")
def participation(code):
    return jsonify(error="not_implemented"), 501
