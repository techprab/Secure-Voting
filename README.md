# INTE2667 A3 — Secure Voting Prototype

Group assignment 3 for INTE2667 Secure Software Systems (RMIT, Semester 2 2026).
A functional prototype of the **Vote Casting** subsystem of the Electronic Voting Platform, with a thin count-and-publish slice, implementing 21 security requirements merged from the members' Assignment 1 work.

## Team

| Member | Slice |
| --- | --- |
| Dev | A · Voter access |
| Jaewook | B · Ballot & anonymity |
| Riya | C · Staff & audit |
| Daksh | D · Crypto & pipeline |
| Prabh | E · Count & publish |

## Stack

Python 3.12 · Flask · Flask-SQLAlchemy (SQLite) · Flask-JWT-Extended · bcrypt · cryptography (AES-256-GCM, ECDSA P-384) · pyotp · Flask-Limiter · pytest · GitHub Actions · Docker

## Docs

- [Security requirements](docs/requirements.md) — the 21 requirements, priority, complexity
- [Interfaces & conventions](docs/interfaces.md) — function contract, data model, repo layout, git rules

## Run (once the skeleton is merged)

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py
flask --app run run --cert=adhoc
pytest -q
```

## Working rules

One branch and one pull request per requirement issue; commit messages start with the requirement ID (`R-07: ...`); every security mechanism merges together with its test.
