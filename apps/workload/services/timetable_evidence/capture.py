"""Fresh PostgreSQL repeatable-read readonly capture; fixed tenant, actor and manifest."""

import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import timetable_clock_evidence
from core.rls import apply_rls_request_context

from ..four_cell_history_capture import save_encrypted
from ..scoped_snapshot import SnapshotError
from ..syllabus_content_export.limits import query_budget
from .contract import validate
from .data import collect
from .spec import FORMAT, MANIFEST_SHA, MAX_BYTES, ORG, PERIOD, SOURCE_REPORT_SHA, selection

__all__ = ["capture", "save_encrypted"]


def capture(username, batch):
    selected = selection(batch)
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout='120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
            organization = (
                apps.get_model("organizations.Organization")
                .objects.filter(pk=ORG, is_active=True, status="active")
                .first()
            )
            if organization is None:
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
            data = collect(selected)
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            payload = {
                "format": FORMAT,
                "organization_id": ORG,
                "period_id": PERIOD,
                "academic_year": "2026/2027",
                "batch": batch,
                "actor_id": actor,
                "manifest_sha256": MANIFEST_SHA,
                "source_report_sha256": SOURCE_REPORT_SHA,
                "captured_at": timezone.now().isoformat(),
                "read_only": True,
                "eligible_for_apply": False,
                "selection": selected,
                "clock_policy": timetable_clock_evidence(organization),
                "counts": {key: len(rows) for key, rows in data.items()},
                "data": data,
            }
            encoded = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False)
            if len(encoded.encode()) > MAX_BYTES:
                raise SnapshotError("timetable_evidence_output_budget")
            payload = json.loads(encoded)
            validate(payload)
            return payload
