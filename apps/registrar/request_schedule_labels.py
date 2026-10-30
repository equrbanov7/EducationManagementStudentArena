"""MR116/117: exact teacher-confirmed lesson labels, without calendar inference."""

import datetime as dt
import hashlib
import json

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from .models import CourseOffering, Lesson, LessonMark

OFFERING = "f16f9692-eb86-443a-b4b5-b0791c3adbfe"
TEACHER = "shahbaz.shireliyev"
CASES = {
    "f5fddd66-85c6-497d-945a-a19338128570": ("2026-10-22", "kənar dərs deyil. cədvəldə mənim dərsimdi"),
    "f0f0ec07-fd00-4a45-81e8-b2732cb88da2": ("2026-10-29", "cədvəl üzrə mənim dərsimdi"),
}


class RepairError(ValueError):
    pass


def _state(organization):
    return {
        "lessons": list(Lesson.objects.filter(organization=organization, offering_id=OFFERING).order_by("pk").values()),
        "marks": list(
            LessonMark.objects.filter(organization=organization, lesson__offering_id=OFFERING).order_by("pk").values()
        ),
    }


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline=""):
    if not user.is_active or not user.is_superuser:
        raise RepairError("active_superadmin_required")
    offering = (
        CourseOffering.objects.select_for_update(of=("self",))
        .select_related("instructor")
        .get(pk=OFFERING, organization=organization)
    )
    if offering.instructor is None or offering.instructor.username != TEACHER:
        raise RepairError("offering_teacher_changed")
    lessons = list(
        Lesson.objects.select_for_update().filter(organization=organization, offering=offering, pk__in=CASES)
    )
    if len(lessons) != 2:
        raise RepairError("exact_lessons_missing")
    for lesson in lessons:
        date, reason = CASES[str(lesson.pk)]
        if (
            lesson.date.isoformat() != date
            or lesson.start_time != dt.time(11, 50)
            or lesson.kind != "seminar"
            or lesson.hours != 2
            or lesson.instructor_id not in (None, offering.instructor_id)
            or lesson.off_schedule_reason not in ("", reason)
        ):
            raise RepairError("lesson_source_changed")
    before = _state(organization)
    baseline = hashlib.sha256(json.dumps(before, sort_keys=True, default=str).encode()).hexdigest()
    pending = [lesson for lesson in lessons if lesson.off_schedule_reason]
    result = {"baseline": baseline, "pending": len(pending), "already_present": 2 - len(pending)}
    if not apply or not pending:
        return result
    if expected_baseline != baseline:
        raise RepairError("baseline_changed")
    for lesson in pending:
        old = lesson.off_schedule_reason
        Lesson.objects.filter(pk=lesson.pk, organization=organization).update(off_schedule_reason="")
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            resource_type="registrar.request_schedule_label",
            resource_id=str(lesson.pk),
            reason="MR116/MR117: teacher confirms these exact dates are scheduled lessons; no recurring timetable inferred",
            old_values={"off_schedule_reason": old},
            new_values={"off_schedule_reason": "", "baseline": baseline},
        )
    expected = json.loads(json.dumps(before, default=str))
    for row in expected["lessons"]:
        if str(row["id"]) in CASES:
            row["off_schedule_reason"] = ""
    if json.loads(json.dumps(_state(organization), default=str)) != expected:
        raise RepairError("academic_data_changed")
    return {**result, "applied": len(pending)}
