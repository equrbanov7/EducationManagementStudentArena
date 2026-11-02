"""Local operator-only decoding; credentials written0600, never printed."""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
COUNTS = {"staff-seven": 7, "magistr-two": 2, "behruz-one": 1}


def decode(encoded, private_bytes):
    if len(encoded) > 65536:
        raise ValueError("targeted_envelope_size")
    envelope = json.loads(encoded)
    metadata = {k: envelope[k] for k in ("format", "cipher", "key_sha256")}
    if metadata != dict(format="wcu-workload-envelope/1", cipher="AES-256-GCM+RSA-OAEP-SHA256", key_sha256=FINGERPRINT):
        raise ValueError("targeted_envelope_metadata")
    private = serialization.load_pem_private_key(private_bytes, password=None)
    if not isinstance(private, rsa.RSAPrivateKey):
        raise ValueError("targeted_key_required")
    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != FINGERPRINT:
        raise ValueError("targeted_key_pin")
    key = private.decrypt(
        base64.b64decode(envelope["wrapped_key"], validate=True),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    payload = json.loads(
        AESGCM(key).decrypt(
            base64.b64decode(envelope["nonce"], validate=True),
            base64.b64decode(envelope["ciphertext"], validate=True),
            json.dumps(metadata, sort_keys=True).encode(),
        )
    )
    if (
        set(payload) != {"format", "batch", "baseline", "csv"}
        or payload["format"] != "wcu-targeted-credentials/1"
        or payload["batch"] not in COUNTS
    ):
        raise ValueError("targeted_payload_required")
    rows = list(csv.reader(io.StringIO(payload["csv"])))
    if (
        not rows
        or rows[0] != ["ad_soyad_ata_adi", "username", "ilkin_parol"]
        or len(rows) > COUNTS[payload["batch"]] + 1
        or any(len(row) != 3 for row in rows)
    ):
        raise ValueError("targeted_csv_required")
    return payload["csv"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        content = decode(Path(args.input).read_bytes(), Path(args.private_key).read_bytes())
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(content)
    except Exception:
        print("targeted_credentials_decode_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
