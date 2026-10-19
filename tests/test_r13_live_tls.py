"""Real loopback HTTPS tests with temporary certificates and database."""
import hashlib
import http.client
import ipaddress
import json
import ssl
import threading
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app import create_app, db
from app.config import TestConfig
from app.models import Voter
from app.security.voter_guard import require_voter
from mission_tls import make_mission_server


def issue_certificate(folder, name, issuer=None, purpose=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer[1].subject if issuer else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.BasicConstraints(ca=issuer is None, path_length=None),
            critical=True,
        )
    )
    if purpose:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([purpose]), critical=False
        )
    if purpose == ExtendedKeyUsageOID.SERVER_AUTH:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
    certificate = builder.sign(
        issuer[0] if issuer else key, hashes.SHA256()
    )
    cert_path = folder / (name + ".pem")
    key_path = folder / (name + ".key")
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.touch(mode=0o600)
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return key, certificate, cert_path, key_path


@pytest.fixture()
def live_mission(tmp_path):
    ca = issue_certificate(tmp_path, "test-ca")
    server_cert = issue_certificate(
        tmp_path, "server", ca, ExtendedKeyUsageOID.SERVER_AUTH
    )
    approved = issue_certificate(
        tmp_path, "approved", ca, ExtendedKeyUsageOID.CLIENT_AUTH
    )
    unapproved = issue_certificate(
        tmp_path, "unapproved", ca, ExtendedKeyUsageOID.CLIENT_AUTH
    )
    rogue_ca = issue_certificate(tmp_path, "rogue-ca")
    rogue = issue_certificate(
        tmp_path, "rogue", rogue_ca, ExtendedKeyUsageOID.CLIENT_AUTH
    )
    fingerprint = hashlib.sha256(
        approved[1].public_bytes(serialization.Encoding.DER)
    ).hexdigest()

    class LiveConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(tmp_path / "test.db")
        JWT_SECRET_KEY = "r13-live-test-key-only-" + "x" * 32
        WINDOW_CLOSE = "2099-01-01T00:00:00+00:00"
        MISSION_ALLOWLIST = "127.0.0.1/32"
        MISSION_CERTS = fingerprint
        REQUIRE_HTTPS = True
        RATELIMIT_ENABLED = False

    app = create_app(LiveConfig)

    @app.get("/_test/mission")
    @require_voter
    def protected_probe():
        return {"ok": True}

    with app.app_context():
        db.create_all()
        db.session.add(Voter(
            name="tls-voter", division="Test Division",
            overseas=True, eligible=True,
            password_hash=bcrypt.hashpw(
                b"test-password", bcrypt.gensalt(rounds=4)
            ).decode(),
        ))
        db.session.commit()

    server = make_mission_server(
        app, server_cert[2], server_cert[3], ca[2], port=0
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(client="approved", path="/auth/login", headers=None):
        context = ssl.create_default_context(cafile=str(ca[2]))
        identities = {
            "approved": approved, "unapproved": unapproved, "rogue": rogue
        }
        if client is not None:
            identity = identities[client]
            context.load_cert_chain(str(identity[2]), str(identity[3]))
        connection = http.client.HTTPSConnection(
            "127.0.0.1", server.server_port, context=context, timeout=5
        )
        try:
            if path == "/auth/login":
                body = json.dumps({
                    "username": "tls-voter", "password": "test-password"
                })
                connection.request(
                    "POST", path, body,
                    {"Content-Type": "application/json", **(headers or {})},
                )
            else:
                connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        yield app, request, fingerprint
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_live_tls_approved_certificate_login_and_protected_route(live_mission):
    app, request, fingerprint = live_mission
    status, body = request()
    assert status == 200
    status, body = request(
        path="/_test/mission",
        headers={"Authorization": "Bearer " + body["token"]},
    )
    assert status == 200
    assert body == {"ok": True}


@pytest.mark.parametrize("client", [None, "rogue"])
def test_live_tls_missing_or_untrusted_certificate_rejected(live_mission, client):
    app, request, fingerprint = live_mission
    with pytest.raises((
        ssl.SSLError, ConnectionResetError, BrokenPipeError,
        http.client.RemoteDisconnected,
    )):
        request(client=client)


def test_live_tls_trusted_but_unapproved_certificate_denied(live_mission):
    app, request, fingerprint = live_mission
    status, body = request(client="unapproved")
    assert status == 403
    assert body["error"] == "mission_access_denied"


def test_live_tls_spoofed_headers_cannot_replace_certificate(live_mission):
    app, request, fingerprint = live_mission
    status, body = request(client="unapproved", headers={
        "SSL-Client-Verify": "SUCCESS",
        "SSL-Client-Fingerprint-SHA256": fingerprint,
        "X-Client-Cert": fingerprint,
        "X-Forwarded-For": "203.0.113.9",
    })
    assert status == 403


def test_live_tls_approved_certificate_wrong_network_denied(live_mission):
    app, request, fingerprint = live_mission
    app.config["MISSION_ALLOWLIST"] = "203.0.113.0/24"
    status, body = request()
    assert status == 403
