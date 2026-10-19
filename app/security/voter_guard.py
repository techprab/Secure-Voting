"""STUBS owned by Dev (Slice A). Do not treat as production security."""
from functools import wraps
from flask import g, current_app, make_response, abort
from flask_jwt_extended import (
    verify_jwt_in_request, 
    get_jwt, 
    get_jwt_identity, 
    create_access_token
)
from .. import db
from ..errors import ReplayError, AlreadyVotedError
from ..models import UsedNonce, Participation, Voter
from ..services.audit_log import append_audit
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError

def voter_session_token(voter):
    """Issue a voter token expiring at inactivity timeout or poll close.

    A deadline without a timezone is interpreted as UTC.
    Missing or invalid deadline configuration denies access.
    """
    value = current_app.config.get("WINDOW_CLOSE")
    try:
        close = (
            value if isinstance(value, datetime)
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
        if close.tzinfo is None:
            close = close.replace(tzinfo=timezone.utc)
        close = close.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError):
        abort(make_response(
            {"error": "voting_window_unavailable"}, 503
        ))

    now = datetime.now(timezone.utc)
    expiry = min(now + timedelta(minutes=15), close)
    expiry_timestamp = int(expiry.timestamp())
    if expiry_timestamp <= now.timestamp():
        abort(make_response({"error": "voting_closed"}, 401))

    return create_access_token(
        identity=str(voter.id),
        additional_claims={
            "type": "voter",
            "division": voter.division,
            "exp": expiry_timestamp,
        },
        expires_delta=expiry - now,
    )


def require_voter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("type") != "voter":
            return {"error": "forbidden"}, 403

        try:
            voter_id = int(get_jwt_identity())
        except (TypeError, ValueError):
            return {"error": "unauthorized"}, 401

        voter = db.session.get(Voter, voter_id)
        if voter is None:
            return {"error": "unauthorized"}, 401
        if not voter.eligible:
            return {"error": "ineligible_voter"}, 403

        # Keep the integer interface used by the ballot routes.
        g.voter = voter.id

        # Check the voting deadline before the protected action runs.
        new_token = voter_session_token(voter)
        response = make_response(fn(*args, **kwargs))

        # Only successful requests renew the client's session.
        if 200 <= response.status_code < 300:
            response.headers["X-Session-Token"] = new_token
            response.headers["Cache-Control"] = "no-store"
        return response
    return wrapper


def consume_nonce(nonce: str) -> None:
    # R-04: records nonce; raises ReplayError if seen before
    if db.session.get(UsedNonce, nonce):
        append_audit(action="replay", actor_id=None)
        raise ReplayError()
    db.session.add(UsedNonce(nonce=nonce))
    db.session.flush()

def begin_single_cast(voter_id: int) -> str:
    # R-01: adds Participation(voter_id) in the current transaction
    code = secrets.token_urlsafe(24)
    
    # Single timestamp assignment
    voted_hour = datetime.utcnow().strftime("%Y-%m-%d %H")
    
    row = Participation(
        voter_id=voter_id,
        code=code,
        voted_hour=voted_hour,
    )
    
    try:
        db.session.add(row)
        db.session.flush()  # Moved inside try/except per Daksh's review
    except IntegrityError as exc:
        db.session.rollback()
        raise AlreadyVotedError() from exc
        
    return code