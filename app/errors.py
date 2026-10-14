from flask import jsonify

class ReplayError(Exception):
    pass

class AlreadyVotedError(Exception):
    pass

class DefinitionMismatch(Exception):
    pass

class ReleaseBlocked(Exception):
    pass

def register_error_handlers(app):
    mappings = [
        (ReplayError, 409, "replay"),
        (AlreadyVotedError, 409, "already_voted"),
        (DefinitionMismatch, 503, "ballot_definition_mismatch"),
        (ReleaseBlocked, 409, "release_blocked"),
    ]
    for exc_type, status, code in mappings:
        app.register_error_handler(
            exc_type,
            lambda exc, status=status, code=code: (jsonify(error=code), status)
        )

    @app.errorhandler(401)
    def unauthorized(_exc):
        return jsonify(error="unauthorized"), 401

    @app.errorhandler(403)
    def forbidden(_exc):
        return jsonify(error="forbidden"), 403
