"""Restore only the source-proven Thursday slot for MR77's 634 Interior group."""

import datetime as dt
import hashlib
import json

from django.db import transaction

from . import schedule_lock, schedule_manage, schedule_manage_actions
from .models import CourseOffering, Lesson, LessonMark, ScheduleSlot

OFFERING = "d1f52385-239d-4c91-b60d-121188710f45"
GROUP = "edb4810e-945c-4d91-a0bc-2bd8034c3cea"
SUBJECT = "eda11aed-9333-423d-b9ed-b5682ac38214"
TEACHER = 8106
PAYLOAD = {"weekday": 4, "time_slot": "11:50|13:20", "kind": "seminar", "week_type": "all", "room": ""}


class RepairError(ValueError):
    pass


def state(organization):
    return {
        "lessons": list(Lesson.objects.filter(organization=organization, offering_id=OFFERING).order_by("pk").values()),
        "marks": list(
            LessonMark.objects.filter(organization=organization, lesson__offering_id=OFFERING).order_by("pk").values()
        ),
        "slots": list(
            ScheduleSlot.all_objects.filter(organization=organization, offering_id=OFFERING).order_by("pk").values()
        ),
    }


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline=""):
    if not user.is_active or not user.is_superuser:
        raise RepairError("active_superadmin_required")
    offering = (
        CourseOffering.objects.select_for_update(of=("self",))
        .select_related("period", "organization", "instructor", "subject", "group")
        .get(pk=OFFERING, organization=organization)
    )
    if str(offering.group_id) != GROUP or str(offering.subject_id) != SUBJECT or offering.instructor_id != TEACHER:
        raise RepairError("offering_identity_changed")
    schedule_lock.lock_for_offering(offering)
    slots = list(ScheduleSlot.objects.filter(organization=organization, offering=offering, is_parked=False))
    exact = [
        s
        for s in slots
        if s.weekday == 4
        and s.start_time == dt.time(11, 50)
        and s.end_time == dt.time(13, 20)
        and s.kind == "seminar"
        and s.week_type == "all"
        and s.instructor_id in (None, TEACHER)
    ]
    if len(exact) > 1:
        raise RepairError("duplicate_target_slots")
    before = state(organization)
    baseline = hashlib.sha256(json.dumps(before, sort_keys=True, default=str).encode()).hexdigest()
    result = {"baseline": baseline, "already_present": len(exact), "pending": int(not exact)}
    if exact:
        return result
    cleaned, errors = schedule_manage.parse_payload(PAYLOAD)
    if errors or schedule_manage.check_slot(offering=offering, cleaned=cleaned):
        raise RepairError("schedule_conflict_or_invalid")
    if not apply:
        return result
    if expected_baseline != baseline:
        raise RepairError("baseline_changed")
    try:
        created = schedule_manage_actions.create_slot(
            actor=user, organization=organization, offering=offering, data=PAYLOAD
        )
    except schedule_manage_actions.ScheduleManageError as exc:
        raise RepairError("canonical_schedule_rejected") from exc
    after = state(organization)
    after["slots"] = [s for s in after["slots"] if str(s["id"]) != created["id"]]
    if after != before:
        raise RepairError("existing_data_changed")
    return {**result, "applied": 1}
