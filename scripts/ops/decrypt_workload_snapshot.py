#!/usr/bin/env python3
"""Locally decrypt an authenticated workload envelope into a new0600JSON file.

No database connection. Private key content and decrypted records are never logged.
"""

import argparse
import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"


def decrypt_snapshot(encoded, private_key_bytes):
    if len(encoded) > 128 * 1024 * 1024:
        raise ValueError("envelope_too_large")
    envelope = json.loads(encoded)
    metadata = {k: envelope[k] for k in ("format", "cipher", "key_sha256")}
    if metadata != {
        "format": "wcu-workload-envelope/1",
        "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
        "key_sha256": KEY_FINGERPRINT,
    }:
        raise ValueError("envelope_metadata_invalid")
    private = serialization.load_pem_private_key(private_key_bytes, password=None)
    if not isinstance(private, rsa.RSAPrivateKey):
        raise ValueError("rsa_private_key_required")
    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != KEY_FINGERPRINT:
        raise ValueError("private_key_fingerprint_mismatch")
    key = private.decrypt(
        base64.b64decode(envelope["wrapped_key"], validate=True),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(envelope["nonce"], validate=True),
        base64.b64decode(envelope["ciphertext"], validate=True),
        json.dumps(metadata, sort_keys=True).encode(),
    )
    payload = json.loads(plaintext)
    if (
        payload.get("format") != "wcu-workload-snapshot/1"
        or payload.get("organization_id") != ORG
        or payload.get("academic_year") != "2026/2027"
    ):
        raise ValueError("snapshot_scope_invalid")
    return payload


def write_new_snapshot(payload, directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("existing_private_output_directory_required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = directory / f"wcu-workload-{stamp}-{uuid.uuid4().hex[:12]}.json"
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    payload = decrypt_snapshot(Path(args.input).read_bytes(), Path(args.private_key).read_bytes())
    print(write_new_snapshot(payload, args.output_dir))


if __name__ == "__main__":
    main()
