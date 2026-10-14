from datetime import datetime
from .. import db

class Voter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    division = db.Column(db.String(120), nullable=False)
    eligible = db.Column(db.Boolean, nullable=False, default=True)
    overseas = db.Column(db.Boolean, nullable=False, default=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Participation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voter.id"), nullable=False, unique=True)
    code = db.Column(db.String(64), nullable=False, unique=True)
    voted_hour = db.Column(db.String(16), nullable=False)

class PendingBallot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    blob = db.Column(db.LargeBinary, nullable=False)

class Ballot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    blob = db.Column(db.LargeBinary, nullable=False)
    prev_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)
    batch_id = db.Column(db.String(64), nullable=True)

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    position = db.Column(db.String(80), nullable=False)
    excluded = db.Column(db.Boolean, nullable=False, default=False)

class CandidateSetApproval(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    set_hash = db.Column(db.String(64), nullable=False)
    approved_by = db.Column(db.Integer, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    totp_secret = db.Column(db.String(64), nullable=False)
    recertified_until = db.Column(db.Date, nullable=True)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(120), nullable=False)
    before = db.Column(db.Text, nullable=True)
    after = db.Column(db.Text, nullable=True)
    ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    prev_hash = db.Column(db.String(64), nullable=False, default=lambda: "0" * 64)
    hash = db.Column(db.String(64), nullable=False, default=lambda: "0" * 64)

class UsedNonce(db.Model):
    nonce = db.Column(db.String(36), primary_key=True)

class ExclusionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, nullable=False)
    court_ref = db.Column(db.String(120), nullable=False)
    approver_1 = db.Column(db.Integer, nullable=True)
    approver_2 = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    applied = db.Column(db.Boolean, nullable=False, default=False)

class ResultRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    payload = db.Column(db.Text, nullable=False)
    signature = db.Column(db.Text, nullable=False)
    released_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class CountCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(120), nullable=False)
    candidate_id = db.Column(db.Integer, nullable=False)
    votes = db.Column(db.Integer, nullable=False, default=0)
