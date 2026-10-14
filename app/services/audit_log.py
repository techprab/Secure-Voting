"""STUBS owned by Riya (Slice C)."""
def append_audit(action: str, actor_id: int | None = None, before=None, after=None) -> None:
    # STUB: append a hash-chained AuditLog row; never log ballot selections.
    pass

def verify_audit_log() -> bool:
    # STUB: recompute and verify the audit chain.
    return True
