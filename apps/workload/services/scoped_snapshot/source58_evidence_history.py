"""Available Source58 history, exact pinned workload receipts and explicit unknowns."""

import json
import re

from django.db import connection
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL
from django.utils.translation import override

from ..reviewed_leyla_catalog_graph import model, normal
from . import source58_evidence_spec as fixed
from . import workload_audit_receipt_spec as thin_spec
from . import workload_audit_receipts as thin
from .four_cell_history import annotated, digest, project_audit
from .recovery_audit_scope import audit_locator
from .source58_evidence_rows import MAX_ROWS, EvidenceLimit

MAX_AUDIT_ROWS = 1000
MAX_RAW_AUDIT_BYTES = 8 * 1024 * 1024
AUDIT_REFERENCE_CHUNK = 64


def _labels(cases):
    labels = {}
    for user in (
        model("auth.User")
        .objects.filter(pk__in={c["student_id"] for c in cases.values()}, profile__organization_id=fixed.ORG)
        .only("id", "first_name", "last_name", "username")
    ):
        items = {}
        for point, case in cases.items():
            if case["student_id"] != user.pk:
                continue
            items[point] = set()
            lesson = model("registrar.Lesson")(date=case["date"], kind=case["kind"])
            for language in ("az", "en", "ru", "tr", "de"):
                with override(language):
                    items[point].add(digest(case["date"] + " · " + str(lesson.get_kind_display())))
        labels[user.pk] = {
            "student_label_sha256": digest(user.get_full_name() or user.username),
            "item_sha256_by_point": {key: sorted(values) for key, values in items.items()},
        }
    return labels


def collect_history(*, referenced_ids):
    cases = fixed.HISTORY_SCOPE.cases
    locator = audit_locator(cases) | Q(resource_id__in=referenced_ids)
    Audit = model("audit.AuditLog")
    table = connection.ops.quote_name(Audit._meta.db_table)
    ordered_ids = sorted(referenced_ids)
    # PostgreSQL's regex compiler allocates a superlinear transition matrix for
    # thousands of alternatives. Small fixed chunks bound compilation memory.
    patterns = [
        "(" + "|".join(re.escape(pk) for pk in ordered_ids[start : start + AUDIT_REFERENCE_CHUNK]) + ")"
        for start in range(0, len(ordered_ids), AUDIT_REFERENCE_CHUNK)
    ]
    points = "(^|[^0-9])(" + "|".join(str(point) for point in sorted(cases)) + ")([^0-9]|$)"
    if sum(len(pattern.encode()) for pattern in patterns) > 1024 * 1024:
        raise EvidenceLimit("source58_audit_locator_byte_budget")
    for field in ("changes", "old_values", "new_values"):
        for pattern in patterns:
            locator |= Q(RawSQL(f"COALESCE({table}.{field}::text ~ %s, FALSE)", [pattern], output_field=BooleanField()))
        locator |= Q(
            RawSQL(
                f"COALESCE({table}.{field}::text ~ %s, FALSE)",
                [points],
                output_field=BooleanField(),
            )
        )
    query = Audit._base_manager.filter(organization_id=fixed.ORG).filter(locator).order_by("created_at", "pk")
    pre = list(annotated(query).values("id", "_raw_bytes", "_raw_sha")[: MAX_AUDIT_ROWS + 1])
    if len(pre) > MAX_AUDIT_ROWS:
        raise EvidenceLimit("source58_audit_row_budget")
    pinned = {str(row["id"]) for row in pre} & thin_spec.PINS.keys()
    for row in pre:
        if str(row["id"]) in pinned and row["_raw_sha"] != thin_spec.PINS[str(row["id"])][1]:
            raise EvidenceLimit("source58_pinned_workload_receipt_changed")
    ordinary = [row for row in pre if str(row["id"]) not in pinned]
    raw_bytes = sum(row["_raw_bytes"] for row in ordinary)
    if raw_bytes > MAX_RAW_AUDIT_BYTES or any(row["_raw_bytes"] > 1024 * 1024 for row in ordinary):
        # A generic resource prefix can never exempt an unknown large/masked grade event.
        raise EvidenceLimit("source58_unknown_audit_byte_budget")
    thin_rows = thin.preview(annotated(query.filter(pk__in=pinned)))
    if {str(row["id"]) for row in thin_rows} != pinned:
        raise EvidenceLimit("source58_pinned_workload_receipt_scope_changed")
    try:
        audits = [thin.project(row) for row in thin_rows]
    except ValueError as exc:
        raise EvidenceLimit("source58_pinned_receipt_semantics_unverified") from exc
    values = list(
        annotated(query.exclude(pk__in=pinned)).values(
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
        )[: MAX_AUDIT_ROWS + 1]
    )
    labels, changes = _labels(cases), []
    for row in values:
        try:
            projected, matched = project_audit(
                row, labels, _cases=cases, _undo_operation=fixed.HISTORY_SCOPE.undo_operation
            )
        except ValueError as exc:
            raise EvidenceLimit("source58_audit_shape_budget_or_invalid_structure") from exc
        projected.update(projection="parsed_audit", source_raw_bytes=row["_raw_bytes"])
        audits.append(projected)
        for change in matched:
            # Existing parser needs numbers to distinguish a clear from an untouched blank;
            # exact grades never enter the exported Source58 projection.
            change.pop("old_numeric", None)
            change.pop("new_numeric", None)
            changes.append(change)
    if len(changes) > MAX_ROWS or raw_bytes + len(json.dumps(audits, default=str).encode()) > MAX_RAW_AUDIT_BYTES:
        raise EvidenceLimit("source58_history_projection_budget")
    unknown = (
        Audit._base_manager.filter(organization_id=fixed.ORG, action__iexact="delete")
        .filter(
            resource_type__in=("registrar.LessonMark", "registrar.lessonmark", "registrar.Lesson", "registrar.lesson")
        )
        .exclude(locator)
    )
    unlocated_grade = Audit._base_manager.filter(
        organization_id=fixed.ORG,
        resource_type__in=("registrar.grade.mark", "registrar.grade.full-edit"),
    ).exclude(locator)
    unlocated_rows = list(
        annotated(unlocated_grade)
        .order_by("pk")
        .values("id", "created_at", "user_id", "action", "_raw_sha", "_raw_bytes")[: MAX_AUDIT_ROWS + 1]
    )
    if len(unlocated_rows) > MAX_AUDIT_ROWS:
        raise EvidenceLimit("source58_unlocatable_grade_history_budget")
    return {
        "source58_history_audits": normal(audits),
        "source58_history_changes": normal(changes),
        "source58_unlocatable_grade_history": [
            dict(normal(row), unresolved_history_hold=True) for row in unlocated_rows
        ],
        "source58_history_coverage": [
            {
                "available_scope_collected": True,
                "history_is_best_effort": True,
                "absence_of_audit_is_not_proof_of_no_deletion": True,
                "unlocatable_delete_audits": unknown.count(),
                "unlocatable_grade_history_rows": len(unlocated_rows),
                "unresolved_scope_rows": sum(row["unresolved_scope_row"] for row in audits),
                "verified_pinned_workload_receipts": len(thin_rows),
                "ordinary_audit_rows": len(values),
                "ordinary_audit_raw_bytes": raw_bytes,
                "all_grade_history_resolved": False,
                "unknown_masked_history_remains_hold": True,
            }
        ],
    }
