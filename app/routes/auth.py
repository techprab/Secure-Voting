from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
import bcrypt
from datetime import timedelta
from .. import db, limiter
from ..models import Voter
from ..security.mission_guard import mission_access_allowed
from ..security.voter_guard import voter_session_token

# This MUST be called 'bp' to match app/__init__.py
bp = Blueprint('auth', __name__)

# R-20: Rate limiting on login to prevent brute force
@bp.route('/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "invalid_request"}, 400
    username = data.get('username')
    password = data.get('password')

    if (not isinstance(username, str) or not username
            or not isinstance(password, str) or not password):
        return {"error": "missing_credentials"}, 400

    voter = Voter.query.filter_by(name=username).first()

    if not voter or not password_matches(password, voter.password_hash):
        return {"error": "unauthorized"}, 401

    if not voter.eligible:
        return {"error": "ineligible_voter"}, 403

    if not mission_access_allowed(voter):
        return {"error": "mission_access_denied"}, 403

    token = voter_session_token(voter)
    response = jsonify({
        "token": token,
        "voter_id": voter.id,
        "division": voter.division,
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200



def password_matches(password, stored_hash):
    # A malformed stored hash or an over-long password makes bcrypt raise.
    # Treat both as a failed login instead of a server error.
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError, AttributeError):
        return False
