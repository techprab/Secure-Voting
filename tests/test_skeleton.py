import pytest

def test_health_endpoint(client):
    response = client.get('/health')
    assert response.status_code == 200

# Note: test_registered_route_stubs_return_501 has been removed.
# It was a skeleton test to verify that routes return 501 (Not Implemented).
# Now that /auth/login is fully implemented, this test is obsolete.