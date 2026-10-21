"""Shared fixtures for Slice E (count & publish) tests."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import db
from app.models import Ballot, Candidate
from app.security.crypto import chain_hash, seal_ballot

DIVISION = "Division E"


@pytest.fixture()
def signing_key(app):
    """A fresh P-384 key for each test, never a key from the repo."""
    key = ec.generate_private_key(ec.SECP384R1())
    app.config["RESULT_SIGNING_KEY"] = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return key


@pytest.fixture()
def candidates(app):
    """Three candidates in DIVISION. Returns their ids as (a, b, c)."""
    rows = [Candidate(division=DIVISION, name=n, position=str(i + 1), excluded=False)
            for i, n in enumerate(("Alpha", "Bravo", "Charlie"))]
    db.session.add_all(rows)
    db.session.commit()
    return tuple(r.id for r in rows)


@pytest.fixture()
def add_ballots(app):
    """Seal ballots with the real AES-GCM code and append them to the hash chain."""
    def _add(rankings, division=DIVISION):
        last = db.session.query(Ballot).order_by(Ballot.id.desc()).first()
        prev = last.hash if last else "0" * 64
        for ranking in rankings:
            blob = seal_ballot(list(ranking))
            row_hash = chain_hash(prev, blob)
            db.session.add(Ballot(division=division, blob=blob, prev_hash=prev,
                                  hash=row_hash, batch_id="test"))
            prev = row_hash
        db.session.commit()
    return _add


@pytest.fixture()
def auth():
    return lambda token: {"Authorization": f"Bearer {token}"}
