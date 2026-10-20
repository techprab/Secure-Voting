"""R-08: an auditor checks the ballot store against participation without re-linking them.

Owner: Jaewook (Slice B).

GET /audit/ballots/verify (auditor, MFA) returns counts only:
  {"chain_ok": bool,
   "divisions": {"<division>": {"sealed": n, "pending": n, "participation": n, "ok": bool}}}
ok means sealed + pending == participation, i.e. every recorded participation has exactly one
ballot and no ballot is unaccounted for. No voter id, participation code, ranking or blob is
returned, so the response cannot be used to link a voter to a ballot.
"""
from flask import Blueprint, jsonify
from sqlalchemy import func

from .. import db
from ..models import Ballot, Participation, PendingBallot, Voter
from ..security.crypto import verify_chain
from ..security.staff_guard import audited, require_staff

bp = Blueprint("audit_ballots", __name__, url_prefix="/audit/ballots")


def _counts_by_division(query) -> dict[str, int]:
    return {division: count for division, count in query.all()}


@bp.get("/verify")
@require_staff("auditor")
@audited("verify_ballots")
def verify_ballots():
    sealed = _counts_by_division(
        db.session.query(Ballot.division, func.count(Ballot.id)).group_by(Ballot.division))
    pending = _counts_by_division(
        db.session.query(PendingBallot.division, func.count(PendingBallot.id)).group_by(PendingBallot.division))
    participation = _counts_by_division(
        db.session.query(Voter.division, func.count(Participation.id))
        .join(Voter, Voter.id == Participation.voter_id)
        .group_by(Voter.division))

    divisions = {}
    for division in sorted(set(sealed) | set(pending) | set(participation)):
        row = {
            "sealed": sealed.get(division, 0),
            "pending": pending.get(division, 0),
            "participation": participation.get(division, 0),
        }
        row["ok"] = row["sealed"] + row["pending"] == row["participation"]
        divisions[division] = row

    return jsonify(chain_ok=verify_chain(), divisions=divisions), 200
