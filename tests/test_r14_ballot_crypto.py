
import base64
import os

import pytest

from app import create_app, db
from app.config import TestConfig
from app.models import Ballot
from app.security.crypto import (
    seal_ballot,
    open_ballot,
    chain_hash,
    verify_chain,
)


@pytest.fixture
def app_with_test_db(monkeypatch):
    # Use a separate, randomly generated key for testing.
    test_key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("BALLOT_KEY", test_key)

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_ballot_encrypts_and_decrypts(app_with_test_db):
    preferences = [2, 1, 3]

    encrypted = seal_ballot(preferences)

    assert isinstance(encrypted, bytes)
    assert encrypted != b"[2,1,3]"
    assert open_ballot(encrypted) == preferences


def test_tampered_ballot_is_rejected(app_with_test_db):
    encrypted = seal_ballot([1, 2, 3])
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(ValueError):
        open_ballot(tampered)


def test_valid_hash_chain_passes(app_with_test_db):
    first_blob = seal_ballot([1, 2])
    first_hash = chain_hash("0" * 64, first_blob)

    first = Ballot(
        division="test",
        blob=first_blob,
        prev_hash="0" * 64,
        hash=first_hash,
    )
    db.session.add(first)
    db.session.commit()

    second_blob = seal_ballot([2, 1])
    second_hash = chain_hash(first_hash, second_blob)

    second = Ballot(
        division="test",
        blob=second_blob,
        prev_hash=first_hash,
        hash=second_hash,
    )
    db.session.add(second)
    db.session.commit()

    assert verify_chain() is True


def test_broken_hash_chain_fails(app_with_test_db):
    blob = seal_ballot([1, 2])
    correct_hash = chain_hash("0" * 64, blob)

    ballot = Ballot(
        division="test",
        blob=blob,
        prev_hash="f" * 64,
        hash=correct_hash,
    )
    db.session.add(ballot)
    db.session.commit()

    assert verify_chain() is False
