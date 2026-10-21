"""Count & publish routes. Owner: Prabh (Slice E).

R-12  POST /count/recount/<division>        officer + MFA, recomputes from sealed ballots

Privileged routes stack the decorators as require_staff -> _commit_on_success -> audited,
so the state change and its audit entry are committed in one transaction, or neither is.
"""
from functools import wraps

from flask import Blueprint, g, jsonify, make_response

from .. import db
from ..security.crypto import verify_chain
from ..security.staff_guard import audited, require_staff
from ..services.count import UnknownDivision, count_a, write_display_cache

bp = Blueprint("count", __name__)


def _commit_on_success(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            response = make_response(fn(*args, **kwargs))
        except Exception:
            db.session.rollback()
            raise
        if response.status_code < 400:
            db.session.commit()
        else:
            db.session.rollback()
        return response
    return wrapper


# --------------------------------------------------------------------------- R-12

@bp.post("/count/recount/<division>")
@require_staff("officer")
@_commit_on_success
@audited("recount")
def recount(division):
    # R-10 before R-12: refuse to count a ballot store whose hash chain has been altered.
    if not verify_chain():
        return jsonify(error="chain_broken"), 409
    try:
        totals = count_a(division)
    except UnknownDivision:
        return jsonify(error="unknown_division"), 404
    except ValueError:
        return jsonify(error="ballot_integrity"), 409

    write_display_cache(division, totals)
    g.audit_after = {"division": division, "totals": {str(k): v for k, v in totals.items()}}
    return jsonify(division=division, totals={str(k): v for k, v in totals.items()}), 200


@bp.post("/exclusions")
def exclusions():
    return jsonify(error="not_implemented"), 501  # STUB until R-21


@bp.get("/results/<path:result_path>")
def results(result_path):
    return jsonify(error="not_implemented"), 501  # STUB until R-22
