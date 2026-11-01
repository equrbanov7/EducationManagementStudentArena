"""Fixed Four/Source28 audit-size metadata; no raw JSON or recovery authority."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone

from core.rls import apply_rls_request_context

from .four_cell_recovery_history import validate_fixed_recovery_actor
from .scoped_snapshot import SnapshotError
from .scoped_snapshot.four_cell_history import RESOURCE_CODES, annotated, bounded, digest
from .scoped_snapshot.four_cell_history_spec import CASES, MAX_AUDIT_BYTES, ORG
from .scoped_snapshot.recovery_audit_scope import audit_queryset
from .source28_spec import history_scope
from .syllabus_content_export.limits import query_budget

FORMAT = "wcu-recovery-audit-diagnostic/2"


def metadata(cases):
    query = annotated(audit_queryset(cases))
    table = query.model._meta.db_table
    for field in ("changes", "old_values", "new_values"):
        query = query.annotate(
            **{
                "_" + field + "_bytes": RawSQL(f'octet_length("{table}"."{field}"::text)', []),
                "_"
                + field
                + "_sha": RawSQL(
                    f"encode(sha256(convert_to(COALESCE(\"{table}\".\"{field}\"::text,'null'),'UTF8')),'hex')", []
                ),
            }
        )
    rows = bounded(
        query.values(
            "id",
            "organization_id",
            "created_at",
            "action",
            "resource_type",
            "resource_id",
            "_raw_sha",
            "_raw_bytes",
            *["_" + name + suffix for name in ("changes", "old_values", "new_values") for suffix in ("_bytes", "_sha")],
        )
    )
    result = []
    known = {c[k] for c in cases.values() for k in ("offering_id", "lesson_id", "enrollment_id")}
    for row in rows:
        resource = str(row["resource_id"] or "")
        kind = row["resource_type"]
        result.append(
            {
                "id": str(row["id"]),
                "organization_id": str(row["organization_id"]),
                "created_at": row["created_at"],
                "action": row["action"] if row["action"] in {"create", "update", "delete", "view"} else "other",
                "resource_kind": kind if kind in RESOURCE_CODES else "other",
                "resource_kind_sha256": digest(kind),
                "resource_id": resource if resource in known else None,
                "resource_id_sha256": digest(resource),
                "raw_record_sha256": row["_raw_sha"],
                "raw_bytes": row["_raw_bytes"],
                **{
                    name + suffix: row["_" + name + suffix]
                    for name in ("changes", "old_values", "new_values")
                    for suffix in ("_bytes", "_sha")
                },
            }
        )
    from .scoped_snapshot import workload_audit_receipt_spec as thin_spec
    from .scoped_snapshot import workload_audit_receipts as thin

    previews = []
    for row in thin.preview(query):
        try:
            thin.validate(row)
            verified = True
        except ValueError:
            verified = False
        previews.append(
            {
                "id": str(row["id"]),
                "raw_record_sha256": row["_raw_sha"],
                "raw_bytes": row["_raw_bytes"],
                "created_at": row["created_at"],
                "user_id": row["user_id"],
                "row_hash_matches": row["_raw_sha"] == thin_spec.PINS[str(row["id"])][1],
                "semantic_checks_passed": verified,
                "grade_apply_authority": False,
                "json_hash_policy": thin_spec.JSON_SQL_POLICY,
                "row_hash_policy": thin_spec.ROW_SQL_POLICY,
                "proof": row["_thin"],
            }
        )
    return {
        "receipt_semantic_previews": previews,
        "rows": result,
        "row_count": len(result),
        "total_raw_bytes": sum(row["raw_bytes"] for row in result),
        "strict_total_budget": MAX_AUDIT_BYTES,
        "strict_per_row_budget": 1024 * 1024,
        "raw_json_fetched": False,
        "history_cleared_for_apply": False,
    }


def capture(username):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
            actor = get_user_model().objects.get(username=username, is_active=True, is_superuser=True)
            organization = apps.get_model("organizations.Organization").objects.get(pk=ORG)
            validate_fixed_recovery_actor(actor=actor, organization=organization)
            apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
            data = {"four": metadata(CASES), "source28": metadata(history_scope().cases)}
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            return {
                "format": FORMAT,
                "organization_id": ORG,
                "captured_at": timezone.now().isoformat(),
                "read_only": True,
                "eligible_for_apply": False,
                "absence_claim": False,
                "raw_body_included": False,
                "data": data,
            }
