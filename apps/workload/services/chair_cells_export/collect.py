"""Explicit field schemas; no auth/profile rows or arbitrary model serialization."""

import re

from django.apps import apps
from django.db.models import Q

from ..scoped_snapshot import SnapshotError
from ..scoped_snapshot.data import ORG
from .evidence import SCHEMAS as EVIDENCE_SCHEMAS
from .evidence import collect_evidence
from .spec import MAX_MARKS, MAX_OFFERINGS, MAX_ROWS, PERIOD

SCHEMAS = {
    "offerings": (
        "id",
        "organization_id",
        "subject_id",
        "period_id",
        "group_id",
        "instructor_id",
        "lesson_hours",
        "is_active",
        "created_at",
        "updated_at",
    ),
    "enrollments": (
        "id",
        "organization_id",
        "student_id",
        "offering_id",
        "kind",
        "status",
        "superseded_by_id",
        "source_group_id",
        "added_by_id",
        "absence_hours",
        "created_at",
        "updated_at",
    ),
    "lessons": (
        "id",
        "organization_id",
        "offering_id",
        "date",
        "kind",
        "topic",
        "hours",
        "start_time",
        "end_time",
        "created_by_id",
        "instructor_id",
        "room_id",
        "syllabus_week",
        "is_legacy_synthesised",
        "created_at",
        "updated_at",
    ),
    "marks": (
        "id",
        "organization_id",
        "lesson_id",
        "enrollment_id",
        "status",
        "score",
        "entered_by_id",
        "created_at",
        "updated_at",
    ),
    "ledger": (
        "id",
        "organization_id",
        "source_system",
        "entity_type",
        "legacy_pk",
        "target_model_label",
        "target_pk",
        "state",
        "source_row_hash",
        "created_at",
        "updated_at",
    ),
}

SCHEMAS.update(EVIDENCE_SCHEMAS)


def model(name):
    return apps.get_model("registrar", name)


def bounded(query, schema, limit=MAX_ROWS):
    result = list(query.order_by("id").values(*schema)[: limit + 1])
    if len(result) > limit:
        raise SnapshotError("row_budget_exceeded")
    return result


def collect(spec):
    selected = {row["id"] for row in spec["offerings"]}
    offering = model("CourseOffering")
    scoped = offering.objects.filter(organization_id=ORG, period_id=PERIOD)
    if scoped.filter(id__in=selected).count() != len(selected):
        raise SnapshotError("pinned_offering_scope_changed")
    enrollment = model("Enrollment")
    # Include the complete same-period supersession closure, both directions. Never
    # silently truncate history; split/review the pinned batch when it exceeds25.
    course_ids = set(selected)
    while True:
        seeds = enrollment.objects.filter(organization_id=ORG, offering_id__in=course_ids)
        linked = enrollment.objects.filter(organization_id=ORG).filter(
            Q(id__in=seeds.values("superseded_by_id")) | Q(superseded_by__in=seeds.values("id"))
        )
        linked_ids = set(linked.values_list("offering_id", flat=True))
        found = course_ids | {str(pk) for pk in linked_ids}
        if found == course_ids:
            break
        if len(found) > MAX_OFFERINGS:
            raise SnapshotError("history_course_budget_exceeded_split_batch")
        if scoped.filter(id__in=found).count() != len(found):
            raise SnapshotError("history_tenant_or_period_mismatch")
        course_ids = found
    data = {
        "offerings": bounded(scoped.filter(id__in=course_ids), SCHEMAS["offerings"], MAX_OFFERINGS),
        "enrollments": bounded(
            enrollment.objects.filter(organization_id=ORG, offering_id__in=course_ids), SCHEMAS["enrollments"]
        ),
        "lessons": bounded(
            model("Lesson").objects.filter(organization_id=ORG, offering_id__in=course_ids), SCHEMAS["lessons"]
        ),
    }
    lesson_ids = {row["id"] for row in data["lessons"]}
    enrollment_ids = {row["id"] for row in data["enrollments"]}
    if any(
        r["superseded_by_id"] is not None and r["superseded_by_id"] not in enrollment_ids for r in data["enrollments"]
    ):
        raise SnapshotError("supersession_reference_outside_scope")
    marks = (
        model("LessonMark")
        .objects.filter(organization_id=ORG)
        .filter(Q(lesson_id__in=lesson_ids) | Q(enrollment_id__in=enrollment_ids))
    )
    data["marks"] = bounded(marks, SCHEMAS["marks"], MAX_MARKS)
    if any(m["lesson_id"] not in lesson_ids or m["enrollment_id"] not in enrollment_ids for m in data["marks"]):
        raise SnapshotError("mark_outside_history_closure")
    # Source keys must be typed opaque numeric/UUID keys, never free-form payload.
    targets = Q()
    for label, rows in (
        ("courseoffering", data["offerings"]),
        ("enrollment", data["enrollments"]),
        ("lesson", data["lessons"]),
        ("lessonmark", data["marks"]),
    ):
        targets |= Q(target_model_label=f"registrar.{label}", target_pk__in=[str(r["id"]) for r in rows])
    users = {str(r["student_id"]) for r in data["enrollments"]}
    for rows, fields in (
        (data["offerings"], ("instructor_id",)),
        (data["lessons"], ("instructor_id", "created_by_id")),
        (data["marks"], ("entered_by_id",)),
    ):
        users.update(str(r[f]) for r in rows for f in fields if r[f] is not None)
    targets |= Q(target_model_label="auth.user", target_pk__in=users)
    for label, field in (("registrar.subject", "subject_id"), ("organizations.orgunit", "group_id")):
        targets |= Q(
            target_model_label=label, target_pk__in=[str(r[field]) for r in data["offerings"] if r[field] is not None]
        )
    ledger = apps.get_model("legacy_import", "LegacyEntityMap")
    data["ledger"] = bounded(
        ledger.objects.filter(targets, organization_id=ORG, source_system="myedu_mariadb"), SCHEMAS["ledger"]
    )
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,254}", r["legacy_pk"]) for r in data["ledger"]):
        raise SnapshotError("ledger_source_key_schema_unsafe")
    evidence = collect_evidence(data, model=model, bounded=bounded)
    if sum(map(len, data.values())) > MAX_ROWS:
        raise SnapshotError("total_row_budget_exceeded")
    return data, evidence
