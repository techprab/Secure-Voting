from unittest.mock import patch

from flask import g, jsonify

from app.security.staff_guard import audited


def test_r05_candidate_edit_logged_with_before_after(app, client):
    @app.post("/test-r05-edit")
    @audited("edit_candidate")
    def edit_candidate():
        g.staff = type("StaffContext", (), {"id": "123"})()
        g.audit_before = {"name": "Old Candidate"}
        g.audit_after = {"name": "New Candidate"}
        return jsonify(success=True), 200

    with patch("app.security.staff_guard.append_audit") as mock_audit:
        response = client.post("/test-r05-edit")

    assert response.status_code == 200
    mock_audit.assert_called_once_with(
        "edit_candidate",
        "123",
        before={"name": "Old Candidate"},
        after={"name": "New Candidate"},
    )


def test_r05_actor_is_the_authenticated_staff(app, client):
    @app.post("/test-r05-actor")
    @audited("staff_action")
    def staff_action():
        g.staff = type("StaffContext", (), {"id": "456"})()
        return jsonify(success=True), 200

    with patch("app.security.staff_guard.append_audit") as mock_audit:
        response = client.post("/test-r05-actor")

    assert response.status_code == 200
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[1] == "456"


def test_r05_failed_action_not_logged_as_success(app, client):
    @app.post("/test-r05-failure")
    @audited("edit_candidate")
    def failed_action():
        g.staff = type("StaffContext", (), {"id": "123"})()
        return jsonify(error="bad_request"), 400

    with patch("app.security.staff_guard.append_audit") as mock_audit:
        response = client.post("/test-r05-failure")

    assert response.status_code == 400
    mock_audit.assert_not_called()