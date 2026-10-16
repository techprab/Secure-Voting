"""R-07  Explicit confirmation before commit; the receipt proves participation only.
Source: Jaewook SR-07 + Daksh R-04 + Prabh SR-06 · Slice B · Issue #8

POST /ballot/preview {preferences}            -> 200 {summary, preview_token}  (token: 5 min, voter-bound,
                                                  holds sha256(preferences) only)
POST /ballot/submit {preferences, preview_token, confirm: true, nonce}
                                              -> 201 {"participation_code": "..."} and nothing else
GET /participation/<code>                     -> 200 {"voted": true} | 404
"""
import uuid
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from app import models


def _submit(client, auth, voter_id, **body):
    return client.post("/ballot/submit", json=body, headers=auth(voter_id=voter_id))


@pytest.mark.parametrize("confirm", [False, None, "yes", 1])
def test_r07_submit_without_confirm_400(division, cast, counts, confirm):
    r = cast(division["voters"][0], division["candidates"], body={"confirm": confirm})
    assert r.status_code == 400
    assert r.get_json() == {"error": "confirmation_required"}
    assert counts()["participation"] == 0


def test_r07_submit_without_preview_token_400(division, client, auth, counts):
    r = _submit(client, auth, division["voters"][0], preferences=division["candidates"],
                confirm=True, nonce=str(uuid.uuid4()))
    assert r.status_code == 400
    assert counts()["participation"] == 0


def test_r07_preferences_changed_after_preview_400(division, preview, client, auth, counts):
    voter, prefs = division["voters"][0], division["candidates"]
    token = preview(voter, prefs).get_json()["preview_token"]
    r = _submit(client, auth, voter, preferences=list(reversed(prefs)), preview_token=token,
                confirm=True, nonce=str(uuid.uuid4()))
    assert r.status_code == 400
    assert r.get_json() == {"error": "preview_mismatch"}
    assert counts()["participation"] == 0


def test_r07_preview_token_bound_to_voter(division, preview, client, auth, counts):
    prefs = division["candidates"]
    token = preview(division["voters"][0], prefs).get_json()["preview_token"]
    r = _submit(client, auth, division["voters"][1], preferences=prefs, preview_token=token,
                confirm=True, nonce=str(uuid.uuid4()))
    assert r.status_code == 400
    assert counts()["participation"] == 0


def test_r07_expired_preview_token_400(division, client, auth, counts):
    from app.routes.ballot import PREVIEW_TOKEN_TYPE, preferences_hash

    voter, prefs = division["voters"][0], division["candidates"]
    expired = create_access_token(
        identity=str(voter),
        additional_claims={"type": PREVIEW_TOKEN_TYPE, "division": division["name"],
                           "pref_hash": preferences_hash(prefs)},
        expires_delta=timedelta(seconds=-1),
    )
    r = _submit(client, auth, voter, preferences=prefs, preview_token=expired,
                confirm=True, nonce=str(uuid.uuid4()))
    assert r.status_code == 400
    assert r.get_json() == {"error": "invalid_preview_token"}
    assert counts()["participation"] == 0


def test_r07_preview_token_is_not_a_voter_session(division, preview, client):
    token = preview(division["voters"][0], division["candidates"]).get_json()["preview_token"]
    r = client.get("/ballot", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (401, 403)


def test_r07_preview_returns_summary_and_writes_nothing(division, preview, counts):
    r = preview(division["voters"][0], division["candidates"])
    assert r.status_code == 200
    body = r.get_json()
    assert body["preview_token"]
    assert [row["name"] for row in body["summary"]] == ["Alpha", "Bravo", "Charlie"]
    assert counts() == {"pending": 0, "sealed": 0, "participation": 0}


@pytest.mark.parametrize("bad", ["duplicate", "missing", "unknown", "empty", "not_int"])
def test_r07_preview_rejects_invalid_ranking(division, preview, bad):
    a, b, c = division["candidates"]
    prefs = {"duplicate": [a, a, b], "missing": [a, b], "unknown": [a, b, 999999],
             "empty": [], "not_int": [str(a), b, c]}[bad]
    r = preview(division["voters"][0], prefs)
    assert r.status_code == 400
    assert r.get_json() == {"error": "invalid_ranking"}


def test_r07_invalid_nonce_400(division, cast, counts):
    r = cast(division["voters"][0], division["candidates"], body={"nonce": "not-a-uuid"})
    assert r.status_code == 400
    assert counts()["participation"] == 0


def test_r07_submit_returns_only_the_participation_code(division, cast, counts):
    r = cast(division["voters"][0], division["candidates"])
    assert r.status_code == 201
    assert set(r.get_json()) == {"participation_code"}
    assert counts() == {"pending": 1, "sealed": 0, "participation": 1}


def test_r07_code_lookup_never_returns_preferences(division, cast, client):
    code = cast(division["voters"][0], division["candidates"]).get_json()["participation_code"]
    r = client.get(f"/participation/{code}")
    assert r.status_code == 200
    assert r.get_json() == {"voted": True}


def test_r07_unknown_code_404(division, client):
    assert client.get("/participation/not-a-real-code").status_code == 404


def test_r07_participation_row_has_no_ballot_reference():
    columns = {c.name for c in models.Participation.__table__.columns}
    assert columns == {"id", "voter_id", "code", "voted_hour"}


def test_r07_pending_ballot_has_no_voter_reference():
    columns = {c.name for c in models.PendingBallot.__table__.columns}
    assert columns == {"id", "division", "blob"}
    assert not models.PendingBallot.__table__.foreign_keys
