import pytest
from app import create_app, db
from app.config import TestConfig
from flask_jwt_extended import create_access_token

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
        with app.app_context():
            return create_access_token(
                identity=str(voter_id),
                additional_claims={"type": "voter", "division": "Test Division"},
            )
    return _token

@pytest.fixture()
def staff_token(app):
    def _token(role="auditor", mfa=True, staff_id=1):
        with app.app_context():
            return create_access_token(
                identity=str(staff_id),
                additional_claims={"type": "staff", "role": role, "mfa": mfa},
            )
    return _token
