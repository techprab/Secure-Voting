from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask_limiter.util import get_remote_address
"""Ballot routes. Owner: Jaewook (Slice B).

R-06: GET /ballot serves the candidate list only if it matches the last approved set.
R-07: the voter previews the exact ranking, confirms it, and only then is it committed.
      The receipt (participation code) proves that the voter took part, never how they voted.
"""
import hashlib
import json
import uuid
from datetime import timedelta

from flask import Blueprint, abort, g, jsonify, request
from flask_jwt_extended import create_access_token, decode_token

from .. import db, limiter
from ..models import Participation, PendingBallot, Voter
from ..security.crypto import seal_ballot
from ..security.voter_guard import begin_single_cast, consume_nonce, require_voter
from ..services.ballot_def import check_ballot_definition, current_candidates
from ..services.ballots import commit_with_seal

bp = Blueprint("ballot", __name__)

PREVIEW_TTL = timedelta(minutes=5)
PREVIEW_TOKEN_TYPE = "ballot_preview"


def current_voter() -> Voter:
    """Load the signed-in voter. require_voter stores the voter id in g.voter."""
    voter_id = g.voter if isinstance(g.voter, int) else g.voter.id
    voter = db.session.get(Voter, voter_id)
    if voter is None or not voter.eligible:
        abort(403)
    return voter


def preferences_hash(preferences: list[int]) -> str:
    """SHA-256 of the ranking. Only this hash goes into the preview token, never the ranking."""
    return hashlib.sha256(json.dumps(preferences, separators=(",", ":")).encode("utf-8")).hexdigest()


def valid_ranking(preferences, division: str) -> bool:
    """Every candidate of the division ranked exactly once, as a list of candidate ids."""
    if not isinstance(preferences, list) or not preferences:
        return False
    if any(type(p) is not int for p in preferences):
        return False
    candidate_ids = {c.id for c in current_candidates(division)}
    return len(preferences) == len(candidate_ids) and set(preferences) == candidate_ids


def bad_request(code: str):
    return jsonify(error=code), 400


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
@require_voter
def ballot_preview():
    voter = current_voter()
    check_ballot_definition(voter.division)
    preferences = (request.get_json(silent=True) or {}).get("preferences")
    if not valid_ranking(preferences, voter.division):
        return bad_request("invalid_ranking")

    names = {c.id: c.name for c in current_candidates(voter.division)}
    summary = [{"rank": i + 1, "candidate_id": cid, "name": names[cid]} for i, cid in enumerate(preferences)]
    token = create_access_token(
        identity=str(voter.id),
        additional_claims={
            "type": PREVIEW_TOKEN_TYPE,
            "division": voter.division,
            "pref_hash": preferences_hash(preferences),
        },
        expires_delta=PREVIEW_TTL,
    )
    return jsonify(summary=summary, preview_token=token), 200


def submission_voter_key():
    # Verify the signature before using identity as a rate-limit key.
    # Use voter identity, not the rotating session token.
    verify_jwt_in_request()
    return "voter:" + str(get_jwt_identity())


@bp.post("/ballot/submit")
@limiter.limit("30 per minute", key_func=get_remote_address)
@limiter.limit("10 per minute", key_func=submission_voter_key)
@require_voter
def ballot_submit():
    voter = current_voter()
    body = request.get_json(silent=True) or {}
    preferences = body.get("preferences")

    # 1. Explicit confirmation of the previewed ranking (R-07).
    if body.get("confirm") is not True:
        return bad_request("confirmation_required")
    try:
        claims = decode_token(body.get("preview_token") or "")
    except Exception:
        return bad_request("invalid_preview_token")
    if (
        claims.get("type") != PREVIEW_TOKEN_TYPE
        or claims.get("sub") != str(voter.id)
        or claims.get("division") != voter.division
        or not isinstance(preferences, list)
        or claims.get("pref_hash") != preferences_hash(preferences)
    ):
        return bad_request("preview_mismatch")
    if not valid_ranking(preferences, voter.division):
        return bad_request("invalid_ranking")

    nonce = body.get("nonce")
    try:
        nonce = str(uuid.UUID(str(nonce)))
    except ValueError:
        return bad_request("invalid_nonce")

    # 2. Ballot definition check (R-06) before anything is written.
    check_ballot_definition(voter.division)

    # 3. One transaction: replay check (R-04), one cast per voter (R-01),
    #    encrypted ballot into the pending buffer with no voter reference (R-14, R-02).
    consume_nonce(nonce)
    code = begin_single_cast(voter.id)
    db.session.add(PendingBallot(division=voter.division, blob=seal_ballot(preferences)))
    commit_with_seal(voter.division)
    return jsonify(participation_code=code), 201


@bp.get("/participation/<code>")
@limiter.limit("30 per minute", key_func=get_remote_address)
def participation(code):
    """Receipt check: says only that the code exists. No voter, time or ranking is returned."""
    if Participation.query.filter_by(code=code).first() is None:
        return jsonify(error="not_found"), 404
    return jsonify(voted=True), 200
