"""R-13 application tests; WSGI certificate verification is simulated."""
import bcrypt
import pytest
from flask_jwt_extended import create_access_token

from app import db
from app.models import Voter
from app.security.voter_guard import require_voter

FP = "ab" * 32


@pytest.fixture()
def mission_setup(app):
    app.config.update(
        MISSION_ALLOWLIST="203.0.113.0/24, 2001:db8::/32",
        MISSION_CERTS=FP + "," + "cd" * 32,
        WINDOW_CLOSE="2099-01-01T00:00:00+00:00",
    )

    @app.get("/_test/mission")
    @require_voter
    def probe():
        return {"ok": True}, 200

    voter = Voter(
        name="mission-voter", division="Test Division",
        eligible=True, overseas=True,
        password_hash=bcrypt.hashpw(
            b"test-password", bcrypt.gensalt(rounds=4)
        ).decode(),
    )
    db.session.add(voter)
    db.session.commit()
    return voter.id


def trusted_env(ip="203.0.113.9", cert=FP):
    return {
        "REMOTE_ADDR": ip,
        "SSL_CLIENT_VERIFY": "SUCCESS",
        "SSL_CLIENT_FINGERPRINT_SHA256": cert,
    }


def login(client, env=None, headers=None):
    return client.post(
        "/auth/login",
        json={"username": "mission-voter", "password": "test-password"},
        environ_overrides=env or {},
        headers=headers or {},
    )


@pytest.mark.parametrize("ip", ["203.0.113.9", "2001:db8::9"])
def test_r13_approved_ip_and_verified_certificate_allowed(
    client, mission_setup, ip
):
    assert login(client, trusted_env(ip)).status_code == 200


@pytest.mark.parametrize("ip", ["203.0.113.90", "203.0.113.100"])
def test_r13_exact_cidr_boundaries(client, app, mission_setup, ip):
    app.config["MISSION_ALLOWLIST"] = "203.0.113.8/29"
    assert login(client, trusted_env(ip)).status_code == 403


def test_r13_unknown_ip_denied(client, mission_setup):
    assert login(client, trusted_env("198.51.100.9")).status_code == 403


@pytest.mark.parametrize("cert", ["ab", "ef" * 32])
def test_r13_partial_or_unknown_fingerprint_denied(
    client, mission_setup, cert
):
    assert login(client, trusted_env(cert=cert)).status_code == 403


def test_r13_spoofed_headers_do_not_authenticate(client, mission_setup):
    response = login(
        client,
        {"REMOTE_ADDR": "203.0.113.9"},
        {
            "X-Client-Cert": FP,
            "X-Mission-Cert": FP,
            "SSL-Client-Verify": "SUCCESS",
            "SSL-Client-Fingerprint-SHA256": FP,
        },
    )
    assert response.status_code == 403


def test_r13_unverified_certificate_denied(client, mission_setup):
    env = trusted_env()
    env["SSL_CLIENT_VERIFY"] = "FAILED"
    assert login(client, env).status_code == 403


@pytest.mark.parametrize("setting,value", [
    ("MISSION_ALLOWLIST", ""),
    ("MISSION_ALLOWLIST", None),
    ("MISSION_ALLOWLIST", "not-a-network"),
    ("MISSION_CERTS", ""),
    ("MISSION_CERTS", None),
    ("MISSION_CERTS", "not-a-fingerprint"),
])
def test_r13_bad_configuration_denies(
    client, app, mission_setup, setting, value
):
    app.config[setting] = value
    assert login(client, trusted_env()).status_code == 403


def test_r13_domestic_account_unaffected(client, mission_setup):
    db.session.get(Voter, mission_setup).overseas = False
    db.session.commit()
    assert login(client).status_code == 200


def test_r13_overseas_loopback_has_no_bypass(client, mission_setup):
    assert login(client).status_code == 403


def test_r13_existing_token_still_requires_mission_checks(
    client, mission_setup
):
    token = create_access_token(
        identity=str(mission_setup),
        additional_claims={"type": "voter", "division": "Test Division"},
    )
    headers = {"Authorization": "Bearer " + token}
    denied = client.get(
        "/_test/mission", headers=headers,
        environ_overrides={"REMOTE_ADDR": "203.0.113.9"},
    )
    assert denied.status_code == 403
    allowed = client.get(
        "/_test/mission", headers=headers,
        environ_overrides=trusted_env(),
    )
    assert allowed.status_code == 200
