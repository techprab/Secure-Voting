"""STUBS owned by Jaewook (Slice B)."""
from ..models import Ballot, PendingBallot
from .. import db

def flush_pending(division: str) -> int:
    # STUB: move pending rows to the sealed ballot store with hash-chain updates.
    return 0

def sealed_ballots(division: str) -> list[Ballot]:
    # STUB: counting must read only this function, never PendingBallot directly.
    return Ballot.query.filter_by(division=division).order_by(Ballot.id).all()
