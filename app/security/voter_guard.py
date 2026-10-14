"""STUBS owned by Dev (Slice A). Do not treat as production security."""
from functools import wraps
from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from .. import db
from ..errors import ReplayError, AlreadyVotedError
from ..models import UsedNonce, Participation
import secrets
from datetime import datetime

def require_voter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if claims.get("type") != "voter":
            return {"error": "forbidden"}, 403
        g.voter = get_jwt_identity()
        # STUB: sliding 15-minute token refresh is not implemented.
        return fn(*args, **kwargs)
    return wrapper

def consume_nonce(nonce: str) -> None:
    # STUB: currently records nonce, but replay audit integration is pending.
    if db.session.get(UsedNonce, nonce):
        raise ReplayError()
    db.session.add(UsedNonce(nonce=nonce))
    db.session.flush()

def begin_single_cast(voter_id: int) -> str:
    # STUB: relies on DB UNIQUE constraint; owner A must handle IntegrityError/rollback.
    code = secrets.token_urlsafe(24)
    row = Participation(
        voter_id=voter_id,
        code=code,
        voted_hour=datetime.utcnow().strftime("%Y-%m-%d %H"),
    )
    db.session.add(row)
    db.session.flush()
    return code
