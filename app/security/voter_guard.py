"""STUBS owned by Dev (Slice A). Do not treat as production security."""
from functools import wraps
from flask import g
from flask_jwt_extended import (
    verify_jwt_in_request, 
    get_jwt, 
    get_jwt_identity, 
    create_access_token
)
from .. import db
from ..errors import ReplayError, AlreadyVotedError
from ..models import UsedNonce, Participation
from ..services.audit_log import append_audit
import secrets
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

def require_voter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("type") != "voter":
            return {"error": "forbidden"}, 403
        g.voter = int(get_jwt_identity())
        
        # R-03: Sliding 15-minute expiry
        new_token = create_access_token(
            identity=g.voter,
            additional_claims={"type": "voter", "division": claims.get("division")},
            expires_delta=timedelta(minutes=15)
        )
        g.new_session_token = new_token
        
        return fn(*args, **kwargs)
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
    except IntegrityError:
        db.session.rollback()
        raise AlreadyVotedError()
        
    return code