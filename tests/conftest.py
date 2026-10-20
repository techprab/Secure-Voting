import pytest
from datetime import date, timedelta

from app import create_app, db
from app.config import TestConfig
from app.models import Voter, Staff
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def voter_token(app):
    def _token(voter_id=1):
        voter = db.session.get(Voter, voter_id)

        if voter is None:
            voter = Voter(
                id=voter_id,
                name=f"Test Voter {voter_id}",
                division="Test Division",
                eligible=True,
                overseas=False,
                password_hash=generate_password_hash(
                    "test-password"
                ),
            )
            db.session.add(voter)
            db.session.commit()

        return create_access_token(
            identity=str(voter.id),
            additional_claims={
                "type": "voter",
                "division": voter.division,
            },
        )

    return _token

@pytest.fixture()
def staff_token(app):
    """Create a JWT for a Staff row with the requested role."""

    def _token(role="auditor", mfa=True, staff_id=None):
        if staff_id is None:
            staff = (
                Staff.query
                .filter_by(role=role)
                .order_by(Staff.id)
                .first()
            )
        else:
            staff = db.session.get(Staff, staff_id)

        if staff is None:
            staff = Staff(
                id=staff_id,
                username=f"test-{role}-{staff_id if staff_id is not None else 'auto'}",
                role=role,
                password_hash="unused",
                totp_secret="unused",
                recertified_until=date.today() + timedelta(days=90),
            )
            db.session.add(staff)
            db.session.commit()

        assert staff.role == role, (
            f"Staff {staff.id} is a {role}, not a {staff.role}"
        )

        return create_access_token(
            identity=str(staff.id),
            additional_claims={
                "type": "staff",
                "role": role,
                "mfa": mfa,
            },
        )

    return _token