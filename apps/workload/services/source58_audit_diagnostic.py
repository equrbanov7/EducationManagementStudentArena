"""Encrypted full fixed audit evidence; never a recovery/clear-intent verdict."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone

from core.rls import apply_rls_request_context

from .four_cell_recovery_history import validate_fixed_recovery_actor
from .scoped_snapshot import SnapshotError
from .scoped_snapshot.four_cell_history import annotated
from .scoped_snapshot.recovery_audit_scope import audit_locator
from .scoped_snapshot.source58_evidence_rows import budget
from .scoped_snapshot.source58_evidence_spec import HISTORY_SCOPE, ORG, SOURCE_SHA256
from .source58_audit_chunks import MAX_AUDITS, MAX_TOTAL_BYTES, write_bundle
from .source58_audit_scope import reference_ids


def capture(username, public_key, output):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
        actor = get_user_model().objects.get(username=username, is_active=True, is_superuser=True)
        organization = apps.get_model("organizations.Organization").objects.get(pk=ORG)
        validate_fixed_recovery_actor(actor=actor, organization=organization)
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
        with budget():
            refs = reference_ids()
            locator = audit_locator(HISTORY_SCOPE.cases, referenced_ids=refs, source_points=HISTORY_SCOPE.cases)
            Audit = apps.get_model("audit.AuditLog")
            query = Audit._base_manager.filter(organization_id=ORG).filter(locator).order_by("created_at", "pk")
            inventory = list(annotated(query).values("id", "_raw_sha", "_raw_bytes")[: MAX_AUDITS + 1])
            if len(inventory) > MAX_AUDITS or sum(r["_raw_bytes"] for r in inventory) > MAX_TOTAL_BYTES:
                raise SnapshotError("source58_diagnostic_inventory_budget")
            matched_ids = [r["id"] for r in inventory]
            unlocated_deletes = (
                Audit._base_manager.filter(
                    organization_id=ORG,
                    action__iexact="delete",
                    resource_type__in=(
                        "registrar.LessonMark",
                        "registrar.lessonmark",
                        "registrar.Lesson",
                        "registrar.lesson",
                    ),
                )
                .exclude(pk__in=matched_ids)
                .count()
            )
            unlocated_grades = (
                Audit._base_manager.filter(
                    organization_id=ORG,
                    resource_type__in=("registrar.grade.mark", "registrar.grade.full-edit"),
                )
                .exclude(pk__in=matched_ids)
                .count()
            )
            table = connection.ops.quote_name(Audit._meta.db_table)

            def rows():
                for item in inventory:
                    # Same exact SQL serialization as annotated(), all fields retained.
                    raw = (
                        Audit._base_manager.filter(organization_id=ORG, pk=item["id"])
                        .annotate(body=RawSQL(f"convert_to(row_to_json({table})::text,'UTF8')", []))
                        .values_list("body", flat=True)
                        .get()
                    )
                    yield str(item["id"]), bytes(raw), item["_raw_sha"], item["_raw_bytes"]

            result = write_bundle(
                rows(),
                public_key,
                output,
                dict(
                    organization_id=ORG,
                    source_sha256=SOURCE_SHA256,
                    captured_at=timezone.now().isoformat(),
                    read_only=True,
                    matched_audit_count=len(inventory),
                    locator_reference_count=len(refs),
                    unlocatable_delete_audits=unlocated_deletes,
                    unlocatable_grade_audits=unlocated_grades,
                    unlocatable_history_remains_hold=True,
                    completeness_scope="exact_source58_locator_only_not_all_tenant_history",
                    clear_delete_intent="UNREVIEWED_FULL_CONTENT",
                    recovery_limits_unchanged=True,
                ),
            )
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            return result
