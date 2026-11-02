"""Fixed-tenant read-only snapshot and authenticated public-key envelope."""

import hashlib
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from core.encrypted_export import encrypt_export
from core.rls import apply_rls_request_context

from .data import ORG, YEAR, collect
from .ilahe_references import collect_ilahe_references
from .jale_account_inventory import collect_jale_account_inventory
from .jale_handovers import collect_jale_handovers
from .journal_diagnostics import collect_journal_diagnostics
from .leyla_references import collect_leyla_references
from .request_content import collect_request_content
from .request_syllabus import collect_request_syllabus
from .source58_evidence import collect_source58_evidence
from .two_catalog_references import collect_two_catalog_references
from .vefa_catalog_references import collect_vefa_catalog_references

KEY_FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
FORMAT = "wcu-workload-snapshot/1"


class SnapshotError(ValueError):
    pass


def capture(username):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        # Fixed tenant, no bypass, including when invoked from a superuser ops shell.
        apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
        actor = (
            get_user_model()
            .objects.filter(username=username, is_active=True, is_superuser=True)
            .values_list("id", flat=True)
            .first()
        )
        if actor is None:
            raise SnapshotError("active_superuser_required")
        apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
        data = collect(student_secret=os.urandom(32))
        data["journal_access_diagnostics"] = collect_journal_diagnostics(data)
        data.update(collect_request_content())
        data.update(collect_request_syllabus())
        data.update(collect_leyla_references())
        data.update(collect_ilahe_references())
        data.update(collect_jale_handovers())
        data.update(collect_jale_account_inventory())
        data.update(collect_two_catalog_references())
        data.update(collect_vefa_catalog_references())
        data.update(collect_source58_evidence())
        if not data["tasks"]:
            raise SnapshotError("fixed_org_tasks_missing")
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise SnapshotError("readonly_transaction_required")
        return {
            "format": FORMAT,
            "organization_id": ORG,
            "academic_year": YEAR,
            "captured_at": timezone.now().isoformat(),
            "actor_id": actor,
            "coverage": {
                "current_chairs": len({r["chair_id"] for r in data["tasks"]}),
                "current_tasks": len(data["tasks"]),
                "official_source_chairs": 14,
                "official_source_status": "external reconciliation coverage14/18; not a live completeness assertion",
            },
            "schema_fields": {key: sorted({field for row in values for field in row}) for key, values in data.items()},
            "fingerprints": "MD5 opaque change detectors, not cryptographic integrity; AES-GCM authenticates export",
            "student_set_tokens": "HMAC-SHA256 with random per-snapshot secret, never exported; same student stable only within this snapshot; exact group IDs preserved, no aliases or parent/child/sector merge",
            "data": data,
        }


def encrypt(snapshot, public_key_bytes):
    return encrypt_export(snapshot, public_key_bytes, fingerprint=KEY_FINGERPRINT, error_class=SnapshotError)


def save_encrypted(snapshot, public_key, output):
    envelope = encrypt(snapshot, Path(public_key).read_bytes())
    encoded = json.dumps(envelope, sort_keys=True).encode()
    # O_EXCL prevents overwriting an old snapshot;0600 from creation, no plaintext file.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()
