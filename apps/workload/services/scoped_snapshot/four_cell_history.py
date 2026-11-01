"""Bounded fixed-four available audit/source-claim evidence; never recovery authority."""

import hashlib
import json
import re
import uuid

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import Q
from django.db.models.expressions import RawSQL

from .four_cell_history_spec import CASES, MAX_AUDIT_BYTES, MAX_ROWS, ORG

UUID_REFS = {
    "offering_id",
    "lesson_id",
    "lesson_ref",
    "enrollment_id",
    "enrollment_ref",
    "lesson_mark_id",
    "lesson_mark_ref",
}
BLANK = {"", "—", "-", "clear"}
RESOURCE_CODES = {
    "registrar.grade.mark",
    "registrar.grade.full-edit",
    "registrar.Lesson",
    "registrar.lesson",
    "registrar.LessonMark",
    "registrar.lessonmark",
    "legacy_import.reviewed_journal_content",
    "legacy_import.reviewed_content",
    "legacy_import.applied_math_coupled_repair",
}


def mark_ids(*, _cases=None):
    cases = CASES if _cases is None else _cases
    return {
        point: str(
            uuid.uuid5(
                uuid.UUID(ORG),
                f"reviewed-source-mark:{c['lesson_id']}:{c['enrollment_id']}",
            )
        )
        for point, c in cases.items()
    }


