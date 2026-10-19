import pytest

from app import create_app, db, limiter
from app.config import TestConfig


class RateLimitConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"


@pytest.fixture()
def limited_client():
    app = create_app(RateLimitConfig)
    with app.app_context():
        db.create_all()
        limiter.reset()
        try:
            yield app.test_client()
        finally:
            limiter.reset()
            db.session.remove()
            db.drop_all()


def attempt(client, ip):
    return client.post(
        "/auth/login",
        json={},
        environ_overrides={"REMOTE_ADDR": ip},
    )


def test_r20_sixth_login_request_is_limited(limited_client):
    for _ in range(5):
        assert attempt(limited_client, "192.0.2.10").status_code == 400
    assert attempt(limited_client, "192.0.2.10").status_code == 429


def test_r20_other_ip_has_separate_limit(limited_client):
    for _ in range(5):
        assert attempt(limited_client, "192.0.2.10").status_code == 400
    assert attempt(limited_client, "192.0.2.10").status_code == 429
    assert attempt(limited_client, "192.0.2.11").status_code == 400
