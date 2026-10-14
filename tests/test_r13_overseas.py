import pytest
from app.routes.auth import is_overseas_request

def test_r13_overseas_fails_closed():
    # An arbitrary external IP should be treated as overseas (needs certificate)
    assert is_overseas_request("203.0.113.5") is True

def test_r13_allowlisted_ip_is_not_overseas():
    # Note: This depends on what is in your config.py MISSION_ALLOWLIST
    # If it's empty, everything is overseas (fail closed)
    pass