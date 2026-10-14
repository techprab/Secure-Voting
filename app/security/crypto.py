"""Cryptographic interfaces owned by Daksh (Slice D).

IMPORTANT: These are skeleton stubs only. Do not use them for real voting.
Replace seal_ballot/open_ballot with AES-256-GCM before integrating real ballots.
"""
import hashlib
import json
from .. import db
from ..models import Ballot

def seal_ballot(preferences: list[int]) -> bytes:
    # STUB — owner D replaces with AES-256-GCM; plain JSON is NOT secure.
    return json.dumps(preferences, separators=(",", ":")).encode("utf-8")

def open_ballot(blob: bytes) -> list[int]:
    # STUB — owner D replaces with AES-256-GCM and authenticated decryption.
    return json.loads(blob.decode("utf-8"))

def chain_hash(prev_hash: str, blob: bytes) -> str:
    return hashlib.sha256(prev_hash.encode("utf-8") + blob).hexdigest()

def verify_chain() -> bool:
    # STUB — owner D replaces with recomputation of every Ballot.hash in ID order.
    return True
