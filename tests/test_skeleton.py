def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"

def test_registered_route_stubs_return_501(client):
    response = client.post("/auth/login", json={})
    assert response.status_code == 501
    assert response.get_json()["error"] == "not_implemented"
