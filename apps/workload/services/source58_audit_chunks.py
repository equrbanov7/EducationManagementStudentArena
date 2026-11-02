"""Read-only fixed-scope audit bodies, encrypted in bounded pieces before disk."""

import base64
import hashlib
import json
import os
import zipfile
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder

from .scoped_snapshot import encrypt

CHUNK_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_AUDITS = 1000
FORMAT = "wcu-source58-audit-chunks/1"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True).encode()


def write_bundle(rows, public_key, output, context):
    """Rows carry exact PostgreSQL row_to_json UTF8 bytes, not reserialized JSON.

    Only ciphertext ZIP entries touch disk. The encrypted final manifest commits
    every ordered audit ID/hash/length and every chunk hash/ordinal. Partial files
    are removed on any failure; a bundle is never evidence of absence or authority.
    """
    key = Path(public_key).read_bytes()
    manifest = dict(context, format=FORMAT, eligible_for_apply=False, history_cleared_for_apply=False)
    inventory, total, seen = [], 0, set()
    created = False
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                for number, row in enumerate(rows):
                    if number >= MAX_AUDITS:
                        raise ValueError("source58_chunk_audit_count_budget")
                    audit_id, raw, expected_sha, expected_bytes = row
                    if audit_id in seen or not isinstance(raw, bytes):
                        raise ValueError("source58_chunk_identity_invalid")
                    seen.add(audit_id)
                    total += len(raw)
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("source58_chunk_total_budget")
                    if len(raw) != expected_bytes or digest(raw) != expected_sha:
                        raise ValueError("source58_chunk_raw_changed")
                    chunks = []
                    for ordinal, offset in enumerate(range(0, len(raw), CHUNK_BYTES)):
                        body = raw[offset : offset + CHUNK_BYTES]
                        name = f"audit-{number:04d}-part-{ordinal:04d}.enc.json"
                        payload = dict(
                            format=FORMAT,
                            audit_id=audit_id,
                            ordinal=ordinal,
                            offset=offset,
                            raw_record_sha256=expected_sha,
                            raw_bytes=expected_bytes,
                            chunk_sha256=digest(body),
                            encoding="base64",
                            content=base64.b64encode(body).decode(),
                        )
                        cipher = encoded(encrypt(payload, key))
                        archive.writestr(name, cipher)
                        chunks.append(
                            dict(
                                file=name,
                                ordinal=ordinal,
                                offset=offset,
                                bytes=len(body),
                                plaintext_sha256=digest(body),
                                encrypted_sha256=digest(cipher),
                            )
                        )
                    inventory.append(
                        dict(id=audit_id, raw_record_sha256=expected_sha, raw_bytes=expected_bytes, chunks=chunks)
                    )
                if len(inventory) != context["matched_audit_count"]:
                    raise ValueError("source58_chunk_incomplete_inventory")
                manifest.update(
                    inventory=inventory,
                    audit_count=len(inventory),
                    total_raw_bytes=total,
                    ordered_inventory_sha256=digest(encoded(inventory)),
                    complete=True,
                )
                archive.writestr("manifest.enc.json", encoded(encrypt(manifest, key)))
            stream.flush()
            os.fsync(stream.fileno())
        return digest(Path(output).read_bytes())
    except BaseException:
        if created:
            Path(output).unlink(missing_ok=True)
        raise
