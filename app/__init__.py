from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .config import Config
from .errors import register_error_handlers

db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)

    # Register before the first database connection is opened.
    from .sqlite_transactions import configure_sqlite_transactions
    with app.app_context():
        configure_sqlite_transactions(db.engine)
    jwt.init_app(app)
    limiter.init_app(app)

    # Import models after db exists, so SQLAlchemy registers them.
    from . import models  # noqa: F401

    # Register every blueprint here. Feature owners replace route stubs in their own files.
    from .routes.auth import bp as auth_bp
    from .routes.ballot import bp as ballot_bp
    from .routes.candidates import bp as candidates_bp
    from .routes.staff import bp as staff_bp
    from .routes.audit_ballots import bp as audit_ballots_bp
    from .routes.audit_log import bp as audit_log_bp
    from .routes.count import bp as count_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ballot_bp)
    app.register_blueprint(candidates_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(audit_ballots_bp)
    app.register_blueprint(audit_log_bp)
    app.register_blueprint(count_bp)

    register_error_handlers(app)

    @app.get("/health")
    def health():
        return jsonify(status="ok", message="Secure Voting skeleton is running"), 200

    # STUB — R-09: production HTTPS enforcement/HSTS must be implemented and tested.
    @app.after_request
    def security_headers(response):
        if app.config.get("REQUIRE_HTTPS", False):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains"
            )
        return response

    return app
