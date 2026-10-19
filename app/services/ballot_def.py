"""R-06: the ballot is served and accepted only against the last approved candidate set.

Owner: Jaewook (Slice B).
"""
import hashlib
import hmac
import json

from .. import db
from ..errors import DefinitionMismatch
from ..models import Candidate, CandidateSetApproval
from .audit_log import append_audit


def current_candidates(division: str) -> list[Candidate]:
    """Candidates of a division in ballot order (position, then id as a tie-break)."""
    return (
        Candidate.query.filter_by(division=division)
        .order_by(Candidate.position, Candidate.id)
        .all()
    )


def candidate_set_hash(division: str) -> str:
    """SHA-256 over the canonical JSON of [id, name, position] for each candidate.

    `excluded` is left out on purpose: excluding a candidate after a court order
    (R-21) must not stop the ballot being served.
    position is converted to str so the hash does not change if the column type does.
    """
    rows = [[c.id, c.name, str(c.position)] for c in current_candidates(division)]
    canonical = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def latest_approval(division: str) -> CandidateSetApproval | None:
    return (
        CandidateSetApproval.query.filter_by(division=division)
        .order_by(CandidateSetApproval.id.desc())
        .first()
    )


def check_ballot_definition(division: str) -> None:
    """Raise DefinitionMismatch (503) unless the current set matches the latest approval.

    A mismatch is recorded as a system audit event (actor_id=None) and committed
    straight away, so the record survives the error response.
    """
    approval = latest_approval(division)
    current = candidate_set_hash(division)
    if approval is None or not hmac.compare_digest(approval.set_hash, current):
        append_audit(
            "ballot_definition_mismatch",
            actor_id=None,
            before={"division": division, "approved_hash": approval.set_hash if approval else None},
            after={"division": division, "current_hash": current},
        )
        db.session.commit()
        raise DefinitionMismatch()
