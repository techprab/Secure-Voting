# R-13 local TLS verification

## Purpose
mission_tls.py provides a local demonstration of client-certificate
verification connected to the existing mission-access guard.

The server binds only to 127.0.0.1 and requires a trusted client
certificate for every connection. It derives the SHA-256 fingerprint
from the actual TLS peer certificate, not from HTTP headers.
The existing application guard checks the network and fingerprint
allowlists for voters marked overseas.

## Run the automated demonstration
From the repository root, with the virtual environment active:

    python -m pytest -v --tb=short tests/test_r13_live_tls.py

The tests generate temporary certificates and an isolated database.
No manual seed data or persistent certificate files are needed.

## Manual startup
Supply your own server certificate, private key and client CA file:

    python mission_tls.py --cert /path/server.pem --key /path/server.key --ca /path/client-ca.pem

The server listens on https://127.0.0.1:8443 by default.
Clients must trust the server certificate and present a certificate
signed by the configured client CA.

Configure MISSION_ALLOWLIST and MISSION_CERTS for the intended test
network and approved client-certificate SHA-256 fingerprints.
The manual server uses the normal application configuration/database.
It does not create users or initialize the database.

## Verified behaviour
Six live HTTPS tests cover:
- Approved certificate: login and protected request succeed.
- Missing client certificate: connection rejected.
- Untrusted client certificate: connection rejected.
- Trusted but unapproved certificate: overseas login denied.
- Spoofed verification headers: cannot replace the real certificate.
- Approved certificate outside the allowed network: login denied.

Local validation: six live TLS tests passed; full branch suite 93 passed.

## Limits and deployment assumptions
This is a Werkzeug development server, not a production deployment.
There is no separate plaintext backend in this launcher.
It does not prevent someone from independently starting run.py or
another application listener. A deployed system must prevent alternate
access paths that bypass its intended network and TLS controls.

The launcher requires certificates for all connections and is intended
as a separate mission-terminal demonstration, not the domestic public
voting endpoint.

The application still relies on the voter.overseas flag. It does not
geolocate domestic accounts or prove a terminal's physical location.
Certificate revocation and a production certificate-management process
are not implemented. Full R-13 completion is therefore not claimed.

Never commit generated private keys or real credentials.
