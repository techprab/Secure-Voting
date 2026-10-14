from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
import bcrypt
from datetime import timedelta
from .. import db, limiter
from ..models import Voter
from ..config import Config

# This MUST be called 'bp' to match app/__init__.py
bp = Blueprint('auth', __name__)

# R-20: Rate limiting on login to prevent brute force
@bp.route('/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return {"error": "missing_credentials"}, 400

    # R-13: Overseas fail-closed check
    client_ip = request.remote_addr
    if is_overseas_request(client_ip):
        cert_header = request.headers.get('X-Client-Cert')
        if not cert_header or cert_header not in Config.MISSION_CERTS:
            return {"error": "forbidden"}, 403

    voter = Voter.query.filter_by(name=username).first()

    if not voter or not bcrypt.checkpw(password.encode('utf-8'), voter.password_hash.encode('utf-8')):
        return {"error": "unauthorized"}, 401

    # R-03: Issue a 15-minute session token
    token = create_access_token(
        identity=str(voter.id),
        additional_claims={"type": "voter", "division": voter.division},
        expires_delta=timedelta(minutes=15)
    )

    return jsonify({"token": token, "voter_id": voter.id, "division": voter.division}), 200


def is_overseas_request(client_ip):
    # R-13: Fail-closed logic
    # Localhost / test client should not be treated as overseas
    if client_ip in ("127.0.0.1", "localhost", "::1") or client_ip.startswith("127."):
        return False
    # If allowlist is empty, everything else is overseas (fail closed)
    if not Config.MISSION_ALLOWLIST:
        return True
    for cidr in Config.MISSION_ALLOWLIST:
        if client_ip.startswith(cidr.split('/')[0].rsplit('.', 1)[0]):
            return False
    return True