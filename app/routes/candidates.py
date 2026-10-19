"""R-06: a delegate approves the current candidate set of a division.

Owner: Jaewook (Slice B).
"""
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from .. import db
from ..models import Candidate, CandidateSetApproval
from ..security.staff_guard import audited, require_staff
from ..services.ballot_def import candidate_set_hash, latest_approval

bp = Blueprint("candidates", __name__, url_prefix="/staff/candidates")


@bp.post("/approve")
@require_staff("delegate")
@audited("approve_candidates")
def approve_candidates():
    body = request.get_json(silent=True) or {}
    division = body.get("division")
    if not isinstance(division, str) or not division.strip():
        return jsonify(error="bad_request"), 400
    if Candidate.query.filter_by(division=division).count() == 0:
        return jsonify(error="unknown_division"), 404

    previous = latest_approval(division)
    set_hash = candidate_set_hash(division)
    g.audit_before = {"division": division, "set_hash": previous.set_hash if previous else None}
    g.audit_after = {"division": division, "set_hash": set_hash}

    db.session.add(
        CandidateSetApproval(
            division=division,
            set_hash=set_hash,
            approved_by=int(g.staff.id),
            approved_at=datetime.utcnow(),
        )
    )
    db.session.commit()
    return jsonify(division=division, set_hash=set_hash), 201
