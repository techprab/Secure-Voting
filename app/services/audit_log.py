"""Append and verify a tamper-evident audit log."""
import hashlib
import json
from datetime import datetime, timezone

from .. import db
from ..models import AuditLog

GENESIS_HASH = "0" * 64


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _entry_payload(actor_id, action, before, after, ts) -> str:
    return _canonical_json([
        actor_id, action, before, after, ts.isoformat()
    ])


def append_audit(
    action: str,
    actor_id: int | None = None,
    before=None,
    after=None,
) -> None:
    """Append an audit entry without committing the caller's transaction."""
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")

    before_json = None if before is None else _canonical_json(before)
    after_json = None if after is None else _canonical_json(after)

    previous = AuditLog.query.order_by(AuditLog.id.desc()).first()
    previous_hash = previous.hash if previous else GENESIS_HASH
    timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    payload = _entry_payload(
        actor_id, action, before, after, timestamp
    )
    entry_hash = hashlib.sha256(
        (previous_hash + payload).encode("utf-8")
    ).hexdigest()

    db.session.add(AuditLog(
        actor_id=actor_id,
        action=action,
        before=before_json,
        after=after_json,
        ts=timestamp,
        prev_hash=previous_hash,
        hash=entry_hash,
    ))

    # Leave commit and rollback to the caller.
    db.session.flush()


def verify_audit_log_details() -> dict:
    """Return validity and the first invalid entry ID, if any."""
    previous_hash = GENESIS_HASH
    entries = AuditLog.query.order_by(AuditLog.id.asc()).all()

    for entry in entries:
        if entry.prev_hash != previous_hash:
            return {"ok": False, "first_bad_id": entry.id}

        try:
            before = None if entry.before is None else json.loads(entry.before)
            after = None if entry.after is None else json.loads(entry.after)
            payload = _entry_payload(
                entry.actor_id, entry.action, before, after, entry.ts
            )
            expected_hash = hashlib.sha256(
                (previous_hash + payload).encode("utf-8")
            ).hexdigest()
        except (TypeError, ValueError, AttributeError):
            return {"ok": False, "first_bad_id": entry.id}

        if entry.hash != expected_hash:
            return {"ok": False, "first_bad_id": entry.id}

        previous_hash = entry.hash

    return {"ok": True, "first_bad_id": None}


def verify_audit_log() -> bool:
    """Compatibility interface for existing callers."""
    return verify_audit_log_details()["ok"]
