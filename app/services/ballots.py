"""R-02: ballots leave the pending buffer only in sets of 20 or more.

Owner: Jaewook (Slice B).

Submitted ballots wait in PendingBallot. Once a division has at least 20, the whole set is
shuffled and moved to the sealed Ballot store together, so the order and time of sealing
cannot be matched to the order and time of individual submissions.
After the voting window closes, a smaller remainder is sealed by force (WINDOW_CLOSE + 60 min).

Concurrency: reading the chain tip and committing the new rows happen under one lock
(commit_with_seal, force_seal_after_close). Without it, two requests could read the same tip
and fork the chain, or seal the same pending rows twice. The lock covers one server process,
which is how the prototype runs; several processes would also need a database guard
(for example UNIQUE on Ballot.prev_hash).
"""
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app

from .. import db
from ..models import Ballot, PendingBallot
from ..security.crypto import chain_hash

MIN_SET_SIZE = 20
GENESIS_HASH = "0" * 64
FORCE_SEAL_DELAY = timedelta(minutes=60)

_rng = secrets.SystemRandom()
_seal_lock = threading.Lock()


def _chain_tip() -> str:
    last = db.session.query(Ballot).order_by(Ballot.id.desc()).first()
    return last.hash if last else GENESIS_HASH


def flush_pending(division: str, min_size: int = MIN_SET_SIZE, force: bool = False) -> int:
    """Seal every pending ballot of a division if there are at least `min_size` (or `force`).

    Returns how many ballots were sealed. Does not commit and does not lock:
    call it through commit_with_seal or force_seal_after_close.
    """
    pending = db.session.query(PendingBallot).filter_by(division=division).all()
    if not pending or (len(pending) < min_size and not force):
        return 0

    _rng.shuffle(pending)
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


def commit_with_seal(division: str) -> int:
    """Seal the division's set if it is due, then commit the whole transaction.

    Used by the submit route, so the vote and the seal are committed together, or not at all.
    """
    with _seal_lock:
        try:
            sealed = flush_pending(division)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return sealed


def window_close_utc() -> datetime:
    """WINDOW_CLOSE as an aware UTC datetime. A value without a timezone is read as UTC
    (same rule as R-03). An invalid value raises ValueError, so nothing is sealed by force."""
    value = current_app.config.get("WINDOW_CLOSE")
    close = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if close.tzinfo is None:
        close = close.replace(tzinfo=timezone.utc)
    return close.astimezone(timezone.utc)


def force_seal_after_close(now: datetime | None = None) -> int:
    """Seal every remaining pending ballot once WINDOW_CLOSE + 60 minutes has passed."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now < window_close_utc() + FORCE_SEAL_DELAY:
        return 0
    with _seal_lock:
        try:
            divisions = [d for (d,) in db.session.query(PendingBallot.division).distinct()]
            sealed = sum(flush_pending(d, force=True) for d in divisions)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return sealed


def sealed_ballots(division: str) -> list[Ballot]:
    """The ONLY source counting may read: sealed ballots, never the pending buffer."""
    return db.session.query(Ballot).filter_by(division=division).order_by(Ballot.id).all()
