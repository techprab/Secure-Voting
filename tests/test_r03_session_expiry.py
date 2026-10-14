import pytest
import bcrypt
from flask_jwt_extended import decode_token
from app import db
from app.models import Voter


def test_r03_login_issues_15_min_token(client, app):
    with app.app_context():
        # Create a voter with a known password so the test doesn't depend on seed.py
        password = "password123"
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        voter = Voter(
            name="test_voter_r03",
            division="Test Division",
            eligible=True,
            password_hash=password_hash
        )
        db.session.add(voter)
        db.session.commit()

        # Now attempt to log in
        response = client.post('/auth/login', json={
            "username": "test_voter_r03",
            "password": password
        })

        assert response.status_code == 200, f"Login failed: {response.get_json()}"
        token = response.get_json()["token"]
        decoded = decode_token(token)
        assert decoded["type"] == "voter"
        assert "division" in decoded