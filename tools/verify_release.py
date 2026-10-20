"""R-22: verify a signed result release offline, using only the published public key.

Usage:
    python tools/verify_release.py public_key.pem release.json

release.json is the body of GET /results/<division>/latest (needs "payload" and "signature").
Exit code 0 = valid signature, 1 = invalid. This script never contacts the voting app.
"""
import base64
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def verify(public_pem: bytes, payload: str, signature_b64: str) -> bool:
    key = serialization.load_pem_public_key(public_pem)
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp384r1":
        raise ValueError("expected an ECDSA P-384 public key")
    try:
        key.verify(base64.b64decode(signature_b64, validate=True),
                   payload.encode("utf-8"), ec.ECDSA(hashes.SHA384()))
        return True
    except (InvalidSignature, ValueError):
        return False


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    with open(argv[1], "rb") as fh:
        public_pem = fh.read()
    with open(argv[2], encoding="utf-8") as fh:
        release = json.load(fh)
    ok = verify(public_pem, release["payload"], release["signature"])
    print("VALID" if ok else "INVALID")
    if ok:
        print(json.dumps(json.loads(release["payload"]), indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
