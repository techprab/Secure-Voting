# Interfaces & conventions

The contract every slice codes against. The skeleton ships each function below as a stub with this exact signature; the owner replaces the stub body, never the signature. Change a signature only with the consumers' agreement, in a PR that edits this file.

**This file is the source of truth.** If a personal guide disagrees with it, this file wins.

## Who delivers what to whom

| From | To | Delivers |
| --- | --- | --- |
| Dev (A) | Jaewook (B) | `require_voter`, `consume_nonce`, `begin_single_cast` |
| Riya (C) | Jaewook (B) | `require_staff('auditor' / 'delegate')`, `@audited`, `append_audit` |
| Riya (C) | Prabh (E) | `require_staff('delegate' / 'officer')`, MFA claim, `@audited` |
| Riya (C) | Dev (A) | `append_audit` (replay is logged as a system event) |
| Daksh (D) | Jaewook (B) | `seal_ballot`, `chain_hash`, `verify_chain` |
| Daksh (D) | Prabh (E) | `open_ballot`, `verify_chain` |
| Jaewook (B) | Prabh (E) | `sealed_ballots` |

The only hard blocker left is the skeleton merge (Daksh). Everything else starts as a stub and is swapped for real code at integration on Mon 19.

## Repo layout and file ownership

One owner per file, so two people never edit the same file in parallel. The skeleton creates every file below and registers every blueprint, so nobody needs to touch `app/__init__.py` afterwards except Daksh.

```
Secure-Voting/
├── app/
│   ├── __init__.py          # D  create_app(), db, jwt, limiter, all blueprints, error handlers
│   ├── config.py            # D  Config (.env) and TestConfig
│   ├── errors.py            # D  exception classes -> JSON + status (see Errors)
│   ├── models/              # D  writes them in the skeleton; later changes by PR with Jaewook's review
│   ├── security/
│   │   ├── voter_guard.py   # A
│   │   ├── staff_guard.py   # C
│   │   └── crypto.py        # D
│   ├── services/
│   │   ├── ballots.py       # B  flush_pending, sealed_ballots
│   │   ├── ballot_def.py    # B  candidate_set_hash
│   │   ├── audit_log.py     # C  append_audit, verify_audit_log
│   │   └── count.py         # E  count_a, count_b, release_check
│   └── routes/
│       ├── auth.py          # A  /auth/login
│       ├── ballot.py        # B  /ballot, /ballot/preview, /ballot/submit, /participation/<code>
│       ├── candidates.py    # B  /staff/candidates/approve
│       ├── staff.py         # C  /staff/login, /staff/mfa, /staff/<id>/recertify
│       ├── audit_ballots.py # B  /audit/ballots/verify
│       ├── audit_log.py     # C  /audit/log/verify
│       └── count.py         # E  /count/recount, /exclusions, /results/*
├── tests/                   # conftest.py (D) + test_rNN_<name>.py, one file per requirement (its owner)
├── seed.py                  # D
├── run.py
├── Dockerfile
├── requirements.txt
└── .github/workflows/ci.yml
```

## Function contract

```python
# app/security/voter_guard.py — owner A (Dev)
def require_voter(fn): ...
    # route decorator: valid, unexpired voter JWT -> g.voter; else 401.
    # On success it puts a fresh 15-minute token in the X-Session-Token response header (sliding expiry).
def consume_nonce(nonce: str) -> None: ...
    # R-04: records nonce; raises ReplayError if seen before (and logs a system audit event).
    # The nonce is a client-generated UUID sent in the submit body: {"nonce": "..."}
def begin_single_cast(voter_id: int) -> str: ...
    # R-01: adds Participation(voter_id) in the current transaction, returns a participation code;
    # raises AlreadyVotedError

# app/security/staff_guard.py — owner C (Riya)
def require_staff(*roles: str, mfa: bool = True): ...
    # decorator: staff JWT, role in roles, recertified_until >= today, mfa claim if mfa=True -> g.staff
def audited(action: str): ...
    # decorator: after a successful route, calls append_audit(action, g.staff.id, g.audit_before, g.audit_after)

# app/services/audit_log.py — owner C (Riya)
def append_audit(action: str, actor_id: int | None = None, before=None, after=None) -> None: ...
    # R-17: appends one hash-chained AuditLog row. actor_id=None means a system event
    # (e.g. R-04 replay, R-06 ballot-definition mismatch). Never pass ballot selections.

# app/security/crypto.py — owner D (Daksh)
def seal_ballot(preferences: list[int]) -> bytes: ...   # R-14: AES-256-GCM, returns nonce + ciphertext + tag
def open_ballot(blob: bytes) -> list[int]: ...          # R-14: decrypt; raises on a failed tag
def chain_hash(prev_hash: str, blob: bytes) -> str: ... # R-10: sha256(prev_hash + blob) hex; genesis '0' * 64
def verify_chain() -> bool: ...                         # R-10: recompute every Ballot.hash in id order

# app/services/ballots.py — owner B (Jaewook)
def sealed_ballots(division: str) -> list[Ballot]: ...  # the ONLY source counting may read
```