def digest(value):
    return hashlib.sha256(
        json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def typed_refs(value):
    result = {}
    stack = [(value, 0)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > 10000 or depth > 32:
            raise ValueError("four_cell_audit_shape_budget_exceeded")
        if isinstance(node, dict):
            for key, val in node.items():
                if key in UUID_REFS and isinstance(val, str):
                    result.setdefault(key, set()).add(val)
                if key == "student_id" and (type(val) is int or isinstance(val, str) and val.isdigit()):
                    result.setdefault(key, set()).add(int(val))
                if isinstance(val, (dict, list)):
                    stack.append((val, depth + 1))
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)
    return result


def case_ids(refs, *, _cases=None):
    cases = CASES if _cases is None else _cases
    result = []
    for point, c in cases.items():
        enrs = refs.get("enrollment_id", set()) | refs.get("enrollment_ref", set())
        lessons = refs.get("lesson_id", set()) | refs.get("lesson_ref", set())
        # An enrollment alone is a source-claim locator, not proof of this particular slot.
        if c["enrollment_id"] in enrs and c["lesson_id"] in lessons:
            result.append(point)
    return result


def project_audit(row, labels, *, _cases=None, _undo_operation="fixed_four_undo"):
    cases = CASES if _cases is None else _cases
    refs = typed_refs([row.get(k) for k in ["changes", "old_values", "new_values"]])
    ids = case_ids(refs, _cases=cases)
    changes = []
    raws = row.get("changes") or []
    if not isinstance(raws, list):
        raws = []
    for index, change in enumerate(raws):
        if not isinstance(change, dict):
            continue
        direct = case_ids(typed_refs(change), _cases=cases)
        lesson_deleted = (
            change.get("student") == "—" and change.get("old") == "dərs sütunu" and change.get("new") == "silindi"
        )
        for point, c in cases.items():
            expected = labels.get(c["student_id"])
            if (
                lesson_deleted
                and expected
                and str(row.get("resource_id")) == c["offering_id"]
                and digest(change.get("item")) in expected["item_sha256_by_point"].get(point, [])
            ):
                direct.append(point)
            if (
                expected
                and digest(change.get("student")) == expected["student_label_sha256"]
                and digest(change.get("item")) in expected["item_sha256_by_point"].get(point, [])
                and point not in direct
            ):
                direct.append(point)
        if not direct:
            continue
        old, new = change.get("old"), change.get("new")

        def blank(value):
            return value is None or isinstance(value, str) and value in BLANK

        def numeric(value):
            if type(value) in (int, float, str) and re.fullmatch(
                r"(?:10(?:\.0{1,2})?|[0-9](?:\.[0-9]{1,2})?)", str(value)
            ):
                return str(value)
            return None

        for point in direct:
            changes.append(
                {
                    "audit_id": str(row["id"]),
                    "source_point_id": point,
                    "change_index": index,
                    "old_sha256": digest(old),
                    "new_sha256": digest(new),
                    "old_blank": blank(old),
                    "new_blank": blank(new),
                    "old_numeric": numeric(old),
                    "new_numeric": numeric(new),
                    "clear_evidence": not blank(old) and blank(new),
                    "lesson_delete_evidence": lesson_deleted,
                    "time_absent_from_legacy_audit_label": point not in case_ids(typed_refs(change), _cases=cases),
                    "matching": (
                        "typed_pair"
                        if point in case_ids(typed_refs(change), _cases=cases)
                        else "current_exact_label_and_date_kind"
                    ),
                }
            )
        ids.extend(direct)
    resource = str(row.get("resource_id") or "")
    direct = [
        point
        for point, c in cases.items()
        if resource in {c["lesson_id"], c["enrollment_id"], mark_ids(_cases=cases)[point]}
    ]
    deleted = row["action"].lower() == "delete"
    if deleted:
        direct.extend(point for point, c in cases.items() if resource == c["offering_id"])
    ids.extend(direct)
    known = {c[k] for c in cases.values() for k in ["offering_id", "lesson_id", "enrollment_id"]}
    known |= set(mark_ids(_cases=cases).values())
    code = row.get("resource_type")
    return {
        "id": str(row["id"]),
        "organization_id": ORG,
        "created_at": row["created_at"],
        "user_id": row.get("user_id"),
        "action": (row["action"] if row["action"] in {"create", "update", "delete", "view"} else "other"),
        "resource_kind": code if code in RESOURCE_CODES else "other",
        "resource_kind_sha256": digest(code),
        "resource_id": resource if resource in known else None,
        "resource_id_sha256": digest(resource),
        "case_ids": sorted(set(ids)),
        "raw_record_sha256": row["_raw_sha"],
        "old_values_sha256": digest(row.get("old_values")),
        "new_values_sha256": digest(row.get("new_values")),
        "changes_sha256": digest(row.get("changes")),
        "reason_present": bool(row.get("reason")),
        "malformed_intent": bool(
            code in {"registrar.grade.mark", "registrar.grade.full-edit"}
            and (not isinstance(row.get("changes"), list) or any(not isinstance(c, dict) for c in row["changes"]))
        ),
        "source_undo_marker": bool(
            code == "legacy_import.reviewed_content"
            and isinstance(row.get("new_values"), dict)
            and row["new_values"].get("operation") == _undo_operation
        ),
        "unresolved_scope_row": not bool(ids),
        "contrary_clear_evidence": any(c["clear_evidence"] for c in changes),
        "contrary_delete_evidence": bool(deleted and direct) or any(c["lesson_delete_evidence"] for c in changes),
    }, changes


def bounded(query):
    rows = list(query[: MAX_ROWS + 1])
    if len(rows) > MAX_ROWS:
        raise ValueError("four_cell_history_row_budget_exceeded")
    return rows


def annotated(query):
    table = query.model._meta.db_table
    # PostgreSQL SHA256 occurs on the server: raw notes/contact/JSON never leave the DB in evidence rows.
    text = f'row_to_json("{table}")::text'
    return query.annotate(
        _raw_sha=RawSQL(f"encode(sha256(convert_to({text},'UTF8')),'hex')", []),
        _raw_bytes=RawSQL(f"octet_length({text})", []),
    )


def collect_four_cell_history():
    if connection.vendor != "postgresql" or not connection.in_atomic_block:
        raise ValueError("four_cell_readonly_pg_required")
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()[0] != "on":
            raise ValueError("four_cell_readonly_pg_required")
    return collect_available_history()


def collect_available_history(*, _scope=None):
    """SELECT-only core; internal sanctioned writer also needs fresh contrary evidence."""
    if connection.vendor != "postgresql" or not connection.in_atomic_block:
        raise ValueError("four_cell_atomic_pg_required")
    from .history_scope import approved_history_scope

    if _scope is not None and not approved_history_scope(_scope):
        raise ValueError("compiled_history_scope_required")
    cases = CASES if _scope is None else _scope.cases
    prefix = "four_cell_history" if _scope is None else _scope.prefix
    undo_operation = "fixed_four_undo" if _scope is None else _scope.undo_operation
    model = apps.get_model
    from .recovery_audit_scope import audit_queryset

    enrs = {c["enrollment_id"] for c in cases.values()}
    lessons = {c["lesson_id"] for c in cases.values()}
    audit = audit_queryset(cases)
    from . import workload_audit_receipt_spec as thin_spec
    from . import workload_audit_receipts as thin

    pre = bounded(annotated(audit).values("id", "_raw_bytes", "_raw_sha"))
    matched_ids = [row["id"] for row in pre]
    query = Q(pk__in=matched_ids)
    audit = model("audit.AuditLog").objects.filter(organization_id=ORG, pk__in=matched_ids).order_by("created_at", "pk")
    fixed_ids = {str(row["id"]) for row in pre} & thin_spec.PINS.keys()
    for row in pre:
        if str(row["id"]) in fixed_ids and row["_raw_sha"] != thin_spec.PINS[str(row["id"])][1]:
            raise ValueError("fixed_workload_receipt_row_changed")
    raw_pre = [row for row in pre if str(row["id"]) not in fixed_ids]
    raw_bytes = sum(row["_raw_bytes"] for row in raw_pre)
    if raw_bytes > MAX_AUDIT_BYTES or any(row["_raw_bytes"] > 1024 * 1024 for row in raw_pre):
        raise ValueError("four_cell_audit_byte_budget_exceeded")
    thin_rows = thin.preview(annotated(audit.filter(pk__in=fixed_ids)))
    if {str(row["id"]) for row in thin_rows} != fixed_ids:
        raise ValueError("fixed_workload_receipt_scope_changed")
    thin_audits = [thin.project(row) for row in thin_rows]
    thin_bytes = len(json.dumps(thin_audits, cls=DjangoJSONEncoder, ensure_ascii=False).encode())
    if raw_bytes + thin_bytes > MAX_AUDIT_BYTES:
        raise ValueError("four_cell_audit_byte_budget_exceeded")
    values = bounded(
        annotated(audit.exclude(pk__in=fixed_ids)).values(
            "id",
            "organization_id",
            "created_at",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "changes",
            "old_values",
            "new_values",
            "reason",
            "_raw_sha",
            "_raw_bytes",
        )
    )
    # Grade audit's canonical student label is User.get_full_name() or username, not source names.
    labels = {}
    from django.utils.translation import override

    for user in (
        model("auth.User")
        .objects.filter(
            pk__in={c["student_id"] for c in cases.values()},
            profile__organization_id=ORG,
        )
        .only("id", "first_name", "last_name", "username")
    ):
        items = {}
        for point, c in cases.items():
            if c["student_id"] != user.pk:
                continue
            items[point] = set()
            Lesson = model("registrar.Lesson")
            lesson = Lesson(date=c["date"], kind=c["kind"])
            for language in ["az", "en", "ru", "tr", "de"]:
                with override(language):
                    items[point].add(digest(str(c["date"]) + " · " + str(lesson.get_kind_display())))
        labels[user.pk] = {
            "student_label_sha256": digest(user.get_full_name() or user.username),
            "item_sha256_by_point": {k: sorted(v) for k, v in items.items()},
        }
    audits = list(thin_audits)
    changes = []
    for row in values:
        if _scope is None:
            projected, matched = project_audit(row, labels)
        else:
            projected, matched = project_audit(row, labels, _cases=cases, _undo_operation=undo_operation)
        projected = {
            **projected,
            "projection": "parsed_audit",
            "json_hash_policy": thin_spec.JSON_PYTHON_POLICY,
            "row_hash_policy": thin_spec.ROW_SQL_POLICY,
            "source_raw_bytes": row["_raw_bytes"],
        }
        audits.append(projected)
        changes.extend(matched)
    if len(changes) > MAX_ROWS:
        raise ValueError("four_cell_change_budget_exceeded")
    evidence = []
    correction_ids = []
    lesson_correction_ids = []
    queries = {
        "registrar.JournalCorrection": model("registrar.JournalCorrection").objects.filter(
            organization_id=ORG, lesson_ref__in=lessons, enrollment_ref__in=enrs
        ),
        "registrar.LessonCorrection": model("registrar.LessonCorrection").objects.filter(
            organization_id=ORG, lesson_id__in=lessons
        ),
        "registrar.JournalHygieneDecision": model("registrar.JournalHygieneDecision").objects.filter(
            organization_id=ORG, enrollment_id__in=enrs
        ),
        "registrar.LegacyGradeFact": model("registrar.LegacyGradeFact").objects.filter(
            organization_id=ORG,
            source_system="myedu_mariadb",
            source_table__in=["journals_dates_points", "journals_dates_points_archive"],
            source_pk__in=cases,
        ),
        "registrar.LegacyGradeArtifact": model("registrar.LegacyGradeArtifact").objects.filter(
            organization_id=ORG,
            source_system="myedu_mariadb",
            source_table__in=["journals_dates_points", "journals_dates_points_archive"],
            source_pk__in=cases,
        ),
    }
    fields = {
        "id",
        "organization_id",
        "created_at",
        "updated_at",
        "lesson_id",
        "lesson_ref",
        "enrollment_id",
        "enrollment_ref",
        "lesson_mark_id",
        "lesson_mark_ref",
        "source_pk",
        "source_table",
        "source_row_hash",
        "source_snapshot_sha256",
        "materialization_digest",
        "old_status",
        "new_status",
        "evidence_kind",
        "mapping_status",
        "is_archive",
        "old_score",
        "new_score",
        "created_mark",
        "is_deletion",
        "reverted_at",
        "reverted_by_id",
        "decided_by_id",
        "corrected_by_id",
    }
    for label, qs in queries.items():
        selected = fields & {f.attname for f in qs.model._meta.concrete_fields}
        for row in bounded(annotated(qs.order_by("pk")).values(*sorted(selected), "_raw_sha")):
            if label == "registrar.JournalCorrection":
                correction_ids.append(row["id"])
            if label == "registrar.LessonCorrection":
                lesson_correction_ids.append(row["id"])
            for key in ("old_status", "new_status"):
                if key in row and row[key] not in (
                    "",
                    "present",
                    "absent",
                    "excused",
                    None,
                ):
                    row[key + "_sha256"] = digest(row[key])
                    row[key] = None
            for key in (
                "source_row_hash",
                "source_snapshot_sha256",
                "materialization_digest",
            ):
                if key in row and not re.fullmatch(r"[a-f0-9]{64}", row[key] or ""):
                    row[key + "_invalid_sha256"] = digest(row[key])
                    row[key] = None
            for key in ("evidence_kind", "mapping_status"):
                if key in row:
                    allowed = {str(value) for value, _ in qs.model._meta.get_field(key).choices}
                    if row[key] not in allowed:
                        row[key + "_sha256"] = digest(row[key])
                        row[key] = None
            row["model_label"] = label
            row["raw_record_sha256"] = row.pop("_raw_sha")
            evidence.append(row)
    reversal = (
        model("registrar.CorrectionReversal")
        .objects.filter(organization_id=ORG)
        .filter(Q(journal_correction_id__in=correction_ids) | Q(lesson_correction_id__in=lesson_correction_ids))
    )
    for row in bounded(
        annotated(reversal.order_by("pk")).values(
            "id",
            "organization_id",
            "created_at",
            "updated_at",
            "journal_correction_id",
            "lesson_correction_id",
            "reverted_by_id",
            "_raw_sha",
        )
    ):
        row["model_label"] = "registrar.CorrectionReversal"
        row["raw_record_sha256"] = row.pop("_raw_sha")
        evidence.append(row)
    key_sets = {
        "worker": ["23", "713"],
        "student": ["9354", "8220", "8222", "8247"],
        "lesson_subject": ["5", "1493"],
        "group_unit": ["812", "765"],
        "course_offering": ["NcAA2ymEa8:812", "knqwDXQuIs:765"],
        "journal_enrollment": [
            "NcAA2ymEa8:9354",
            "knqwDXQuIs:8220",
            "knqwDXQuIs:8222",
            "knqwDXQuIs:8247",
        ],
        "journal_marks": ["NcAA2ymEa8", "knqwDXQuIs"],
    }
    if _scope is not None:
        key_sets = _scope.source_keys
    source_keys = Q()
    for entity, keys in key_sets.items():
        source_keys |= Q(entity_type=entity, legacy_pk__in=keys)
    ledger = []
    source_query = (
        model("legacy_import.LegacyEntityMap")
        .objects.filter(source_keys, organization_id=ORG, source_system="myedu_mariadb")
        .order_by("pk")
    )
    for row in bounded(
        annotated(source_query).values(
            "id",
            "organization_id",
            "entity_type",
            "legacy_pk",
            "target_model_label",
            "target_pk",
            "state",
            "source_row_hash",
            "_raw_sha",
        )
    ):
        if row["target_model_label"] not in {
            "auth.user",
            "registrar.subject",
            "organizations.orgunit",
            "registrar.courseoffering",
            "registrar.enrollment",
            "registrar.lessonmark",
        }:
            row["target_model_label_sha256"] = digest(row["target_model_label"])
            row["target_model_label"] = None
        if not re.fullmatch(
            r"[0-9]{1,12}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
            row["target_pk"] or "",
        ):
            row["target_pk_sha256"] = digest(row["target_pk"])
            row["target_pk"] = None
        if row["state"] not in {
            "migrated",
            "unresolved",
            "skipped",
            "conflict",
            "failed",
            "staged",
        }:
            row["state_sha256"] = digest(row["state"])
            row["state"] = None
        if not re.fullmatch(r"[a-f0-9]{64}", row["source_row_hash"] or ""):
            row["invalid_source_row_hash_sha256"] = digest(row["source_row_hash"])
            row["source_row_hash"] = None
        row["raw_record_sha256"] = row.pop("_raw_sha")
        ledger.append(row)
    result = {
        prefix + "_ledger": ledger,
        prefix + "_audits": audits,
        prefix + "_changes": changes,
        prefix + "_evidence": evidence,
        prefix
        + "_scope": [
            {
                "organization_id": ORG,
                "fixed_cases_sha256": digest(cases),
                "case_ids": sorted(cases),
                "available_scope_collected": True,
                "audit_rows": len(audits),
                "audit_projection_version": 2,
                "source_audit_raw_bytes": sum(row["_raw_bytes"] for row in pre),
                "raw_parser_source_bytes": raw_bytes,
                "thin_projection_bytes": thin_bytes,
                "verified_workload_receipts": len(thin_audits),
                "raw_parsed_audits": len(values),
                "matched_change_rows": len(changes),
                "unresolved_scope_rows": sum(r["unresolved_scope_row"] for r in audits),
                "audit_is_best_effort": True,
                "absence_of_audit_is_not_proof_of_no_deletion": True,
                "automatic_apply_authority": False,
                "tenant_unlocatable_mark_delete_audits": model("audit.AuditLog")
                .objects.filter(
                    organization_id=ORG,
                    action__iexact="delete",
                    resource_type__in=["registrar.LessonMark", "registrar.lessonmark"],
                )
                .exclude(query)
                .count(),
                "tenant_deleted_lesson_corrections_unlocatable": model("registrar.LessonCorrection")
                .objects.filter(organization_id=ORG, lesson_id__isnull=True)
                .count(),
            }
        ],
    }

    if _scope is not None:
        result[prefix + "_scope"][0]["tenant_unlocatable_lesson_delete_audits"] = (
            model("audit.AuditLog")
            .objects.filter(
                organization_id=ORG,
                action__iexact="delete",
                resource_type__in=["registrar.Lesson", "registrar.lesson"],
            )
            .exclude(query)
            .count()
        )
    return result
