"""Bounded SQL hashes plus explicit metadata; raw grade/JSON/text stays in PostgreSQL."""

import json
from contextlib import contextmanager
from time import monotonic

from django.db import connection
from django.db.models import Q
from django.db.models.expressions import RawSQL

from ..reviewed_leyla_catalog_graph import digest, model, normal
from . import source58_evidence_spec as fixed
from .four_cell_history import annotated

MAX_ROWS = 20000
MAX_BYTES = 32 * 1024 * 1024
MAX_QUERIES = 600
MAX_SECONDS = 90
MAX_DEPTH = 16
SAFE = {
    "created_at",
    "updated_at",
    "status",
    "is_active",
    "is_deleted",
    "deleted_at",
    "blocked_at",
    "access_state",
    "date",
    "start_time",
    "end_time",
    "kind",
    "hours",
    "lesson_hours",
    "absence_hours",
    "absence_exempt",
    "old_absence_hours",
    "new_absence_hours",
    "old_status",
    "new_status",
    "created_mark",
    "is_deletion",
    "old_date",
    "new_date",
    "old_kind",
    "new_kind",
    "old_hours",
    "new_hours",
    "old_time",
    "new_time",
    "reverted_at",
    "field",
    "category",
    "reason_code",
    "from_status",
    "to_status",
    "mapping_status",
    "evidence_kind",
    "artifact_kind",
    "source_pk",
    "source_table",
    "source_system",
    "source_row_hash",
    "source_snapshot_sha256",
    "materialization_digest",
    "evidence_digest",
    "is_archive",
    "state",
    "target_model_label",
    "target_pk",
    "entity_type",
    "legacy_pk",
    "transform_version",
    "academic_year",
    "season",
    "row_kind",
    "activity",
    "total_hours",
    "lecture_plan",
    "seminar_plan",
    "lab_plan",
    "lecture_total",
    "seminar_total",
    "lab_total",
    "union_count",
    "subgroup_count",
    "is_hourly_paid",
    "is_published",
    "approval_status",
    "locked_at",
    "is_superuser",
    "is_staff",
    "start_date",
    "end_date",
    "starts_on",
    "ends_on",
    "source_student_ref",
    "source_journal_ref",
    "source_lesson_ref",
    "source_group_ref",
    "source_enrollment_ref",
    "mapping_issue_code",
    "national_athlete_exemption",
    "absence_limit_percent",
}
HASH_ONLY = {
    "reason",
    "note",
    "document",
    "evidence",
    "revert_reason",
    "reason_note",
    "lesson_label",
    "national_athlete_exemption_note",
}


class EvidenceLimit(ValueError):
    pass


class Rows:
    def __init__(self):
        self.seen = set()
        self.bytes = 0

    def read(self, query, *, cap=MAX_ROWS):
        cls = query.model
        if cls._meta.label_lower == "auth.user":
            # Never read or hash the auth password/contact columns, even server-side.
            rows = list(query.order_by("pk").values("id", "is_active", "is_superuser", "is_staff")[: cap + 1])
            if len(rows) > cap:
                raise EvidenceLimit("source58_auth_metadata_budget")
            for row in rows:
                row["_raw_sha"] = digest(row)
                row["_raw_bytes"] = len(json.dumps(row).encode())
                row["_hash_policy"] = "safe-auth-identity-projection-sha256/1"
            return rows
        fields = {field.attname for field in cls._meta.concrete_fields}
        selected = (SAFE & fields) | {cls._meta.pk.attname}
        selected |= {field.attname for field in cls._meta.concrete_fields if field.is_relation}
        table = connection.ops.quote_name(cls._meta.db_table)
        hashes = {
            key
            + "_sha256": RawSQL(
                f"encode(sha256(convert_to(COALESCE({table}.{connection.ops.quote_name(key)}::text,'null'),'UTF8')),'hex')",
                [],
            )
            for key in HASH_ONLY & fields
        }
        if "reason" in fields and cls._meta.get_field("reason").choices:
            choices = [str(value) for value, _ in cls._meta.get_field("reason").choices]
            hashes["formal_reason_code"] = RawSQL(
                f"CASE WHEN {table}.reason = ANY(%s) THEN {table}.reason ELSE NULL END", [choices]
            )
        rows = normal(
            list(
                annotated(query)
                .annotate(**hashes)
                .order_by("pk")
                .values(*sorted(selected), *sorted(hashes), "_raw_sha", "_raw_bytes")[: cap + 1]
            )
        )
        if len(rows) > cap:
            raise EvidenceLimit("source58_row_budget")
        for row in rows:
            key = (cls._meta.label, str(row[cls._meta.pk.attname]))
            if str(row.get("organization_id", fixed.ORG)) != fixed.ORG:
                raise EvidenceLimit("source58_cross_tenant_reference")
            if key not in self.seen:
                self.seen.add(key)
                self.bytes += row["_raw_bytes"]
            if len(self.seen) > MAX_ROWS or self.bytes > MAX_BYTES:
                raise EvidenceLimit("source58_total_row_or_byte_budget")
        return rows

    def graph(self, roots):
        pending = {label: set(map(str, ids)) for label, ids in roots.items()}
        seen, result = {}, {}
        for _depth in range(MAX_DEPTH + 1):
            if not pending:
                break
            following = {}
            for label, ids in pending.items():
                ids -= seen.get(label, set())
                if not ids:
                    continue
                cls = model(label)
                values = self.read(cls._base_manager.filter(pk__in=ids))
                seen.setdefault(label, set()).update(ids)
                result.setdefault(label, []).extend(values)
                for rel in cls._meta.get_fields(include_hidden=True):
                    if not rel.auto_created or rel.concrete or rel.related_model is None:
                        continue
                    child = rel.related_model
                    lookup = rel.field.name if rel.many_to_many else rel.field.attname
                    children = list(
                        child._base_manager.filter(**{lookup + "__in": ids})
                        .order_by("pk")
                        .values_list("pk", flat=True)[: MAX_ROWS + 1]
                    )
                    if len(children) > MAX_ROWS:
                        raise EvidenceLimit("source58_reverse_budget")
                    following.setdefault(child._meta.label, set()).update(map(str, children))
            pending = {label: ids - seen.get(label, set()) for label, ids in following.items()}
            pending = {label: ids for label, ids in pending.items() if ids}
        if pending:
            raise EvidenceLimit("source58_reverse_depth_budget")
        return result


