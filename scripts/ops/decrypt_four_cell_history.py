#!/usr/bin/env python3
"""Decode only the independent fixed-four history format into a new0600 private artifact."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
MAX_ENVELOPE = 8 * 1024 * 1024 * 4 // 3 + 4096


def validator():
    spec = importlib.util.spec_from_file_location(
        "four_cell_history_scope", Path(__file__).with_name("four_cell_history_scope.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decrypt_snapshot(encoded, private_key_bytes):
    if len(encoded) > MAX_ENVELOPE:
        raise ValueError("four_cell_history_envelope_too_large")
    envelope = json.loads(encoded)
    metadata = {key: envelope[key] for key in ("format", "cipher", "key_sha256")}
    if set(envelope) != {*metadata, "nonce", "wrapped_key", "ciphertext"} or metadata != {
        "format": "wcu-workload-envelope/1",
        "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
        "key_sha256": KEY_FINGERPRINT,
    }:
        raise ValueError("four_cell_history_envelope_metadata_invalid")
    private = serialization.load_pem_private_key(private_key_bytes, password=None)
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 3072:
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
    if len(plaintext) > validator().MAX_BYTES:
        raise ValueError("four_cell_history_plaintext_too_large")
    payload = json.loads(plaintext)
    validator().validate(payload)
    return payload


def write_new_snapshot(payload, directory):
    validator().validate(payload)
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("existing_private_output_directory_required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = directory / f"wcu-four-cell-history-{stamp}-{uuid.uuid4().hex[:12]}.json"
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        payload = decrypt_snapshot(Path(args.input).read_bytes(), Path(args.private_key).read_bytes())
        output = write_new_snapshot(payload, args.output_dir)
    except Exception:
        print("four_cell_history_decode_refused", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
