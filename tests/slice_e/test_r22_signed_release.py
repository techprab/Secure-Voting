"""R-22: results are released only as an ECDSA P-384 signed payload with a published public key."""
import base64
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import db
from app.models import AuditLog, ResultRelease

DIVISION = "Division E"  # same value as tests/slice_e/conftest.py


def _release(client, auth, staff_token, mfa=True):
    return client.post(f"/results/release/{DIVISION}",
                       headers=auth(staff_token("officer", mfa=mfa)))


def test_r22_signature_verifies(client, candidates, add_ballots, staff_token, auth, signing_key):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3 + [[b, c, a]])

    body = _release(client, auth, staff_token).get_json()
    assert json.loads(body["payload"])["totals"] == {str(a): 3, str(b): 1, str(c): 0}

    # An external consumer verifies with only the public key, without calling the app.
    pem = client.get("/results/public-key").get_json()["public_key"]
    public_key = serialization.load_pem_public_key(pem.encode())
    public_key.verify(base64.b64decode(body["signature"]),
                      body["payload"].encode(), ec.ECDSA(hashes.SHA384()))

    check = client.post("/results/verify",
                        json={"payload": body["payload"], "signature": body["signature"]})
    assert check.get_json() == {"valid": True}


def test_r22_altered_payload_invalid(client, candidates, add_ballots, staff_token, auth, signing_key):
    a, b, c = candidates
    add_ballots([[a, b, c]] * 3)
    body = _release(client, auth, staff_token).get_json()

    forged = json.loads(body["payload"])
    forged["totals"][str(b)] = 1000
    forged_payload = json.dumps(forged, sort_keys=True, separators=(",", ":"))

    check = client.post("/results/verify",
                        json={"payload": forged_payload, "signature": body["signature"]})
    assert check.get_json() == {"valid": False}
    with pytest.raises(InvalidSignature):
        signing_key.public_key().verify(base64.b64decode(body["signature"]),
                                        forged_payload.encode(), ec.ECDSA(hashes.SHA384()))


def test_r22_garbage_signature_invalid(client, signing_key):
    check = client.post("/results/verify", json={"payload": "{}", "signature": "not-base64!"})
    assert check.get_json() == {"valid": False}


def test_r22_release_without_mfa_403(client, candidates, add_ballots, staff_token, auth, signing_key):
    a, b, c = candidates
    add_ballots([[a, b, c]])

    assert _release(client, auth, staff_token, mfa=False).status_code == 403
    assert ResultRelease.query.count() == 0


def test_r22_release_stored_audited_and_published(client, candidates, add_ballots,
                                                 staff_token, auth, signing_key):
    a, b, c = candidates
    add_ballots([[c, a, b]] * 2)
    body = _release(client, auth, staff_token).get_json()

    db.session.expire_all()
    stored = ResultRelease.query.one()
    assert (stored.payload, stored.signature) == (body["payload"], body["signature"])
    assert AuditLog.query.filter_by(action="result_release").count() == 1

    latest = client.get(f"/results/{DIVISION}/latest").get_json()
    assert latest["signature"] == body["signature"]


def test_r22_no_signing_key_no_release(client, app, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c]])
    app.config["RESULT_SIGNING_KEY"] = ""

    assert _release(client, auth, staff_token).status_code == 503
    assert ResultRelease.query.count() == 0


def test_r22_wrong_curve_key_refused(client, app, candidates, add_ballots, staff_token, auth):
    a, b, c = candidates
    add_ballots([[a, b, c]])
    weak = ec.generate_private_key(ec.SECP256R1())
    app.config["RESULT_SIGNING_KEY"] = weak.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()

    assert _release(client, auth, staff_token).status_code == 503
