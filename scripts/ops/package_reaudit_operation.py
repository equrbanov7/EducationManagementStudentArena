"""Prepare an encrypted private operation bundle; never upload or dispatch implicitly."""

import argparse
import base64
import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

PLAN_LIMITS = {"cells": 256 * 1024 * 1024, "syllabi": 20_000_000, "structure": 1024 * 1024}


def private_read(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size > limit:
        raise ValueError("private_bounded_source_required")
    return path.read_bytes()


def package(*, operation, plan_path, key_path, output, authority_path=None, offering_ids=()):
    if operation not in PLAN_LIMITS:
        raise ValueError("fixed_operation_required")
    if output.exists() or output.is_symlink() or output.parent.stat().st_mode & 0o077:
        raise ValueError("new_private_output_required")
    plan = private_read(plan_path, PLAN_LIMITS[operation])
    if not plan:
        raise ValueError("nonempty_plan_required")
    authority = private_read(authority_path, 1024 * 1024) if authority_path else b""
    bundle = {
        "format": "reaudit-operation-bundle/2",
        "operation": operation,
        "offering_ids": list(offering_ids),
        "plan_encoding": "gzip",
    }
    for name, data in (("plan", plan), ("authority", authority)):
        bundle[name] = base64.b64encode(gzip.compress(data, mtime=0) if name == "plan" else data).decode()
        bundle[name + "_sha256"] = hashlib.sha256(data).hexdigest()
    raw = json.dumps(bundle, sort_keys=True).encode()
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("bundle_budget")
    env = os.environ.copy()
    env["STAFF_PLAN_KEY"] = private_read(key_path, 16384).decode().strip()
    if not env["STAFF_PLAN_KEY"]:
        raise ValueError("source_key_required")
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-md",
            "sha256",
            "-salt",
            "-pass",
            "env:STAFF_PLAN_KEY",
        ],
        input=gzip.compress(raw, mtime=0),
        env=env,
        capture_output=True,
        timeout=60,
    )
    if result.returncode or not 0 < len(result.stdout) <= 16 * 1024 * 1024:
        raise ValueError("encrypted_bundle_failed_or_too_large")
    # Verify round trip before making any asset available for publication.
    verified = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-md",
            "sha256",
            "-pass",
            "env:STAFF_PLAN_KEY",
        ],
        input=result.stdout,
        env=env,
        capture_output=True,
        timeout=60,
    )
    if verified.returncode or gzip.decompress(verified.stdout) != raw:
        raise ValueError("encrypted_bundle_roundtrip_failed")
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(result.stdout)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "operation": operation,
        "cipher_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "plan_sha256": bundle["plan_sha256"],
        "encrypted_bytes": len(result.stdout),
        "offering_count": len(offering_ids),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for flag in ("operation", "plan", "key-file", "output"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--authority")
    parser.add_argument("--offering", action="append", default=[])
    args = parser.parse_args()
    print(
        json.dumps(
            package(
                operation=args.operation,
                plan_path=Path(args.plan),
                key_path=Path(args.key_file),
                output=Path(args.output),
                authority_path=Path(args.authority) if args.authority else None,
                offering_ids=args.offering,
            ),
            sort_keys=True,
        )
    )
