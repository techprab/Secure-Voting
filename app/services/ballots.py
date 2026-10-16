"""R-02: ballots leave the pending buffer only in sets of 20 or more.

Owner: Jaewook (Slice B).

Submitted ballots wait in PendingBallot. Once a division has at least 20, the whole set is
shuffled and moved to the sealed Ballot store together, so the order and time of sealing
cannot be matched to the order and time of individual submissions.
After the voting window closes, a smaller remainder is sealed by force (WINDOW_CLOSE + 60 min).
"""
import secrets
import uuid
from datetime import datetime, timedelta

from flask import current_app

from .. import db
from ..models import Ballot, PendingBallot
from ..security.crypto import chain_hash

MIN_SET_SIZE = 20
GENESIS_HASH = "0" * 64
FORCE_SEAL_DELAY = timedelta(minutes=60)


def _chain_tip() -> str:
    last = db.session.query(Ballot).order_by(Ballot.id.desc()).first()
    return last.hash if last else GENESIS_HASH


def flush_pending(division: str, min_size: int = MIN_SET_SIZE, force: bool = False) -> int:
    """Seal every pending ballot of a division if there are at least `min_size` (or `force`).

    Returns how many ballots were sealed. Does not commit: the caller owns the transaction
    (the submit route commits once, after the vote and the seal).
    """
    pending = db.session.query(PendingBallot).filter_by(division=division).all()
    if not pending or (len(pending) < min_size and not force):
        return 0

    secrets.SystemRandom().shuffle(pending)
    batch_id = uuid.uuid4().hex
    prev_hash = _chain_tip()
    for row in pending:
        row_hash = chain_hash(prev_hash, row.blob)
        db.session.add(Ballot(division=division, blob=row.blob, prev_hash=prev_hash,
                              hash=row_hash, batch_id=batch_id))
        db.session.delete(row)
        prev_hash = row_hash
    db.session.flush()
    return len(pending)


def force_seal_after_close(now: datetime | None = None) -> int:
    """Seal every remaining pending ballot once WINDOW_CLOSE + 60 minutes has passed."""
    now = now or datetime.utcnow()
    close = datetime.fromisoformat(current_app.config["WINDOW_CLOSE"])
    if now < close + FORCE_SEAL_DELAY:
        return 0
    divisions = [d for (d,) in db.session.query(PendingBallot.division).distinct()]
    sealed = sum(flush_pending(d, force=True) for d in divisions)
    db.session.commit()
    return sealed


def sealed_ballots(division: str) -> list[Ballot]:
    """The ONLY source counting may read: sealed ballots, never the pending buffer."""
    return db.session.query(Ballot).filter_by(division=division).order_by(Ballot.id).all()