**Stub behaviour in the skeleton:** `seal_ballot` / `open_ballot` = plain JSON bytes; `chain_hash` real (it is one line); `verify_chain` returns True; `require_voter` / `require_staff` check token type and role only; `audited`, `append_audit` and `consume_nonce` do nothing; `begin_single_cast` inserts the row and returns a random code. Every stub carries `# STUB — owner X replaces`.

## Tokens

| Token | `identity` | Extra claims | Issued by |
| --- | --- | --- | --- |
| Voter | `Voter.id` | `type: "voter"`, `division` | `POST /auth/login` (A) |
| Staff, password only | `Staff.id` | `type: "staff"`, `role`, `mfa: false` (5 min) | `POST /staff/login` (C) |
| Staff, after TOTP | `Staff.id` | `type: "staff"`, `role`, `mfa: true` | `POST /staff/mfa` (C) |

Tests get tokens from the `voter_token(voter_id)` and `staff_token(role, mfa=True)` fixtures in `tests/conftest.py`.

## Errors

All errors return JSON `{"error": "<code>"}` with the status below. Raise the exception; the handler in `app/errors.py` formats it.

| Exception | Status | `error` | Raised by |
| --- | --- | --- | --- |
| `ReplayError` | 409 | `replay` | A · R-04 |
| `AlreadyVotedError` | 409 | `already_voted` | A · R-01 |
| `DefinitionMismatch` | 503 | `ballot_definition_mismatch` | B · R-06 |
| `ReleaseBlocked` | 409 | `release_blocked` | E · R-19 |
| Flask-Limiter | 429 | `rate_limited` | A · R-20 |
| auth failures | 401 / 403 | `unauthorized` / `forbidden` | A, C |

## Config keys (`.env`, read in `app/config.py`)

| Key | Used by | Notes |
| --- | --- | --- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | all | random, never committed |
| `BALLOT_KEY` | D · R-14 | 32 bytes, base64 |
| `RESULT_SIGNING_KEY` | E · R-22 | ECDSA P-384 private key, PEM |
| `WINDOW_CLOSE` | A · R-03, B · R-02 | ISO datetime; ballots force-seal 60 min after |
| `REQUIRE_HTTPS` | D · R-09 | `True` in Config, `False` in TestConfig unless a test sets it |
| `MISSION_ALLOWLIST`, `MISSION_CERTS` | A · R-13 | CIDR list; approved certificate fingerprints |
| `RATELIMIT_ENABLED` | A · R-20 | `False` in TestConfig; R-20 tests switch it on |

`.env` is git-ignored. The skeleton commits a `.env.example` with placeholder values.

## Data model

```python
Voter(id, name, division, eligible: bool, overseas: bool, password_hash)
Participation(id, voter_id UNIQUE, code, voted_hour: 'YYYY-MM-DD HH')    # no ballot reference
PendingBallot(id, division, blob)                                         # no voter reference
Ballot(id, division, blob, prev_hash, hash, batch_id)                     # no voter, no timestamp
Candidate(id, division, name, position, excluded: bool)                   # excluded is NOT in the R-06 hash
CandidateSetApproval(id, division, set_hash, approved_by, approved_at)
Staff(id, username, role, password_hash, totp_secret, recertified_until)  # role: admin|delegate|auditor|officer
AuditLog(id, actor_id NULL = system, action, before, after, ts, prev_hash, hash)
UsedNonce(nonce PRIMARY KEY)
ExclusionRequest(id, candidate_id, court_ref, approver_1, approver_2, created_at, applied: bool)
ResultRelease(id, division, payload, signature, released_at)
CountCache(division, candidate_id, votes)                                 # display only; R-12 test poisons it
```

**Seed (`python seed.py`):** 2 divisions, 3 candidates each with an approved set, 60 voters (5 overseas), one staff account per role (TOTP secrets printed), 20 sealed ballots per division so slice E can start on day 1. Seed always builds ballots through `seal_ballot` and `chain_hash`, so **re-run it after the real R-14 crypto merges**, or old plain-JSON ballots will not decrypt.

## Git and testing rules

| Rule | Example |
| --- | --- |
| One branch per issue | `R-07-confirm-submit` |
| Commit message starts with the requirement | `R-07: add preview endpoint` |
| PR title + closes the issue | `R-07 Confirm before commit` · `Closes #7` |
| Merge to `main` only via PR, 1 reviewer, CI green | branch protection on `main` (or team rule until it can be enforced) |
| Only touch files you own; anything else goes through its owner | see Repo layout |
| One test file per requirement | `tests/test_r07_confirm.py` |
| Test names say the rule | `test_r07_submit_without_confirm_400` |
| Never commit `.env`, keys or databases | `.gitignore` blocks them |

```
pip install -r requirements.txt
cp .env.example .env      # then fill in keys
python seed.py
flask --app run run --cert=adhoc     # https in dev
pytest -q
```

`requirements.txt`: Flask, Flask-SQLAlchemy, Flask-JWT-Extended, bcrypt, cryptography, pyotp, Flask-Limiter, pyOpenSSL, pytest, pip-audit — Daksh pins versions after `pip-audit` passes.
