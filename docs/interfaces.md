# Interfaces & conventions


The contract every slice codes against. The skeleton ships each function below as a stub with this exact signature; the owner replaces the stub body, never the signature. Change a signature only with the consumers' agreement.

## Who delivers what to whom

| From | To | Delivers |
| --- | --- | --- |
| Dev (A) | Jaewook (B) | `require_voter`, `consume_nonce`, `begin_single_cast` |
| Riya (C) | Jaewook (B) | `require_staff('auditor')` |
| Riya (C) | Prabh (E) | `require_staff('delegate' / 'officer')`, MFA claim, `@audited` |
| Daksh (D) | Jaewook (B) | `seal_ballot`, `chain_hash`, `verify_chain` |
| Daksh (D) | Prabh (E) | `open_ballot`, `verify_chain` |
| Jaewook (B) | Prabh (E) | `sealed_ballots` |

Only two things block work outright: the repo (Jaewook, Sun 11) and the skeleton merge (Daksh, Wed 14). Everything else starts as a stub and is swapped for real code at integration on Mon 19.

## Repo layout

```
Secure-Voting/
├── app/
│   ├── __init__.py        # create_app(), db, jwt, limiter, blueprints, error handlers
│   ├── config.py          # Config (.env) and TestConfig (in-memory SQLite, fixed keys)
│   ├── errors.py          # ReplayError, AlreadyVotedError, DefinitionMismatch -> JSON + status
│   ├── models/            # voter.py, ballot.py, staff.py, audit.py, count.py
│   ├── security/          # voter_guard.py (A), staff_guard.py (C), crypto.py (D)
│   ├── services/          # ballots.py, ballot_def.py (B), count.py (E), audit_log.py (C)
│   └── routes/            # auth.py (A), ballot.py (B), staff.py (C), audit.py (B+C), count.py (E)
├── tests/                 # conftest.py + test_rNN_<name>.py, one file per requirement
├── seed.py
├── run.py
├── Dockerfile
├── requirements.txt
└── .github/workflows/ci.yml
```

## Function contract

```python
# app/security/voter_guard.py — owner A (Dev)
def require_voter(fn): ...
    # route decorator: valid, unexpired voter JWT -> g.voter; else 401
def consume_nonce(nonce: str) -> None: ...
    # R-04: records nonce; raises ReplayError (409, {"error":"replay"}) if seen before
def begin_single_cast(voter_id: int) -> str: ...
    # R-01: adds Participation(voter_id) in the current transaction, returns a participation code;
    # raises AlreadyVotedError (409, {"error":"already_voted"})

# app/security/staff_guard.py — owner C (Riya)
def require_staff(*roles: str, mfa: bool = True): ...
    # decorator: staff JWT, role in roles, recertified_until >= today, mfa claim if mfa=True -> g.staff
def audited(action: str): ...
    # decorator: after a successful route, appends AuditLog(actor, action, g.audit_before, g.audit_after)

# app/security/crypto.py — owner D (Daksh)
def seal_ballot(preferences: list[int]) -> bytes: ...   # R-14: AES-256-GCM, returns nonce + ciphertext + tag
def open_ballot(blob: bytes) -> list[int]: ...          # R-14: decrypt; raises on a failed tag
def chain_hash(prev_hash: str, blob: bytes) -> str: ... # R-10: sha256(prev_hash + blob) hex; genesis '0' * 64
def verify_chain() -> bool: ...                         # R-10: recompute every Ballot.hash in id order

# app/services/ballots.py — owner B (Jaewook)
def sealed_ballots(division: str) -> list[Ballot]: ...  # the ONLY source counting may read
```

**Stub behaviour in the skeleton:** `seal_ballot` / `open_ballot` = plain JSON bytes; `verify_chain` returns True; `require_voter` / `require_staff` check token type and role only; `audited` and `consume_nonce` do nothing; `begin_single_cast` inserts the row and returns a random code. Every stub carries `# STUB — owner X replaces`.

## Data model

```python
Voter(id, name, division, eligible: bool, overseas: bool, password_hash)
Participation(id, voter_id UNIQUE, code, voted_hour: 'YYYY-MM-DD HH')    # no ballot reference
PendingBallot(id, division, blob)                                         # no voter reference
Ballot(id, division, blob, prev_hash, hash, batch_id)                     # no voter, no timestamp
Candidate(id, division, name, position, excluded: bool)
CandidateSetApproval(id, division, set_hash, approved_by, approved_at)
Staff(id, username, role, password_hash, totp_secret, recertified_until)  # role: admin|delegate|auditor|officer
AuditLog(id, actor_id, action, before, after, ts, prev_hash, hash)
UsedNonce(nonce PRIMARY KEY)
ExclusionRequest(id, candidate_id, court_ref, approver_1, approver_2, created_at, applied: bool)
ResultRelease(id, division, payload, signature, released_at)
CountCache(division, candidate_id, votes)                                 # display only; R-12 test poisons it
```

**Seed (`python seed.py`):** 2 divisions, 3 candidates each with an approved set, 60 voters (5 overseas), one staff account per role (TOTP secrets printed), 20 sealed ballots per division so slice E can start on day 1.

## Git and testing rules

| Rule | Example |
| --- | --- |
| One branch per issue | `R-07-confirm-submit` |
| Commit message starts with the requirement | `R-07: add preview endpoint` |
| PR title + closes the issue | `R-07 Confirm before commit` · `Closes #7` |
| Merge to `main` only via PR, 1 reviewer, CI green | branch protection on `main` |
| One test file per requirement | `tests/test_r07_confirm.py` |
| Test names say the rule | `test_r07_submit_without_confirm_400` |

```
pip install -r requirements.txt
python seed.py
flask --app run run --cert=adhoc     # https in dev
pytest -q
```

`requirements.txt`: Flask, Flask-SQLAlchemy, Flask-JWT-Extended, bcrypt, cryptography, pyotp, Flask-Limiter, pyOpenSSL, pytest, pip-audit — pinned versions.
