"""Fixed-tenant, chunked encrypted remediation evidence. No database writes."""

import hashlib
import json
import os
import time
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.encrypted_export import encrypt_export
from core.rls import apply_rls_request_context

from .queries import ORG, PERIOD, SCHEMAS, schema_digest, scoped_query

KEY_FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
FORMAT = "qku-reaudit-state/1"
CHUNK_ROWS = 2000
MAX_TABLE_ROWS = 750000
MAX_TOTAL_ROWS = 2000000
MAX_CHUNK_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 600


def encode(value):
    return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()


def save_new(path, value):
    encoded = encode(value)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(encoded).hexdigest()


def byte_chunks(context, rows, page):
    """Split a bounded query page by exact UTF-8 JSON size, never split a row."""
    selected = []
    size = len(encode({**context, "page": page, "rows": []}))
    for row in rows:
        row_size = len(encode(row))
        if selected and size + 2 + row_size > MAX_CHUNK_BYTES:
            payload = {**context, "page": page, "rows": selected}
            yield payload, encode(payload)
            page += 1
            selected = []
            size = len(encode({**context, "page": page, "rows": []}))
        addition = row_size + (2 if selected else 0)  # default JSON separator: ", "
        if size + addition > MAX_CHUNK_BYTES:
            raise ValueError("snapshot_chunk_budget_exceeded")
        selected.append(row)
        size += addition
    if selected:
        payload = {**context, "page": page, "rows": selected}
        yield payload, encode(payload)


def validate_actor(username):
    apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
    if (
        not apps.get_model("organizations", "Organization")
        .objects.filter(pk=ORG, is_active=True, status="active")
        .exists()
    ):
        raise ValueError("active_fixed_organization_required")
    actor = (
        get_user_model()
        .objects.filter(
            Q(profile__organization_id=ORG)
            | Q(memberships__organization_id=ORG, memberships__is_active=True)
            | Q(owned_organizations__id=ORG),
            username=username,
            is_active=True,
            is_superuser=True,
        )
        .values_list("pk", flat=True)
        .first()
    )
    if actor is None:
        raise ValueError("active_fixed_tenant_superuser_required")
    apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
    return actor


def capture(username, public_key, output_dir, *, diagnostic=None):
    """One repeatable-read snapshot; bounded ciphertext shards, no plaintext disk."""
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}

    def phase(operation, model=None, page=None):
        diagnostic.clear()
        diagnostic.update(operation=operation, model=model, page=page)

    phase("preflight")
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise ValueError("fresh_postgresql_transaction_required")
    directory = Path(output_dir)
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError("private_empty_directory_required")
    if any(directory.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    key = Path(public_key).read_bytes()
    # Check the recipient before any database query.
    phase("encrypt")
    encrypt_export({}, key, fingerprint=KEY_FINGERPRINT)
    manifest = {
        "format": FORMAT,
        "organization_id": ORG,
        "period_id": PERIOD,
        "schema_sha256": schema_digest(),
        "read_only": True,
        "complete": False,
        "tables": {},
        "shards": [],
    }
    total = total_bytes = 0
    started = time.monotonic()
    phase("transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
        phase("actor")
        actor = validate_actor(username)
        manifest["captured_at"] = timezone.now().isoformat()
        for label, spec in SCHEMAS.items():
            phase("count", label)
            query = scoped_query(label, spec).order_by("pk")
            count = query.count()
            if count > MAX_TABLE_ROWS or total + count > MAX_TOTAL_ROWS:
                raise ValueError("snapshot_row_budget_exceeded")
            total += count
            manifest["tables"][label] = {"rows": count, "fields": spec["fields"]}
            for metadata_key in ("body_policy", "body_complete", "excluded_body_fields"):
                if metadata_key in spec:
                    manifest["tables"][label][metadata_key] = spec[metadata_key]
            observed = page = 0
            last_pk = None
            for _query_page in range((count + CHUNK_ROWS - 1) // CHUNK_ROWS):
                # Page means the next emitted shard, including byte subdivisions.
                phase("read", label, page)
                if time.monotonic() - started > MAX_SECONDS:
                    raise ValueError("snapshot_time_budget_exceeded")
                window = query if last_pk is None else query.filter(pk__gt=last_pk)
                rows = list(window.values(*spec["fields"])[:CHUNK_ROWS])
                if not rows:
                    raise ValueError("snapshot_unexpected_empty_page")
                last_pk = rows[-1]["id"]
                observed += len(rows)
                context = {
                    "format": FORMAT,
                    "organization_id": ORG,
                    "period_id": PERIOD,
                    "captured_at": manifest["captured_at"],
                    "schema_sha256": manifest["schema_sha256"],
                    "actor_id": actor,
                    "read_only": True,
                    "model": label,
                }
                phase("encode", label, page)
                for payload, plaintext in byte_chunks(context, rows, page):
                    if time.monotonic() - started > MAX_SECONDS:
                        raise ValueError("snapshot_time_budget_exceeded")
                    total_bytes += len(plaintext)
                    if len(plaintext) > MAX_CHUNK_BYTES:
                        raise ValueError("snapshot_chunk_budget_exceeded")
                    if total_bytes > MAX_TOTAL_BYTES:
                        raise ValueError("snapshot_total_byte_budget_exceeded")
                    file = f"{label.lower()}-{page:04}.enc.json"
                    phase("encrypt", label, page)
                    envelope = encrypt_export(payload, key, fingerprint=KEY_FINGERPRINT)
                    phase("write", label, page)
                    encrypted_sha = save_new(directory / file, envelope)
                    manifest["shards"].append(
                        {
                            "file": file,
                            "model": label,
                            "page": page,
                            "rows": len(payload["rows"]),
                            "sha256": encrypted_sha,
                            "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
                        }
                    )
                    page += 1
                    phase("encode", label, page)
            phase("read", label, page)
            if observed != count:
                raise ValueError("snapshot_table_count_changed")
        phase("finalize")
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise ValueError("readonly_transaction_required")
        manifest["complete"] = True
        manifest["total_rows"] = total
        manifest["finished_at"] = timezone.now().isoformat()
    phase("write")
    manifest_sha = save_new(directory / "manifest.json", manifest)
    return {
        "tables": len(manifest["tables"]),
        "shards": len(manifest["shards"]),
        "rows": total,
        "sha256": manifest_sha,
    }
