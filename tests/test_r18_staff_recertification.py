
from datetime import date, timedelta
import uuid
from app.security.staff_guard import require_staff
from app import db, models


def test_admin_can_recertify_staff(app, client, staff_token):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=30),
        )
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add_all([admin, target])
        db.session.commit()

        admin_id = admin.id
        target_id = target.id

        token = staff_token(role="admin", mfa=True, staff_id=admin_id)

    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    with app.app_context():
        renewed = db.session.get(models.Staff, target_id)
        assert renewed.recertified_until == date.today() + timedelta(days=90)


def test_non_admin_cannot_recertify_staff(app, client, staff_token):
    with app.app_context():
        officer = models.Staff(
            username=f"officer-{uuid.uuid4().hex[:8]}",
            role="officer",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=90),
        )
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add_all([officer, target])
        db.session.commit()
        officer_id, target_id = officer.id, target.id
        token = staff_token(role="officer", mfa=True, staff_id=officer_id)

    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_recertify_unknown_staff_returns_404(app, client, staff_token):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=90),
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        token = staff_token(role="admin", mfa=True, staff_id=admin_id)

    response = client.post(
        "/staff/999999/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_expired_admin_cannot_recertify_staff(app, client, staff_token):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() - timedelta(days=1),
        )
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id, target_id = admin.id, target.id
        token = staff_token(role="admin", mfa=True, staff_id=admin_id)

    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_voter_token_cannot_recertify_staff(app, client, staff_token, voter_token):
    with app.app_context():
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    token = voter_token(1)
    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_admin_without_recertification_cannot_renew(app, client, staff_token):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=None,
        )
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id, target_id = admin.id, target.id
        token = staff_token(role="admin", mfa=True, staff_id=admin_id)

    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403

def test_r18_admin_cannot_recertify_self(app, client, staff_token):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=30),
        )
        db.session.add(admin)
        db.session.commit()

        admin_id = admin.id
        token = staff_token(role="admin", mfa=True, staff_id=admin_id)

    response = client.post(
        f"/staff/{admin_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "self_recertification_not_allowed"

    with app.app_context():
        unchanged_admin = db.session.get(models.Staff, admin_id)
        assert unchanged_admin.recertified_until == date.today() + timedelta(days=30)


def test_r18_rejects_token_when_database_role_changes(
    app, client, staff_token
):
    from flask import jsonify
    from app.security.staff_guard import require_staff

    @app.get("/test-r18-role-guard")
    @require_staff("delegate")
    def test_r18_role_guard():
        return jsonify(ok=True)

    with app.app_context():
        delegate = models.Staff(
            username=f"delegate-{uuid.uuid4().hex[:8]}",
            role="delegate",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=30),
        )
        db.session.add(delegate)
        db.session.commit()

        delegate_id = delegate.id
        token = staff_token(
            role="delegate", mfa=True, staff_id=delegate_id
        )

        delegate.role = "auditor"
        db.session.commit()

    response = client.get(
        "/test-r18-role-guard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_r18_admin_without_mfa_cannot_recertify(
    app, client, staff_token
):
    with app.app_context():
        admin = models.Staff(
            username=f"admin-{uuid.uuid4().hex[:8]}",
            role="admin",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=30),
        )
        target = models.Staff(
            username=f"target-{uuid.uuid4().hex[:8]}",
            role="auditor",
            password_hash="unused",
            totp_secret="unused",
            recertified_until=date.today() + timedelta(days=5),
        )
        db.session.add_all([admin, target])
        db.session.commit()

        admin_id = admin.id
        target_id = target.id
        token = staff_token(role="admin", mfa=False, staff_id=admin_id)

    response = client.post(
        f"/staff/{target_id}/recertify",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
