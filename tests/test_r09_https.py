def test_http_rejected_when_https_required():
    from app import create_app
    from app.config import TestConfig

    class HTTPSRequiredConfig(TestConfig):
        REQUIRE_HTTPS = True
        TESTING = False
        DEBUG = False

    app = create_app(HTTPSRequiredConfig)
    response = app.test_client().get(
        "/health",
        base_url="http://localhost",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "https_required"}


def test_hsts_header_present_when_https_required():
    from app import create_app
    from app.config import TestConfig

    class HTTPSRequiredConfig(TestConfig):
        REQUIRE_HTTPS = True

    app = create_app(HTTPSRequiredConfig)
    response = app.test_client().get(
        "/health",
        base_url="https://localhost",
    )

    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_http_allowed_when_https_not_required(app):
    response = app.test_client().get(
        "/health",
        base_url="http://localhost",
    )

    assert response.status_code == 200