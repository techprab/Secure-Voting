"""Count & publish routes. Owner: Prabh (Slice E).

R-12  POST /count/recount/<division>        officer + MFA, recomputes from sealed ballots
R-21  POST /exclusions                      delegate, first approval of a court-ordered exclusion
      POST /exclusions/<id>/approve         a *different* delegate, within 15 minutes

Privileged routes stack the decorators as require_staff -> _commit_on_success -> audited,
so the state change and its audit entry are committed in one transaction, or neither is.
"""
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, make_response, request

from .. import db
from ..models import Candidate, ExclusionRequest
from ..security.crypto import verify_chain
from ..security.staff_guard import audited, require_staff
from ..services.count import UnknownDivision, count_a, write_display_cache

bp = Blueprint("count", __name__)

EXCLUSION_WINDOW = timedelta(minutes=15)


def _now() -> datetime:
    """Naive UTC, matching how the models store DateTime. Tests monkeypatch this."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


# --------------------------------------------------------------------------- R-21

@bp.post("/exclusions")
@require_staff("delegate")
@_commit_on_success
@audited("exclusion_request")
def request_exclusion():
    body = request.get_json(silent=True) or {}
    candidate_id = body.get("candidate_id")
    court_ref = body.get("court_ref")
    if type(candidate_id) is not int or not isinstance(court_ref, str) \
            or not court_ref.strip() or len(court_ref) > 120:
        return jsonify(error="bad_request"), 400

    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        return jsonify(error="unknown_candidate"), 404
    if candidate.excluded:
        return jsonify(error="already_excluded"), 409

    req = ExclusionRequest(
        candidate_id=candidate.id,
        court_ref=court_ref.strip(),
        approver_1=int(g.staff.id),
        created_at=_now(),
        applied=False,
    )
    db.session.add(req)
    db.session.flush()

    g.audit_after = {"request_id": req.id, "candidate_id": candidate.id,
                     "court_ref": req.court_ref, "status": "pending"}
    return jsonify(id=req.id, status="pending",
                   expires_at=(req.created_at + EXCLUSION_WINDOW).isoformat() + "Z"), 201


@bp.post("/exclusions/<int:request_id>/approve")
@require_staff("delegate")
@_commit_on_success
@audited("exclusion_approve")
def approve_exclusion(request_id):
    req = db.session.get(ExclusionRequest, request_id)
    if req is None:
        return jsonify(error="not_found"), 404
    if req.applied:
        return jsonify(error="already_applied"), 409
    if int(g.staff.id) == req.approver_1:
        return jsonify(error="second_delegate_required"), 403
    if _now() - req.created_at > EXCLUSION_WINDOW:
        return jsonify(error="expired"), 409

    candidate = db.session.get(Candidate, req.candidate_id)
    if candidate is None:
        return jsonify(error="unknown_candidate"), 404

    g.audit_before = {"request_id": req.id, "candidate_id": candidate.id, "excluded": candidate.excluded}
    req.approver_2 = int(g.staff.id)
    req.applied = True
    candidate.excluded = True
    g.audit_after = {"request_id": req.id, "candidate_id": candidate.id, "excluded": True,
                     "approver_1": req.approver_1, "approver_2": req.approver_2}
    return jsonify(id=req.id, status="applied", candidate_id=candidate.id), 200


@bp.get("/results/<path:result_path>")
def results(result_path):
    return jsonify(error="not_implemented"), 501  # STUB until R-22
