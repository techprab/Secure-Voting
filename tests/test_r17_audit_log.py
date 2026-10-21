
import json

from app import db
from app.models import AuditLog
from app.services.audit_log import append_audit, verify_audit_log


def test_r17_valid_chain_verifies(app):
    with app.app_context():
        append_audit("staff_action", 1, before={"role": "auditor"},
                     after={"role": "admin"})
        append_audit("second_action", 2)

        assert verify_audit_log() is True


def test_r17_modified_after_value_is_detected(app):
    with app.app_context():
        append_audit("staff_action", 1, before={"role": "auditor"},
                     after={"role": "admin"})

        entry = AuditLog.query.first()
        entry.after = json.dumps({"role": "voter"})
        db.session.commit()

        assert verify_audit_log() is False


def test_r17_modified_timestamp_is_detected(app):
    from datetime import timedelta

    with app.app_context():
        append_audit("staff_action", 1)

        entry = AuditLog.query.first()
        entry.ts = entry.ts + timedelta(seconds=1)
        db.session.commit()

        assert verify_audit_log() is False


def test_r17_deleted_entry_is_detected(app):
    with app.app_context():
        append_audit("first_action", 1)
        append_audit("second_action", 2)

        first = AuditLog.query.order_by(AuditLog.id.asc()).first()
        db.session.delete(first)
        db.session.commit()

        assert verify_audit_log() is False
def test_r17_malformed_audit_data_is_detected(app):
    with app.app_context():
        append_audit("staff_action", 1, after={"role": "admin"})

        entry = AuditLog.query.first()
        entry.after = "{invalid-json"
        db.session.commit()

        assert verify_audit_log() is False