def project(rows):
    return [
        {
            "model": label,
            "count": len(values),
            "row_hash_policy": (
                values[0].get("_hash_policy", "postgres-row_to_json-text-utf8-sha256/1")
                if values
                else "postgres-row_to_json-text-utf8-sha256/1"
            ),
            "foreign_keys": [
                {"field": field.attname, "target": field.related_model._meta.label}
                for field in model(label)._meta.concrete_fields
                if field.is_relation and field.related_model is not None
            ],
            "reverse_relations": [
                {
                    "child": rel.related_model._meta.label,
                    "field": rel.field.name if rel.many_to_many else rel.field.attname,
                    "hidden": rel.hidden,
                    "many_to_many": rel.many_to_many,
                }
                for rel in model(label)._meta.get_fields(include_hidden=True)
                if rel.auto_created and not rel.concrete and rel.related_model is not None
            ],
            "protected_rows_sha256": digest(
                sorted((str(row[model(label)._meta.pk.attname]), row["_raw_sha"]) for row in values)
            ),
            "rows": sorted(values, key=lambda row: str(row[model(label)._meta.pk.attname])),
        }
        for label, values in sorted(rows.items())
    ]


@contextmanager
def budget():
    started, count = monotonic(), 0

    def enforce(execute, sql, params, many, context):
        nonlocal count
        count += 2  # One local timeout SELECT plus the protected read.
        if not sql.lstrip().upper().startswith(("SELECT", "SHOW")):
            raise EvidenceLimit("source58_select_only_required")
        if count > MAX_QUERIES or monotonic() - started > MAX_SECONDS:
            raise EvidenceLimit("source58_query_or_time_budget")
        remaining_ms = max(1, int((MAX_SECONDS - (monotonic() - started)) * 1000))
        execute("SELECT set_config('statement_timeout', %s, true)", [f"{remaining_ms}ms"], False, context)
        result = execute(sql, params, many, context)
        if monotonic() - started > MAX_SECONDS:
            raise EvidenceLimit("source58_time_budget")
        return result

    with connection.execute_wrapper(enforce):
        yield


def require_readonly():
    if connection.vendor != "postgresql" or not connection.in_atomic_block:
        raise EvidenceLimit("source58_readonly_postgresql_required")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('transaction_read_only'), current_setting('app.current_org_id', true), current_setting('app.bypass_rls', true), current_setting('app.current_user_id', true)"
        )
        readonly, organization, bypass, actor = cursor.fetchone()
    if readonly != "on" or organization != fixed.ORG or bypass not in (None, "", "off", "0", "false"):
        raise EvidenceLimit("source58_readonly_tenant_context_required")
    if (
        not actor
        or not actor.isdigit()
        or not model("auth.User")
        .objects.filter(
            Q(profile__organization_id=fixed.ORG)
            | Q(memberships__organization_id=fixed.ORG, memberships__is_active=True)
            | Q(owned_organizations__pk=fixed.ORG),
            pk=int(actor),
            is_active=True,
            is_superuser=True,
        )
        .exists()
    ):
        raise EvidenceLimit("source58_active_scoped_superadmin_required")
    return int(actor)


def export_budget(data):
    if len(json.dumps(data, default=str).encode()) > MAX_BYTES:
        raise EvidenceLimit("source58_export_byte_budget")
    return data
