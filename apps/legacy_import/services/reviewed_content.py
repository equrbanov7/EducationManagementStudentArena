"""Read-only audit or atomic missing-only insert for the exact reviewed source."""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.registrar.public import gradebook
from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_content_plan as planner
from .reviewed_content_contract import ContentError, validate_payload
from .reviewed_content_spec import ORG, RESOURCE
from .reviewed_content_state import CurrentState, digest, model, protected


def _write(decision):
    # Lesson source rows have no instructor/entered_by column. Source journal
    # owner is audit provenance, never silently substituted as factual author.
    lessons = list(decision.lessons.values())
    if any(lesson.instructor_id is not None or lesson.created_by_id is not None for lesson in lessons):
        raise ContentError("unknown_source_lesson_authorship_must_stay_null")
    model("registrar.Lesson").objects.bulk_create(lessons, batch_size=200)
    if any(mark.entered_by_id is not None for mark in decision.marks):
        raise ContentError("unknown_source_mark_authorship_must_stay_null")
    model("registrar.LessonMark").objects.bulk_create(decision.marks, batch_size=500)
    gradebook.recompute_absence_hours_many(list(decision.touched.values()))


def _verify_created(state, decision):
    lesson_ids = [lesson.pk for lesson in decision.lessons.values()]
    mark_ids = [mark.pk for mark in decision.marks]
    if model("registrar.Lesson").objects.filter(organization_id=ORG, pk__in=lesson_ids).count() != len(lesson_ids):
        raise ContentError("created_source_lesson_count_mismatch")
    if model("registrar.LessonMark").objects.filter(organization_id=ORG, pk__in=mark_ids).count() != len(mark_ids):
        raise ContentError("created_source_mark_count_mismatch")
    actual_lessons = {
        str(row["id"]): row
        for row in model("registrar.Lesson")
        .objects.filter(organization_id=ORG, pk__in=lesson_ids)
        .values("id", "offering_id", "date", "start_time", "kind", "hours", "instructor_id", "created_by_id")
    }
    for lesson in decision.lessons.values():
        row = actual_lessons[str(lesson.pk)]
        if (
            str(row["offering_id"]),
            row["date"],
            row["start_time"],
            row["kind"],
            row["hours"],
            row["instructor_id"],
            row["created_by_id"],
        ) != (str(lesson.offering_id), lesson.date, lesson.start_time, lesson.kind, 2, None, None):
            raise ContentError("created_lesson_differs_from_exact_source_slot")
    actual_marks = {
        str(row["id"]): row
        for row in model("registrar.LessonMark")
        .objects.filter(organization_id=ORG, pk__in=mark_ids)
        .values("id", "lesson_id", "enrollment_id", "status", "score", "entered_by_id")
    }
    for mark in decision.marks:
        row = actual_marks[str(mark.pk)]
        if (str(row["lesson_id"]), str(row["enrollment_id"]), row["status"], row["score"], row["entered_by_id"]) != (
            str(mark.lesson_id),
            str(mark.enrollment_id),
            mark.status,
            mark.score,
            None,
        ):
            raise ContentError("created_mark_differs_from_winning_source_cell")
        if (
            str(mark.lesson.offering_id) not in state.selected
            or str(mark.enrollment.offering_id) != str(mark.lesson.offering_id)
            or str(mark.organization_id) != str(mark.enrollment.organization_id)
        ):
            raise ContentError("created_source_cell_outside_reviewed_course")


@transaction.atomic
def execute(*, data, source_sha256, user, organization, apply=False, expected_baseline=""):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise ContentError("fixed_tenant_active_superadmin_required")
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256 or ""):
        raise ContentError("source_sha256_required")
    if expected_baseline and not re.fullmatch(r"[a-f0-9]{64}", expected_baseline):
        raise ContentError("baseline_invalid")
    if apply and not expected_baseline:
        raise ContentError("fresh_live_baseline_required")
    targets = data["selected_target_ids"]
    data = validate_payload(
        {k: v for k, v in data.items() if k not in {"until_date", "selected_target_ids"}}, target_ids=targets
    )
    if data["until_date"] > timezone.localdate():
        raise ContentError("source_until_cannot_be_in_future")
    state = CurrentState(data, actor=user, lock=apply)
    before = state.fingerprint()
    baseline = digest({"source": source_sha256, "targets": targets, "current": before})
    if expected_baseline and expected_baseline != baseline:
        raise ContentError("fresh_live_baseline_changed")
    decision = planner.build(state)
    result = {"baseline": baseline, **dict(sorted(decision.counts.items()))}
    if not apply:
        return result
    if not decision.marks:
        return {**result, "already_done": 1}
    untouched = protected(state, touched=decision.touched)
    _write(decision)
    _verify_created(state, decision)
    created_lessons = [str(lesson.pk) for lesson in decision.lessons.values()]
    created_marks = [str(mark.pk) for mark in decision.marks]
    if (
        protected(state, created_lessons=created_lessons, created_marks=created_marks, touched=decision.touched)
        != untouched
    ):
        raise ContentError("existing_academic_content_roster_or_author_changed")
    # Re-audit the actual new cell keys: a repeat must propose no more inserts.
    after_state = CurrentState(data, actor=user)
    again = planner.build(after_state)
    if again.marks or again.lessons:
        raise ContentError("source_recovery_not_idempotent")
    batch = f"content-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    log_action(
        AuditAction.CREATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason="Baxılmış köhnə jurnal mənbəsindən yalnız çatışmayan xanaların bərpası",
        new_values={
            "source_sha256": source_sha256,
            "target_ids": targets,
            "before_baseline": baseline,
            "after_fingerprint": digest(after_state.fingerprint()),
            "created_lesson_ids": created_lessons,
            "created_mark_ids": created_marks,
            "source_provenance": decision.provenance,
            "counts": dict(decision.counts),
            "existing_null_authors_preserved": True,
            "existing_nonempty_conflicts_preserved": True,
            "roster_and_syllabus_authors_preserved": True,
        },
    )
    return {**result, "batch": batch, "created_lessons": len(created_lessons), "created_marks": len(created_marks)}
