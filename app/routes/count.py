from flask import Blueprint, jsonify
bp = Blueprint("count", __name__)

@bp.post("/count/recount")
def recount():
    return jsonify(error="not_implemented"), 501

@bp.post("/exclusions")
def exclusions():
    return jsonify(error="not_implemented"), 501

@bp.get("/results/<path:result_path>")
def results(result_path):
    return jsonify(error="not_implemented"), 501
