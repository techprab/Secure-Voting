"""STUBS owned by Riya (Slice C)."""
from functools import wraps
from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity
from ..services.audit_log import append_audit

def require_staff(*roles: str, mfa: bool = True):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("type") != "staff":
                return {"error": "unauthorized"}, 401
            if claims.get("role") not in roles:
                return {"error": "forbidden"}, 403
            if mfa and not claims.get("mfa", False):
                return {"error": "forbidden"}, 403
            g.staff = type("StaffContext", (), {"id": get_jwt_identity()})()
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def audited(action: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import make_response

            result = fn(*args, **kwargs)
            response = make_response(result)

            # Record only successful responses (HTTP status below 400).
            if response.status_code < 400:
                staff = getattr(g, "staff", None)
                actor_id = getattr(staff, "id", None)

                append_audit(
                    action,
                    actor_id,
                    before=g.get("audit_before"),
                    after=g.get("audit_after"),
                )

            return result
        return wrapper
    return decorator
