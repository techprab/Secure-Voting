import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-me-too")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///secure_voting.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BALLOT_KEY = os.getenv("BALLOT_KEY", "")
    RESULT_SIGNING_KEY = os.getenv("RESULT_SIGNING_KEY", "")
    WINDOW_CLOSE = os.getenv("WINDOW_CLOSE", "2099-01-01T00:00:00")
    REQUIRE_HTTPS = os.getenv("REQUIRE_HTTPS", "true").lower() == "true"
    MISSION_ALLOWLIST = os.getenv("MISSION_ALLOWLIST", "")
    MISSION_CERTS = os.getenv("MISSION_CERTS", "")
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"
    REQUIRE_HTTPS = False
    RATELIMIT_ENABLED = False
