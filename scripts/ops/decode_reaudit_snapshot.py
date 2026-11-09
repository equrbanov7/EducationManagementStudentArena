"""Local private decoding; authenticated shard closure before atomic publication."""

import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"


def verify_body_projection(manifest):
    schema_file = Path(__file__).resolve().parents[2] / "apps/legacy_import/services/reaudit_snapshot/schemas.json"
    raw = schema_file.read_bytes()
    schemas = json.loads(raw)
    expected = {label: spec["body_policy"] for label, spec in schemas.items() if spec.get("body_policy")}
    actual = {label: spec["body_policy"] for label, spec in manifest["tables"].items() if spec.get("body_policy")}
    current_schema = hashlib.sha256(raw).hexdigest()
    if actual and (actual != expected or manifest.get("schema_sha256") != current_schema):
        raise ValueError("syllabus_body_projection_changed")
    if manifest.get("schema_sha256") == current_schema and actual != expected:
        raise ValueError("syllabus_body_projection_required")


def read_private(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size > limit:
        raise ValueError("private_bounded_file_required")
    return path.read_bytes()


def decode(folder, private_key, output, expected_tool, expected_deployed):
    if output.exists() or output.is_symlink() or output.parent.stat().st_mode & 0o077:
        raise ValueError("new_private_output_required")
    transport = json.loads(read_private(folder / "transport.json", 16384))
    if transport["tool_head"] != expected_tool or transport["deployed_head"] != expected_deployed:
        raise ValueError("capture_head_changed")
    raw = read_private(folder / "manifest.json", 4 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != transport["manifest_sha256"]:
        raise ValueError("manifest_changed")
    manifest = json.loads(raw)
    if manifest.get("complete") is not True or manifest.get("format") != "qku-reaudit-state/1":
        raise ValueError("complete_snapshot_required")
    verify_body_projection(manifest)
    key = serialization.load_pem_private_key(read_private(private_key, 16384), password=None)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != FINGERPRINT:
        raise ValueError("private_key_mismatch")
    tables = {label: [] for label in manifest["tables"]}
    names, seen, total_bytes = set(), set(), 0
    for shard in manifest["shards"]:
        name = shard["file"]
        if not re.fullmatch(r"[a-z_]+\.[a-z_]+-[0-9]{4}\.enc\.json", name) or name in names:
            raise ValueError("fixed_unique_shard_required")
        names.add(name)
        ciphertext = read_private(folder / name, 48 * 1024 * 1024)
        if hashlib.sha256(ciphertext).hexdigest() != shard["sha256"]:
            raise ValueError("ciphertext_changed")
        envelope = json.loads(ciphertext)
        aad = {k: envelope[k] for k in ("format", "cipher", "key_sha256")}
        if aad != {
            "format": "wcu-workload-envelope/1",
            "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
            "key_sha256": FINGERPRINT,
        }:
            raise ValueError("encryption_contract_changed")
        aes = key.decrypt(
            base64.b64decode(envelope["wrapped_key"]),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        plain = AESGCM(aes).decrypt(
            base64.b64decode(envelope["nonce"]),
            base64.b64decode(envelope["ciphertext"]),
            json.dumps(aad, sort_keys=True).encode(),
        )
        total_bytes += len(plain)
        if total_bytes > 512 * 1024 * 1024 or hashlib.sha256(plain).hexdigest() != shard["plaintext_sha256"]:
            raise ValueError("plaintext_budget_or_digest_mismatch")
        payload = json.loads(plain)
        for field in ("format", "organization_id", "period_id", "schema_sha256", "captured_at", "read_only"):
            if payload[field] != manifest[field]:
                raise ValueError("shard_scope_changed")
        label = shard["model"]
        if payload["model"] != label or payload["page"] != shard["page"] or len(payload["rows"]) != shard["rows"]:
            raise ValueError("shard_identity_changed")
        for row in payload["rows"]:
            pk = (label, str(row["id"]))
            if pk in seen or set(row) != set(manifest["tables"][label]["fields"]):
                raise ValueError("duplicate_row_or_contract_drift")
            seen.add(pk)
        tables[label].extend(payload["rows"])
    if any(len(tables[label]) != spec["rows"] for label, spec in manifest["tables"].items()):
        raise ValueError("table_count_mismatch")
    if sum(map(len, tables.values())) != manifest["total_rows"]:
        raise ValueError("total_count_mismatch")
    temporary = output.with_suffix(output.suffix + ".partial")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump({"manifest": manifest, "transport": transport, "tables": tables}, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(temporary, output)
    return {"tables": len(tables), "rows": manifest["total_rows"], "captured_at": manifest["captured_at"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for arg in ("folder", "private-key", "output", "tool-head", "deployed-head"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            decode(Path(args.folder), Path(args.private_key), Path(args.output), args.tool_head, args.deployed_head),
            sort_keys=True,
        )
    )
