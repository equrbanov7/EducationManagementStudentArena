"""Scoped correction evidence without notes, names, documents or arbitrary JSON."""

from django.db.models import BooleanField, Case, F, Q, Value, When

from ..scoped_snapshot.data import ORG

COMMON = ("id", "organization_id", "created_at", "updated_at")
CORRECTION = COMMON + ("reason", "corrected_by_id", "note_present")
SCHEMAS = {
    "journal_corrections": CORRECTION
    + (
        "lesson_mark_id",
        "lesson_mark_ref",
        "lesson_ref",
        "enrollment_ref",
        "field",
        "old_status",
        "new_status",
        "old_score",
        "new_score",
        "created_mark",
    ),
    "lesson_corrections": CORRECTION
    + (
        "lesson_id",
        "is_deletion",
        "old_date",
        "new_date",
        "old_kind",
        "new_kind",
        "old_hours",
        "new_hours",
        "old_instructor_id",
        "new_instructor_id",
    ),
    "selfwork_corrections": CORRECTION
    + ("topic_id", "enrollment_id", "old_done", "new_done", "old_points", "new_points"),
    "coursework_corrections": CORRECTION + ("enrollment_id", "old_score", "new_score", "old_date", "new_date"),
    "component_corrections": CORRECTION + ("component_id", "enrollment_id", "old_score", "new_score"),
    "correction_reversals": COMMON
    + (
        "journal_correction_id",
        "lesson_correction_id",
        "selfwork_correction_id",
        "coursework_correction_id",
        "component_correction_id",
        "reverted_by_id",
        "reason_code",
        "note_present",
    ),
    "hygiene_decisions": COMMON
    + (
        "enrollment_id",
        "batch",
        "category",
        "reason_code",
        "reason_code_known",
        "from_status",
        "to_status",
        "evidence_digest",
        "decided_by_id",
        "reverted_at",
        "reverted_by_id",
        "note_present",
        "revert_note_present",
    ),
}
HYGIENE_CODES = (
    "archived",
    "expelled",
    "academic_leave",
    "graduated",
    "inactive_record",
    "period_ended",
    "no_record",
    "cancelled_offering",
    "replaced_elective",
    "not_in_curriculum",
    "legacy_no_result",
    "unexplained",
    "no_exam_result",
    "subject_exempt",
)


def present(field):
    return Case(When(**{field: ""}, then=Value(False)), default=Value(True), output_field=BooleanField())


def collect_evidence(data, *, model, bounded):
    lessons = {r["id"] for r in data["lessons"]}
    enrollments = {r["id"] for r in data["enrollments"]}
    courses = {r["id"] for r in data["offerings"]}
    gaps = {}
    journal = (
        model("JournalCorrection")
        .objects.filter(organization_id=ORG)
        .filter(Q(lesson_ref__in=lessons) | Q(enrollment_ref__in=enrollments))
    )
    safe_journal = journal.filter(lesson_ref__in=lessons, enrollment_ref__in=enrollments)
    gaps["journal_correction_outside_captured_refs"] = journal.exclude(id__in=safe_journal.values("id")).count()
    queries = {
        "journal_corrections": safe_journal,
        "lesson_corrections": model("LessonCorrection").objects.filter(organization_id=ORG, lesson_id__in=lessons),
        "selfwork_corrections": model("SelfWorkCorrection").objects.filter(
            organization_id=ORG, enrollment_id__in=enrollments
        ),
        "coursework_corrections": model("CourseWorkCorrection").objects.filter(
            organization_id=ORG, enrollment_id__in=enrollments
        ),
        "component_corrections": model("ComponentScoreCorrection").objects.filter(
            organization_id=ORG, enrollment_id__in=enrollments
        ),
    }
    for table, relation in (("selfwork_corrections", "topic"), ("component_corrections", "component")):
        query = queries[table]
        queries[table] = query.filter(**{f"{relation}__organization_id": ORG, f"{relation}__offering_id__in": courses})
        gaps[f"{table}_outside_captured_course"] = query.exclude(id__in=queries[table].values("id")).count()
    # A deleted lesson correction has no stable course locator in this schema.
    # Count only; exporting its free-text label would be unsafe and guessing wrong.
    gaps["tenant_deleted_lesson_corrections_unlocatable"] = (
        model("LessonCorrection").objects.filter(organization_id=ORG, lesson_id__isnull=True).count()
    )
    for table, query in queries.items():
        data[table] = bounded(query.annotate(note_present=present("note")), SCHEMAS[table])
    reverse = Q()
    for table in queries:
        field = table.removesuffix("s") + "_id"
        reverse |= Q(**{f"{field}__in": [r["id"] for r in data[table]]})
    data["correction_reversals"] = bounded(
        model("CorrectionReversal")
        .objects.filter(reverse, organization_id=ORG)
        .annotate(note_present=present("reason_note")),
        SCHEMAS["correction_reversals"],
    )
    hygiene = (
        model("JournalHygieneDecision")
        .objects.filter(organization_id=ORG, enrollment_id__in=enrollments)
        .annotate(
            safe_reason_code=Case(When(reason_code__in=HYGIENE_CODES, then=F("reason_code")), default=Value("unknown")),
            reason_code_known=Case(
                When(reason_code__in=HYGIENE_CODES, then=Value(True)), default=Value(False), output_field=BooleanField()
            ),
            note_present=present("reason"),
            revert_note_present=present("revert_reason"),
        )
    )
    fields = tuple("safe_reason_code" if f == "reason_code" else f for f in SCHEMAS["hygiene_decisions"])
    rows = bounded(hygiene, fields)
    for row in rows:
        row["reason_code"] = row.pop("safe_reason_code")
    data["hygiene_decisions"] = rows
    return {
        "coverage_gaps": gaps,
        "override_proof_complete": not any(gaps.values()),
        "deleted_unlocatable_evidence_rule": "Tenant-wide count only, not assignable to this batch; retain candidate on hold.",
    }
