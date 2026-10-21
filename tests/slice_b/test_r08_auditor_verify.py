"""R-08  An auditor verifies the ballot set without re-linking voters and ballots.
Source: Jaewook SR-09 + SR-11 + Daksh R-03 + Prabh SR-01 + Riya R5 · Slice B · Issue #9

GET /audit/ballots/verify  (auditor + MFA)
  200 {"chain_ok": bool,
       "divisions": {"<division>": {"sealed": n, "pending": n, "participation": n, "ok": bool}}}
"""
import pytest

from app import db
from app import models

DIV = "TEST-DIV"
FORBIDDEN_KEYS = {"voter", "voter_id", "voters", "code", "participation_code", "preferences",
                  "blob", "ballot", "ballots", "name", "candidate", "candidates", "batch_id", "hash"}


@pytest.fixture
def verify(client, auth):
    def _verify(role="auditor", mfa=True):
        return client.get("/audit/ballots/verify", headers=auth(role=role, mfa=mfa))
    return _verify


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _keys(item)


@pytest.mark.parametrize("role", ["delegate", "officer", "admin"])
def test_r08_non_auditor_403(division, verify, role):
    assert verify(role).status_code == 403


def test_r08_auditor_without_mfa_403(division, verify):
    assert verify(mfa=False).status_code == 403


def test_r08_voter_token_rejected(division, client, auth):
    r = client.get("/audit/ballots/verify", headers=auth(voter_id=division["voters"][0]))
    assert r.status_code in (401, 403)


def test_r08_counts_match_participation(division, cast, verify):
    for voter_id in division["voters"][:25]:
        assert cast(voter_id, division["candidates"]).status_code == 201
    r = verify()
    assert r.status_code == 200
    body = r.get_json()
    assert body["chain_ok"] is True
    assert body["divisions"][DIV] == {"sealed": 20, "pending": 5, "participation": 25, "ok": True}


def test_r08_missing_ballot_is_reported(division, cast, verify):
    for voter_id in division["voters"][:3]:
        cast(voter_id, division["candidates"])
    db.session.delete(db.session.query(models.PendingBallot).filter_by(division=DIV).first())
    db.session.commit()
    row = verify().get_json()["divisions"][DIV]
    assert row == {"sealed": 0, "pending": 2, "participation": 3, "ok": False}


def test_r08_extra_ballot_is_reported(division, cast, verify):
    cast(division["voters"][0], division["candidates"])
    db.session.add(models.PendingBallot(division=DIV, blob=b"injected"))
    db.session.commit()
    row = verify().get_json()["divisions"][DIV]
    assert row["pending"] == 2 and row["participation"] == 1 and row["ok"] is False


def test_r08_tampered_sealed_ballot_breaks_chain_ok(division, cast, verify):
    for voter_id in division["voters"][:20]:
        cast(voter_id, division["candidates"])
    assert verify().get_json()["chain_ok"] is True
    ballot = db.session.query(models.Ballot).filter_by(division=DIV).first()
    ballot.blob = ballot.blob[:-1] + bytes([ballot.blob[-1] ^ 1])
    db.session.commit()
    assert verify().get_json()["chain_ok"] is False


def test_r08_response_has_no_voter_or_ballot_data(division, cast, verify):
    codes = [cast(v, division["candidates"]).get_json()["participation_code"]
             for v in division["voters"][:21]]
    r = verify()
    assert r.status_code == 200
    assert FORBIDDEN_KEYS.isdisjoint(set(_keys(r.get_json())) - {DIV})
    text = r.get_data(as_text=True)
    for code in codes:
        assert code not in text
    for name in ("Alpha", "Bravo", "Charlie"):
        assert name not in text


def test_r08_no_shared_column_between_participation_and_ballots():
    participation = {c.name for c in models.Participation.__table__.columns}
    for table in (models.Ballot, models.PendingBallot):
        assert participation & {c.name for c in table.__table__.columns} == {"id"}
        assert not table.__table__.foreign_keys
