"""Count & publish routes. Owner: Prabh (Slice E).

R-12  POST /count/recount/<division>        officer + MFA, recomputes from sealed ballots
R-21  POST /exclusions                      delegate, first approval of a court-ordered exclusion
      POST /exclusions/<id>/approve         a *different* delegate, within 15 minutes
R-22  POST /results/release/<division>      officer + MFA, release_check, then ECDSA P-384 signature
      GET  /results/public-key              public PEM, so anyone can verify offline
      GET  /results/<division>/latest       latest signed release for external systems
      POST /results/verify                  {"payload", "signature"} -> {"valid": bool}

Privileged routes stack the decorators as require_staff -> _commit_on_success -> audited,
so the state change and its audit entry are committed in one transaction, or neither is.
"""
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Blueprint, current_app, g, jsonify, make_response, request

from .. import db, limiter
from ..models import Candidate, ExclusionRequest, ResultRelease
from ..security.crypto import verify_chain
from ..security.staff_guard import audited, require_staff
from ..services.count import UnknownDivision, count_a, release_check, write_display_cache

bp = Blueprint("count", __name__)

EXCLUSION_WINDOW = timedelta(minutes=15)
SIGNATURE_ALGORITHM = "ECDSA-P384-SHA384"


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


# --------------------------------------------------------------------------- R-22

class SigningKeyUnavailable(RuntimeError):
    pass


def _signing_key() -> ec.EllipticCurvePrivateKey:
    """Load the P-384 private key from RESULT_SIGNING_KEY: PEM text, or a path to a PEM file."""
    value = (current_app.config.get("RESULT_SIGNING_KEY") or "").strip()
    if not value or value.startswith("replace-with"):
        raise SigningKeyUnavailable("RESULT_SIGNING_KEY is not configured")
    if "BEGIN" not in value and os.path.isfile(value):
        with open(value, "rb") as fh:
            pem = fh.read()
    else:
        pem = value.replace("\\n", "\n").encode("utf-8")
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except ValueError as exc:
        raise SigningKeyUnavailable("RESULT_SIGNING_KEY is not a valid PEM key") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp384r1":
        raise SigningKeyUnavailable("RESULT_SIGNING_KEY must be an ECDSA P-384 key")
    return key


def _public_pem(key: ec.EllipticCurvePrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


@bp.post("/results/release/<division>")
@require_staff("officer", mfa=True)
@_commit_on_success
@audited("result_release")
def release_result(division):
    try:
        key = _signing_key()
    except SigningKeyUnavailable:
        return jsonify(error="signing_key_unavailable"), 503
    try:
        totals = release_check(division)  # raises ReleaseBlocked -> 409 release_blocked
    except UnknownDivision:
        return jsonify(error="unknown_division"), 404

    released_at = _now().replace(microsecond=0)
    payload = json.dumps(
        {"division": division,
         "totals": {str(k): v for k, v in totals.items()},
         "released_at": released_at.isoformat() + "Z"},
        sort_keys=True, separators=(",", ":"),
    )
    signature = base64.b64encode(
        key.sign(payload.encode("utf-8"), ec.ECDSA(hashes.SHA384()))
    ).decode("ascii")

    release = ResultRelease(division=division, payload=payload,
                            signature=signature, released_at=released_at)
    db.session.add(release)
    db.session.flush()

    g.audit_after = {"release_id": release.id, "division": division,
                     "payload_sha384": _sha384_hex(payload)}
    return jsonify(release_id=release.id, payload=payload, signature=signature,
                   algorithm=SIGNATURE_ALGORITHM), 201


def _sha384_hex(text: str) -> str:
    digest = hashes.Hash(hashes.SHA384())
    digest.update(text.encode("utf-8"))
    return digest.finalize().hex()


@bp.get("/results/public-key")
def public_key():
    try:
        key = _signing_key()
    except SigningKeyUnavailable:
        return jsonify(error="signing_key_unavailable"), 503
    return jsonify(algorithm=SIGNATURE_ALGORITHM, public_key=_public_pem(key)), 200


@bp.get("/results/<division>/latest")
def latest_release(division):
    release = (ResultRelease.query.filter_by(division=division)
               .order_by(ResultRelease.id.desc()).first())
    if release is None:
        return jsonify(error="not_released"), 404
    return jsonify(release_id=release.id, payload=release.payload,
                   signature=release.signature, algorithm=SIGNATURE_ALGORITHM), 200


@bp.post("/results/verify")
@limiter.limit("30 per minute")
def verify_result():
    body = request.get_json(silent=True) or {}
    payload, signature = body.get("payload"), body.get("signature")
    if not isinstance(payload, str) or not isinstance(signature, str):
        return jsonify(error="bad_request"), 400
    try:
        key = _signing_key()
    except SigningKeyUnavailable:
        return jsonify(error="signing_key_unavailable"), 503
    try:
        key.public_key().verify(base64.b64decode(signature, validate=True),
                                payload.encode("utf-8"), ec.ECDSA(hashes.SHA384()))
        valid = True
    except (InvalidSignature, ValueError):
        valid = False
    return jsonify(valid=valid), 200
