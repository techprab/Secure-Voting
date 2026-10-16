"""R-06  A ballot is served only from the last approved candidate set.
Source: Jaewook SR-08 · Slice B · Issue #7
"""
import pytest

from app import db
from app import models

DIV = "TEST-DIV"
MISMATCH = {"error": "ballot_definition_mismatch"}


@pytest.fixture
def get_ballot(client, auth):
    def _get(voter_id):
        return client.get("/ballot", headers=auth(voter_id=voter_id))
    return _get


def _edit_candidate(candidate_id, **changes):
    row = db.session.get(models.Candidate, candidate_id)
    for field, value in changes.items():
        setattr(row, field, value)
    db.session.commit()


def test_r06_serves_when_hash_matches(division, get_ballot):
    r = get_ballot(division["voters"][0])
    assert r.status_code == 200
    assert [c["name"] for c in r.get_json()["candidates"]] == ["Alpha", "Bravo", "Charlie"]


def test_r06_refuses_after_candidate_row_changed(division, get_ballot):
    _edit_candidate(division["candidates"][1], name="Bravo (edited)")
    r = get_ballot(division["voters"][0])
    assert r.status_code == 503
    assert r.get_json() == MISMATCH


def test_r06_refuses_after_positions_swapped(division, get_ballot):
    first, second = division["candidates"][:2]
    _edit_candidate(first, position="2")
    _edit_candidate(second, position="1")
    assert get_ballot(division["voters"][0]).status_code == 503


def test_r06_refuses_when_candidate_added(division, get_ballot):
    db.session.add(models.Candidate(division=DIV, name="Delta", position="4", excluded=False))
    db.session.commit()
    assert get_ballot(division["voters"][0]).status_code == 503


def test_r06_refuses_when_no_approval_exists(division, get_ballot):
    models.CandidateSetApproval.query.filter_by(division=DIV).delete()
    db.session.commit()
    assert get_ballot(division["voters"][0]).status_code == 503


def test_r06_excluded_flag_does_not_change_the_hash(division, get_ballot):
    from app.services.ballot_def import candidate_set_hash

    before = candidate_set_hash(DIV)
    _edit_candidate(division["candidates"][2], excluded=True)
    assert candidate_set_hash(DIV) == before
    assert get_ballot(division["voters"][0]).status_code == 200


def test_r06_mismatch_writes_system_audit_event(division, get_ballot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.ballot_def.append_audit",
        lambda action, actor_id=None, before=None, after=None: calls.append((action, actor_id)),
    )
    _edit_candidate(division["candidates"][1], name="Bravo (edited)")
    get_ballot(division["voters"][0])
    assert calls == [("ballot_definition_mismatch", None)]


def test_r06_delegate_reapproval_restores_service(division, get_ballot, client, auth):
    _edit_candidate(division["candidates"][1], name="Bravo (edited)")
    assert get_ballot(division["voters"][0]).status_code == 503

    r = client.post("/staff/candidates/approve", json={"division": DIV}, headers=auth(role="delegate"))
    assert r.status_code == 201
    assert get_ballot(division["voters"][0]).status_code == 200


@pytest.mark.parametrize("role", ["auditor", "officer", "admin"])
def test_r06_only_delegate_can_approve(division, client, auth, role):
    r = client.post("/staff/candidates/approve", json={"division": DIV}, headers=auth(role=role))
    assert r.status_code == 403


def test_r06_approve_unknown_division_404(division, client, auth):
    r = client.post("/staff/candidates/approve", json={"division": "NO-SUCH-DIV"}, headers=auth(role="delegate"))
    assert r.status_code == 404


def test_r06_ineligible_voter_403(division, get_ballot):
    voter_id = division["voters"][0]
    db.session.get(models.Voter, voter_id).eligible = False
    db.session.commit()
    assert get_ballot(voter_id).status_code == 403


def test_r06_submit_refused_on_mismatch(division, preview, client, auth, counts):
    voter, prefs = division["voters"][0], division["candidates"]
    token = preview(voter, prefs).get_json()["preview_token"]

    _edit_candidate(division["candidates"][0], name="Alpha (edited)")
    r = client.post("/ballot/submit", headers=auth(voter_id=voter), json={
        "preferences": prefs, "preview_token": token, "confirm": True,
        "nonce": "6f1c2a52-3a43-4d6b-9a52-3f0f5f0c1a11"})
    assert r.status_code == 503
    assert r.get_json() == MISMATCH
    assert counts() == {"pending": 0, "sealed": 0, "participation": 0}
