
from datetime import date, timedelta

from app import db
from app.models import AuditLog, Staff
from app.services.audit_log import append_audit


def create_staff(app, staff_id=1, role="auditor"):
    with app.app_context():
        staff = Staff(
            id=staff_id,
            username=f"r17_staff_{staff_id}",
            role=role,
            password_hash="test-password-hash",
            totp_secret="JBSWY3DPEHPK3PXP",
            recertified_until=date.today() + timedelta(days=30),
        )
        db.session.add(staff)
        db.session.commit()


def test_r17_verify_requires_authentication(client):
    response = client.get("/audit/log/verify")
    assert response.status_code == 401


def test_r17_verify_rejects_voter_token(client, voter_token):
    response = client.get(
        "/audit/log/verify",
        headers={"Authorization": f"Bearer {voter_token()}"},
    )
    assert response.status_code == 401


def test_r17_verify_rejects_staff_without_mfa(
    app, client, staff_token
):
    create_staff(app, staff_id=1, role="auditor")
    token = staff_token(role="auditor", mfa=False, staff_id=1)

    response = client.get(
        "/audit/log/verify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_r17_verify_returns_valid_chain(
    app, client, staff_token
):
    create_staff(app, staff_id=1, role="auditor")

    with app.app_context():
        append_audit("test_action", actor_id=1)

    token = staff_token(role="auditor", mfa=True, staff_id=1)
    response = client.get(
        "/audit/log/verify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "first_bad_id": None,
    }


def test_r17_verify_reports_first_tampered_entry(
    app, client, staff_token
):
    create_staff(app, staff_id=1, role="auditor")

    with app.app_context():
        append_audit("first_action", actor_id=1)
        append_audit("second_action", actor_id=2)

        first = AuditLog.query.order_by(AuditLog.id.asc()).first()
        first.after = '{"tampered":true}'
        first_id = first.id
        db.session.commit()

    token = staff_token(role="auditor", mfa=True, staff_id=1)
    response = client.get(
        "/audit/log/verify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": False,
        "first_bad_id": first_id,
    }