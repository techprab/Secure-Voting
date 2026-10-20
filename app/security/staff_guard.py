"""STUBS owned by Riya (Slice C)."""
from datetime import date
from functools import wraps

from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity

from .. import db
from ..models import Staff
from ..services.audit_log import append_audit


def require_staff(*roles: str, mfa: bool = True):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()

            # 1. Require a staff token
            if claims.get("type") != "staff":
                return {"error": "unauthorized"}, 401

            # 2. Load the current staff record from the database
            staff = db.session.get(Staff, get_jwt_identity())
            if staff is None:
                return {"error": "unauthorized"}, 401

            # 3. Check the staff member's current role
            token_role = claims.get("role")

            if token_role not in roles:
                return {"error": "forbidden"}, 403

            if staff.role not in roles or staff.role != token_role:
                return {"error": "forbidden"}, 403

            # 4. Require valid 90-day recertification
            if (
                staff.recertified_until is None
                or staff.recertified_until < date.today()
            ):
                return {"error": "forbidden"}, 403

            # 5. Require MFA when the route needs it
            if mfa and not claims.get("mfa", False):
                return {"error": "forbidden"}, 403

            # 6. Make the database-backed staff record available to the route
            g.staff = staff

            return fn(*args, **kwargs)

        return wrapper
    return decorator

def audited(action: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)

            # Record the audit entry in the current transaction.
            append_audit(
                action,
                getattr(getattr(g, "staff", None), "id", None),
            )

            # Persist the audit entry before the request session is removed.
            db.session.commit()

            return result
        return wrapper
    return decorator
