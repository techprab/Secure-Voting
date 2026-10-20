"""R-21: a candidate exclusion needs two different delegates within 15 minutes."""
from datetime import timedelta

import app.routes.count as count_routes
from app import db
from app.models import AuditLog, Candidate, ExclusionRequest
from app.services.audit_log import verify_audit_log

DELEGATE_1, DELEGATE_2, DELEGATE_3 = 101, 102, 103


def _request(client, auth, staff_token, candidate_id, staff_id=DELEGATE_1):
    return client.post("/exclusions",
                       json={"candidate_id": candidate_id, "court_ref": "CDR-2026-14"},
                       headers=auth(staff_token("delegate", staff_id=staff_id)))


def test_r21_single_approval_not_applied(client, candidates, staff_token, auth):
    a, _, _ = candidates
    resp = _request(client, auth, staff_token, a)

    assert resp.status_code == 201
    assert resp.get_json()["status"] == "pending"
    assert db.session.get(Candidate, a).excluded is False
    assert db.session.get(ExclusionRequest, resp.get_json()["id"]).applied is False


def test_r21_two_delegates_apply_exclusion(client, candidates, staff_token, auth):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]

    resp = client.post(f"/exclusions/{req_id}/approve",
                       headers=auth(staff_token("delegate", staff_id=DELEGATE_2)))

    assert resp.status_code == 200
    db.session.expire_all()
    req = db.session.get(ExclusionRequest, req_id)
    assert (req.approver_1, req.approver_2, req.applied) == (DELEGATE_1, DELEGATE_2, True)
    assert db.session.get(Candidate, a).excluded is True


def test_r21_same_delegate_twice_403(client, candidates, staff_token, auth):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]

    resp = client.post(f"/exclusions/{req_id}/approve",
                       headers=auth(staff_token("delegate", staff_id=DELEGATE_1)))

    assert resp.status_code == 403
    db.session.expire_all()
    assert db.session.get(Candidate, a).excluded is False


def test_r21_after_15_minutes_rejected(client, candidates, staff_token, auth, monkeypatch):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]
    created = db.session.get(ExclusionRequest, req_id).created_at
    monkeypatch.setattr(count_routes, "_now", lambda: created + timedelta(minutes=15, seconds=1))

    resp = client.post(f"/exclusions/{req_id}/approve",
                       headers=auth(staff_token("delegate", staff_id=DELEGATE_2)))

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "expired"
    db.session.expire_all()
    assert db.session.get(Candidate, a).excluded is False


def test_r21_applied_request_cannot_be_approved_again(client, candidates, staff_token, auth):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]
    client.post(f"/exclusions/{req_id}/approve",
                headers=auth(staff_token("delegate", staff_id=DELEGATE_2)))

    resp = client.post(f"/exclusions/{req_id}/approve",
                       headers=auth(staff_token("delegate", staff_id=DELEGATE_3)))
    assert resp.status_code == 409


def test_r21_only_delegates_can_request_or_approve(client, candidates, staff_token, auth):
    a, _, _ = candidates
    officer = auth(staff_token("officer"))
    assert client.post("/exclusions", json={"candidate_id": a, "court_ref": "x"},
                       headers=officer).status_code == 403
    req_id = _request(client, auth, staff_token, a).get_json()["id"]
    assert client.post(f"/exclusions/{req_id}/approve", headers=officer).status_code == 403


def test_r21_bad_input_rejected(client, candidates, staff_token, auth):
    headers = auth(staff_token("delegate", staff_id=DELEGATE_1))
    assert client.post("/exclusions", json={"candidate_id": "1", "court_ref": "x"},
                       headers=headers).status_code == 400
    assert client.post("/exclusions", json={"candidate_id": 9999, "court_ref": "x"},
                       headers=headers).status_code == 404


def test_r21_both_steps_in_audit_log(client, candidates, staff_token, auth):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]
    client.post(f"/exclusions/{req_id}/approve",
                headers=auth(staff_token("delegate", staff_id=DELEGATE_2)))

    db.session.expire_all()
    entries = {e.action: e for e in AuditLog.query.all()}
    assert entries["exclusion_request"].actor_id == DELEGATE_1
    assert entries["exclusion_approve"].actor_id == DELEGATE_2
    assert verify_audit_log() is True


def test_r21_rejected_approval_not_logged_as_success(client, candidates, staff_token, auth):
    a, _, _ = candidates
    req_id = _request(client, auth, staff_token, a).get_json()["id"]
    client.post(f"/exclusions/{req_id}/approve",
                headers=auth(staff_token("delegate", staff_id=DELEGATE_1)))

    db.session.expire_all()
    assert AuditLog.query.filter_by(action="exclusion_approve").count() == 0


def test_r21_request_and_audit_survive_the_request(tmp_path):
    """The in-memory test DB shares one connection, so it cannot show a missing commit.
    A file database can: the request and its audit entry must still be there afterwards."""
    from datetime import date

    from flask_jwt_extended import create_access_token

    from app import create_app
    from app.config import TestConfig
    from app.models import Staff

    class FileConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'r21.db'}"

    file_app = create_app(FileConfig)
    with file_app.app_context():
        db.create_all()
        db.session.add(Staff(id=DELEGATE_1, username="d1", role="delegate", password_hash="x",
                             totp_secret="x", recertified_until=date.today() + timedelta(days=30)))
        db.session.add(Candidate(id=1, division="File Division", name="Alpha", position="1"))
        db.session.commit()
        token = create_access_token(identity=str(DELEGATE_1),
                                    additional_claims={"type": "staff", "role": "delegate", "mfa": True})

    resp = file_app.test_client().post("/exclusions", json={"candidate_id": 1, "court_ref": "CDR-1"},
                                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201

    with file_app.app_context():
        assert ExclusionRequest.query.count() == 1
        assert [e.action for e in AuditLog.query.all()] == ["exclusion_request"]
        db.drop_all()
