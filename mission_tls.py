"""Local R-13 mTLS demonstration server; not a production deployment."""
import argparse
import hashlib
import ssl

from werkzeug.serving import WSGIRequestHandler, make_server


def server_context(cert, key, ca):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    context.load_verify_locations(cafile=str(ca))
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class MissionRequestHandler(WSGIRequestHandler):
    def make_environ(self):
        environ = super().make_environ()
        # Populate trusted metadata only from the verified TLS connection.
        environ.pop("SSL_CLIENT_VERIFY", None)
        environ.pop("SSL_CLIENT_FINGERPRINT_SHA256", None)

        if (
            isinstance(self.connection, ssl.SSLSocket)
            and self.connection.context.verify_mode == ssl.CERT_REQUIRED
        ):
            certificate = self.connection.getpeercert(binary_form=True)
            if certificate:
                environ["SSL_CLIENT_VERIFY"] = "SUCCESS"
                environ["SSL_CLIENT_FINGERPRINT_SHA256"] = (
                    hashlib.sha256(certificate).hexdigest()
                )
        return environ


def make_mission_server(app, cert, key, ca, port=8443):
    # Direct TLS: no separate plaintext backend or forwarded-header trust.
    return make_server(
        "127.0.0.1", port, app,
        threaded=True,
        ssl_context=server_context(cert, key, ca),
        request_handler=MissionRequestHandler,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()

    from app import create_app
    app = create_app()
    app.config["REQUIRE_HTTPS"] = True
    server = make_mission_server(
        app, args.cert, args.key, args.ca, args.port
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
