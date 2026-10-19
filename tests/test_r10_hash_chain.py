import pytest

from app import db
from app.models import Ballot
from app.security.crypto import (
    seal_ballot,
    open_ballot,
    chain_hash,
    verify_chain,
)


GENESIS_HASH = "0" * 64


def add_ballot(blob, previous_hash):
    """Create a ballot linked to the preceding hash."""
    ballot_hash = chain_hash(previous_hash, blob)

    ballot = Ballot(
        division="Test Division",
        blob=blob,
        prev_hash=previous_hash,
        hash=ballot_hash,
    )
    db.session.add(ballot)
    db.session.commit()
    return ballot


def test_r10_wrong_key_fails_decryption(app):
    """A ballot encrypted with a different key must not decrypt."""
    with app.app_context():
        original_key = app.config["BALLOT_KEY"]
        blob = seal_ballot([1, 2])

        # Use a different valid 32-byte key for the decryption attempt.
        app.config["BALLOT_KEY"] = (
            "OTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTBmZWRjYg=="
        )

        try:
            with pytest.raises(ValueError):
                open_ballot(blob)
        finally:
            app.config["BALLOT_KEY"] = original_key


def test_r10_same_vote_produces_different_ciphertext(app):
    """Fresh nonces should make repeated encryption produce different blobs."""
    with app.app_context():
        first_blob = seal_ballot([1, 2])
        second_blob = seal_ballot([1, 2])

        assert first_blob != second_blob

        # Both ciphertexts must still decrypt to the same preferences.
        assert open_ballot(first_blob) == [1, 2]
        assert open_ballot(second_blob) == [1, 2]


def test_r10_modified_ballot_data_detected(app):
    """Changing stored ballot bytes must invalidate the hash chain."""
    with app.app_context():
        blob = seal_ballot([1, 2])
        ballot = add_ballot(blob, GENESIS_HASH)

        assert verify_chain() is True

        # Change the stored data without updating its recorded hash.
        ballot.blob = bytes([blob[0] ^ 1]) + blob[1:]
        db.session.commit()

        assert verify_chain() is False


def test_r10_deleted_ballot_row_detected(app):
    """Deleting a middle ballot must break the links in the chain."""
    with app.app_context():
        first_blob = seal_ballot([1])
        first = add_ballot(first_blob, GENESIS_HASH)

        second_blob = seal_ballot([2])
        second = add_ballot(second_blob, first.hash)

        third_blob = seal_ballot([3])
        add_ballot(third_blob, second.hash)

        assert verify_chain() is True

        # Delete the middle row. The third row still references its hash.
        db.session.delete(second)
        db.session.commit()

        assert verify_chain() is False
