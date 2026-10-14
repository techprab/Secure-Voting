"""Minimal development seed. Expand after crypto implementation is merged."""
from app import create_app, db
from app.models import Voter, Staff, Candidate
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    db.create_all()
    if not Voter.query.first():
        db.session.add(Voter(
            name="Demo Voter", division="Division 1", eligible=True,
            overseas=False, password_hash=generate_password_hash("change-this-demo-password")
        ))
    if not Staff.query.first():
        db.session.add(Staff(
            username="demo-auditor", role="auditor",
            password_hash=generate_password_hash("change-this-demo-password"),
            totp_secret="JBSWY3DPEHPK3PXP"
        ))
    if not Candidate.query.first():
        db.session.add_all([
            Candidate(division="Division 1", name="Candidate A", position="House"),
            Candidate(division="Division 1", name="Candidate B", position="House"),
            Candidate(division="Division 1", name="Candidate C", position="House"),
        ])
    db.session.commit()
    print("Seed complete. Demo credentials are for local development only.")
