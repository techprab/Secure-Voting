
"""Cryptographic interfaces owned by Daksh (Slice D).

Ballots are encrypted using AES-256-GCM.
The stored blob format is: 12-byte nonce + ciphertext + 16-byte tag.
"""

import base64
import hashlib
import json
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .. import db
from ..models import Ballot


NONCE_SIZE = 12
KEY_SIZE = 32


def _get_ballot_key() -> bytes:
    """Load a 32-byte AES key encoded as Base64 in BALLOT_KEY."""
    encoded_key = os.getenv("BALLOT_KEY", "").strip()

    if not encoded_key:
        raise ValueError("BALLOT_KEY is not configured.")

    try:
        key = base64.b64decode(encoded_key, validate=True)
    except Exception as exc:
        raise ValueError("BALLOT_KEY must contain valid Base64.") from exc

    if len(key) != KEY_SIZE:
        raise ValueError("BALLOT_KEY must decode to exactly 32 bytes.")

    return key


def seal_ballot(preferences: list[int]) -> bytes:
    """Encrypt preferences and return nonce + ciphertext + authentication tag."""
    if not isinstance(preferences, list) or any(
        type(value) is not int for value in preferences
    ):
        raise ValueError("Preferences must be a list of integers.")

    plaintext = json.dumps(
        preferences, separators=(",", ":")
    ).encode("utf-8")

    nonce = os.urandom(NONCE_SIZE)
    ciphertext_and_tag = AESGCM(_get_ballot_key()).encrypt(
        nonce, plaintext, None
    )

    return nonce + ciphertext_and_tag


def open_ballot(blob: bytes) -> list[int]:
    """Authenticate and decrypt a ballot."""
    if not isinstance(blob, bytes) or len(blob) < NONCE_SIZE + 16:
        raise ValueError("Invalid encrypted ballot format.")

    nonce = blob[:NONCE_SIZE]
    ciphertext_and_tag = blob[NONCE_SIZE:]

    try:
        plaintext = AESGCM(_get_ballot_key()).decrypt(
            nonce, ciphertext_and_tag, None
        )
    except InvalidTag as exc:
        raise ValueError(
            "Ballot authentication failed; data may be corrupted or tampered with."
        ) from exc

    try:
        preferences = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Decrypted ballot contains invalid data.") from exc

    if not isinstance(preferences, list) or any(
        type(value) is not int for value in preferences
    ):
        raise ValueError("Decrypted ballot preferences are invalid.")

    return preferences


def chain_hash(prev_hash: str, blob: bytes) -> str:
    """Calculate the SHA-256 hash for a ballot and its previous hash."""
    return hashlib.sha256(prev_hash.encode("utf-8") + blob).hexdigest()


def verify_chain() -> bool:
    """Verify ballot hashes and previous-hash links in ID order."""
    previous_hash = "0" * 64

    ballots = db.session.query(Ballot).order_by(Ballot.id.asc()).all()

    for ballot in ballots:
        if ballot.prev_hash != previous_hash:
            return False

        expected_hash = chain_hash(previous_hash, ballot.blob)

        if not hmac.compare_digest(expected_hash, ballot.hash):
            return False

        previous_hash = ballot.hash

    return True
