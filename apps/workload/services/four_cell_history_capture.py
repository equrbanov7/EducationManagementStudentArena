"""Independent encrypted fixed-four history export; every query is readonly and scoped."""

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

from .scoped_snapshot import SnapshotError, encrypt
from .scoped_snapshot.four_cell_history import CASES, ORG, annotated, bounded, collect_four_cell_history, digest
from .syllabus_content_export.limits import query_budget

FORMAT = "wcu-four-cell-history/1"
MAX_BYTES = 8 * 1024 * 1024
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
CURRENT_FIELDS = {
    "registrar.CourseOffering": [
        "id",
        "organization_id",
        "subject_id",
        "period_id",
        "group_id",
        "instructor_id",
        "is_active",
        "lesson_hours",
        "created_at",
        "updated_at",
    ],
    "registrar.Enrollment": [
        "id",
        "organization_id",
        "offering_id",
        "student_id",
        "status",
        "kind",
        "source_group_id",
        "superseded_by_id",
        "added_by_id",
        "absence_hours",
        "created_at",
        "updated_at",
    ],
    "registrar.Lesson": [
        "id",
        "organization_id",
        "offering_id",
        "date",
        "start_time",
        "end_time",
        "kind",
        "hours",
        "instructor_id",
        "created_by_id",
        "is_legacy_synthesised",
        "room_id",
        "syllabus_week",
        "created_at",
        "updated_at",
    ],
}


def current_rows():
    data = {}
    for label, key in [
        ("registrar.CourseOffering", "offering_id"),
        ("registrar.Enrollment", "enrollment_id"),
        ("registrar.Lesson", "lesson_id"),
    ]:
        query = (
            apps.get_model(label)
            .objects.filter(organization_id=ORG, pk__in={c[key] for c in CASES.values()})
            .order_by("pk")
        )
        data[label] = bounded(annotated(query).values(*CURRENT_FIELDS[label], "_raw_sha"))
    return [
        {
            "model_label": label,
            **{k: v for k, v in row.items() if k != "_raw_sha"},
            "raw_record_sha256": row["_raw_sha"],
        }
        for label, rows in data.items()
        for row in rows
    ]


def capture(username):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout='120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
            Organization = apps.get_model("organizations.Organization")
            if not Organization.objects.filter(pk=ORG, is_active=True, status="active").exists():
                raise SnapshotError("active_fixed_tenant_required")
            actor = (
                get_user_model()
                .objects.filter(
                    Q(profile__organization_id=ORG)
                    | Q(memberships__organization_id=ORG, memberships__is_active=True)
                    | Q(owned_organizations__pk=ORG),
                    username=username,
                    is_active=True,
                    is_superuser=True,
                )
                .values_list("pk", flat=True)
                .first()
            )
            if actor is None:
                raise SnapshotError("active_fixed_tenant_superuser_required")
            apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
            data = collect_four_cell_history()
            data["four_cell_history_current"] = current_rows()
            result = {
                "format": FORMAT,
                "organization_id": ORG,
                "academic_year": "2026/2027",
                "period_id": PERIOD,
                "actor_id": actor,
                "captured_at": timezone.now().isoformat(),
                "source_spec_sha256": digest(CASES),
                "read_only": True,
                "eligible_for_apply": False,
                "counts": {key: len(rows) for key, rows in data.items()},
                "schema_fields": {key: sorted({f for row in rows for f in row}) for key, rows in data.items()},
                "data": data,
            }
            if len(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False).encode()) > MAX_BYTES:
                raise SnapshotError("four_cell_history_output_budget_exceeded")
            return result


def save_encrypted(payload, public_key, output):
    if len(json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False).encode()) > MAX_BYTES:
        raise SnapshotError("four_cell_history_output_budget_exceeded")
    raw = json.dumps(encrypt(payload, Path(public_key).read_bytes()), sort_keys=True).encode()
    if len(raw) > MAX_BYTES * 4 // 3 + 4096:
        raise SnapshotError("four_cell_history_output_budget_exceeded")
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    fd = os.open(Path(output).parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256(raw).hexdigest()
