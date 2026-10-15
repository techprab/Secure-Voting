"""Ballot routes. Owner: Jaewook (Slice B).

R-06: GET /ballot serves the candidate list only if it matches the last approved set.
/ballot/preview, /ballot/submit (R-07) and /participation/<code> are still stubs.
"""
from flask import Blueprint, abort, g, jsonify

from .. import db
from ..models import Voter
from ..security.voter_guard import require_voter
from ..services.ballot_def import check_ballot_definition, current_candidates

bp = Blueprint("ballot", __name__)


def current_voter() -> Voter:
    """Load the signed-in voter. require_voter stores the voter id in g.voter."""
    voter_id = g.voter if isinstance(g.voter, int) else g.voter.id
    voter = db.session.get(Voter, voter_id)
    if voter is None or not voter.eligible:
        abort(403)
    return voter


@bp.get("/ballot")
@require_voter
def ballot_home():
    voter = current_voter()
    check_ballot_definition(voter.division)
    candidates = [
        {"id": c.id, "name": c.name, "position": c.position}
        for c in current_candidates(voter.division)
    ]
    return jsonify(division=voter.division, candidates=candidates), 200


@bp.post("/ballot/preview")
def ballot_preview():
    return jsonify(error="not_implemented"), 501


@bp.post("/ballot/submit")
def ballot_submit():
    return jsonify(error="not_implemented"), 501


@bp.get("/participation/<code>")
def participation(code):
    return jsonify(error="not_implemented"), 501
