"""A fresh repeatable-read read-only tenant audit; no grade or cohort mutation APIs."""

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

from apps.workload.services.chair_cells_export import query_budget
from apps.workload.services.scoped_snapshot import SnapshotError, encrypt
from core.rls import apply_rls_request_context

from . import spec
from .collect import collect
from .contract import validate
from .source import load


def capture(username, path, expected):
    source = load(path, expected)
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            org = apps.get_model("organizations", "Organization")
            if not org.objects.filter(pk=spec.ORG, is_active=True, status="active").exists():
                raise SnapshotError("active_fixed_tenant_required")
            actor = (
                get_user_model()
                .objects.filter(
                    Q(profile__organization_id=spec.ORG)
                    | Q(
                        memberships__organization_id=spec.ORG,
                        memberships__is_active=True,
                    )
                    | Q(owned_organizations__id=spec.ORG),
                    username=username,
                    is_active=True,
                    is_superuser=True,
                    profile__access_state="active",
                    profile__is_deleted=False,
                    profile__blocked_at__isnull=True,
                    profile__deleted_at__isnull=True,
                )
                .values_list("pk", flat=True)
                .first()
            )
            if actor is None:
                raise SnapshotError("active_fixed_tenant_superuser_required")
            apply_rls_request_context(user_id=actor, org_id=spec.ORG, bypass=False, local=True)
            period = apps.get_model("organizations", "AcademicPeriod")
            subjects = apps.get_model("registrar", "Subject")
            if not period.objects.filter(
                pk=spec.PERIOD, organization_id=spec.ORG, academic_year=spec.YEAR
            ).exists() or set(
                str(pk)
                for pk in subjects.objects.filter(pk__in=spec.SUBJECTS, organization_id=spec.ORG).values_list(
                    "pk", flat=True
                )
            ) != set(
                spec.SUBJECTS
            ):
                raise SnapshotError("english_level_fixed_scope_missing")
            data = collect(source)
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            if sum(len(rows) for rows in data.values()) > spec.MAX_ROWS:
                raise SnapshotError("english_level_total_row_budget_exceeded")
            result = {
                "format": spec.FORMAT,
                "organization_id": spec.ORG,
                "academic_year": spec.YEAR,
                "period_id": spec.PERIOD,
                "subject_ids": list(spec.SUBJECTS),
                "source_sha256": spec.SOURCE_SHA,
                "source_namespace": "myedu_new.students.id",
                "source_ids_sha256": spec.SOURCE_IDS_SHA,
                "source_rows_sha256": source["source_rows_sha256"],
                "source_captured_at": source["captured_at"],
                "captured_at": timezone.now().isoformat(),
                "actor_id": actor,
                "read_only": True,
                "eligible_for_apply": False,
                "immutable_mapping": False,
                "data": data,
                "coverage": {
                    "written_marks_exported": False,
                    "raw_lesson_marks_exported": False,
                    "identity_creates_or_mutations": False,
                    "archive_filter_applied": False,
                    "teacher_access_attested": False,
                },
                "counts": {name: len(rows) for name, rows in data.items()},
            }
            if (
                len(
                    json.dumps(
                        result,
                        cls=DjangoJSONEncoder,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode()
                )
                > spec.MAX_BYTES
            ):
                raise SnapshotError("english_level_byte_budget_exceeded")
            return validate(
                json.loads(
                    json.dumps(
                        result,
                        cls=DjangoJSONEncoder,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            )


def save_encrypted(snapshot, public_key, output):
    validate(snapshot)
    raw = json.dumps(encrypt(snapshot, Path(public_key).read_bytes()), sort_keys=True).encode()
    if len(raw) > spec.MAX_BYTES:
        raise SnapshotError("english_level_envelope_budget_exceeded")
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()
