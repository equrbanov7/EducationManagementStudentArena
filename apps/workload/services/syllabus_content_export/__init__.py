"""Independent encrypted content-fingerprint capture; existing workload/journal formats unchanged."""

import hashlib
import json
import os
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.rls import apply_rls_request_context

from ..scoped_snapshot import SnapshotError, encrypt
from . import spec
from .collect import collect
from .limits import query_budget


def capture(username, batch):
    return _capture(username, batch)


def _capture(username, batch, *, _forensic=False):
    selection = spec.batch_spec(batch)
    if _forensic:
        from ..syllabus_forensic_spec import BATCHES

        if batch not in BATCHES or len(selection["offerings"]) != 20:
            raise SnapshotError("syllabus_root_scope_invalid")
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            organization = apps.get_model("organizations.Organization")
            if not organization.objects.filter(pk=spec.ORG, is_active=True, status="active").exists():
                raise SnapshotError("active_fixed_tenant_required")
            actor = (
                get_user_model()
                .objects.filter(
                    Q(profile__organization_id=spec.ORG)
                    | Q(memberships__organization_id=spec.ORG, memberships__is_active=True)
                    | Q(owned_organizations__pk=spec.ORG),
                    username=username,
                    is_active=True,
                    is_superuser=True,
                )
                .values_list("pk", flat=True)
                .first()
            )
            if actor is None:
                raise SnapshotError("active_fixed_tenant_superuser_required")
            apply_rls_request_context(user_id=actor, org_id=spec.ORG, bypass=False, local=True)
            data = collect(selection, _forensic=True) if _forensic else collect(selection)
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            snapshot = {
                "format": spec.FORMAT,
                "organization_id": spec.ORG,
                "academic_year": spec.YEAR,
                "period_id": spec.PERIOD,
                "batch": batch,
                "registry_sha256": spec.REGISTRY_SHA,
                "captured_at": timezone.now().isoformat(),
                "actor_id": actor,
                "read_only": True,
                "eligible_for_apply": False,
                "selection": selection,
                "coverage": {
                    "lookup_complete": True,
                    "closure_complete": True,
                    "truncated": False,
                    "canonical_hash_policy": "exact_syllabus_recovery.digest/1",
                    "body_scope": "selected_owned_current_approved_ancestry",
                    "base_candidates_metadata_only": True,
                    "root_count": len(data["roots"]),
                    "course_context_count": len(data["offerings"]),
                    "absence_claim": False,
                    "automatic_content_verdict": False,
                },
                "data": data,
                "counts": {key: len(rows) for key, rows in data.items()},
                "schema_fields": {key: sorted({field for row in rows for field in row}) for key, rows in data.items()},
            }
            if _forensic:
                from ..syllabus_forensic_spec import FORMAT

                snapshot["format"] = FORMAT
                snapshot["coverage"].update(
                    closure_complete=False,
                    lineage_visited_complete=True,
                    lineage_integrity=False,
                    normal_content_export_usable=False,
                    cycle_affected_root_count=sum(r["lineage_cycle_affected"] for r in data["held_roots"]),
                )
            if len(json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False).encode()) > spec.MAX_OUTPUT_BYTES:
                raise SnapshotError("syllabus_output_byte_budget_exceeded")
            return snapshot


def save_encrypted(snapshot, public_key, output):
    plaintext = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()
    if len(plaintext) > spec.MAX_OUTPUT_BYTES:
        raise SnapshotError("syllabus_output_byte_budget_exceeded")
    envelope = encrypt(snapshot, Path(public_key).read_bytes())
    encoded = json.dumps(envelope, sort_keys=True).encode()
    if len(encoded) > spec.MAX_OUTPUT_BYTES * 4 // 3 + 4096:
        raise SnapshotError("syllabus_envelope_byte_budget_exceeded")
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(encoded).hexdigest()
