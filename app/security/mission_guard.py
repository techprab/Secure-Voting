"""R-13 application boundary; requires a trusted TLS server adapter.

The adapter must verify the client certificate and set these WSGI values:
    SSL_CLIENT_VERIFY = SUCCESS
    SSL_CLIENT_FINGERPRINT_SHA256 = verified certificate SHA-256 fingerprint

Never populate them from unverified HTTP headers. Direct backend access
must be prevented when deploying behind a proxy. This module does not
configure TLS or determine the physical location of domestic accounts.
"""
from ipaddress import ip_address, ip_network
import re

from flask import current_app, request


def config_items(value):
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("Invalid mission configuration")
        return [item.strip() for item in value]
    raise ValueError("Missing mission configuration")


def fingerprint(value):
    if not isinstance(value, str):
        raise ValueError("Missing certificate fingerprint")
    value = value.strip().replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid SHA-256 fingerprint")
    return value


def mission_access_allowed(voter):
    # Prototype scope: overseas status comes from the server-side voter record.
    if not voter.overseas:
        return True

    try:
        networks = [
            ip_network(item, strict=False)
            for item in config_items(current_app.config.get("MISSION_ALLOWLIST"))
        ]
        approved = {
            fingerprint(item)
            for item in config_items(current_app.config.get("MISSION_CERTS"))
        }
        if not networks or not approved:
            return False

        address = ip_address(request.remote_addr)
        if not any(address in network for network in networks):
            return False

        # These are server-provided WSGI values, not request.headers.
        if request.environ.get("SSL_CLIENT_VERIFY") != "SUCCESS":
            return False
        presented = fingerprint(
            request.environ.get("SSL_CLIENT_FINGERPRINT_SHA256")
        )
        return presented in approved
    except (TypeError, ValueError):
        return False
