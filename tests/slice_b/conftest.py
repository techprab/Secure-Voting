"""Shared fixtures for slice B tests (Jaewook): R-02, R-06, R-07, R-08.

Builds on the root tests/conftest.py (owner Daksh): app, client, voter_token, staff_token.
Every test creates its own division "TEST-DIV", so nothing depends on seed.py.
"""
import uuid
from datetime import date, datetime, timedelta

import pytest

from app import db
from app import models

DIV = "TEST-DIV"
CANDIDATE_NAMES = ["Alpha", "Bravo", "Charlie"]


@pytest.fixture
def division(app):
    """TEST-DIV: 3 candidates in ballot order 1-3, an approval of that set, 25 eligible voters."""
    from app.services.ballot_def import candidate_set_hash

    delegate = models.Staff(
        username=f"delegate-{uuid.uuid4().hex[:6]}", role="delegate",
        password_hash="unused", totp_secret="unused",
        recertified_until=date.today() + timedelta(days=90),
    )
    candidates = [models.Candidate(division=DIV, name=n, position=str(i + 1), excluded=False)
                  for i, n in enumerate(CANDIDATE_NAMES)]
    voters = [models.Voter(name=f"Voter {i}", division=DIV, eligible=True, overseas=False,
                           password_hash="unused") for i in range(25)]
    db.session.add_all([delegate] + candidates + voters)
    db.session.flush()
    db.session.add(models.CandidateSetApproval(
        division=DIV, set_hash=candidate_set_hash(DIV),
        approved_by=delegate.id, approved_at=datetime.utcnow(),
    ))
    db.session.commit()
    return {
        "name": DIV,
        "candidates": [c.id for c in candidates],
        "voters": [v.id for v in voters],
    }


@pytest.fixture
def auth(voter_token, staff_token):
    """auth(voter_id=3) or auth(role="auditor") -> {"Authorization": "Bearer ..."}"""
    def _auth(voter_id=None, role=None, mfa=True):
        token = voter_token(voter_id) if voter_id is not None else staff_token(role, mfa=mfa)
        return {"Authorization": f"Bearer {token}"}
    return _auth


@pytest.fixture
def preview(client, auth):
    """preview(voter_id, preferences) -> response of POST /ballot/preview"""
    def _preview(voter_id, preferences):
        return client.post("/ballot/preview", json={"preferences": preferences},
                           headers=auth(voter_id=voter_id))
    return _preview


@pytest.fixture
def cast(client, auth, preview):
    """cast(voter_id, preferences, body=None) -> response of POST /ballot/submit after a valid preview.
    `body` replaces fields of the submit request, e.g. {"confirm": False}."""
    def _cast(voter_id, preferences, body=None):
        p = preview(voter_id, preferences)
        assert p.status_code == 200, p.get_json()
        payload = {
            "preferences": preferences,
            "preview_token": p.get_json()["preview_token"],
            "confirm": True,
            "nonce": str(uuid.uuid4()),
        }
        payload.update(body or {})
        return client.post("/ballot/submit", json=payload, headers=auth(voter_id=voter_id))
    return _cast


@pytest.fixture
def counts():
    """counts() -> {"pending": n, "sealed": n, "participation": n} for TEST-DIV"""
    def _counts(div=DIV):
        participation = (db.session.query(models.Participation)
                         .join(models.Voter, models.Voter.id == models.Participation.voter_id)
                         .filter(models.Voter.division == div).count())
        return {
            "pending": db.session.query(models.PendingBallot).filter_by(division=div).count(),
            "sealed": db.session.query(models.Ballot).filter_by(division=div).count(),
            "participation": participation,
        }
    return _counts
