
def test_gui_response_has_security_headers(client):
    response = client.get("/")

    assert response.status_code == 200

    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
