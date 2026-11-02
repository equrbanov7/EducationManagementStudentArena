"""One exact teacher-confirmed scheduled lesson; metadata only, full graph and exact undo."""

import copy
import datetime as dt
import uuid

from django.apps import apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.reviewed_graph import digest, graph, require, rows

from . import schedule_lock
from .models import CourseOffering, Lesson, LessonMark, ScheduleSlot

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OFFERING = "3326514c-9fe5-4bc0-8167-3f949fa9a054"
GROUP = "0a1783b0-1f13-41ff-bbeb-51652b68b70d"
SUBJECT = "86f4817f-802b-43ec-9774-ec7f869a35ad"
TEACHER = 8420
LESSON = "6a2f801f-a770-48c2-aa3c-73043c461865"
SLOT = "c7b0d9bc-03fa-4398-a676-4a9747b73b1d"
ROOM = 379
REASON = "Cədvələ aiddir bu dərs"
RESOURCE = "registrar.reviewed_nezife_scheduled_label_v1"


def snapshot(organization, user):
    require(
        str(organization.pk) == ORG and organization.is_active and user.is_active and user.is_superuser,
        "nezife_actor_scope",
    )
    require(
        apps.get_model("auth.User")
        .objects.select_for_update()
        .filter(pk=user.pk, is_active=True, is_superuser=True)
        .exists(),
        "nezife_actor_scope",
    )
    require(
        apps.get_model("organizations.Organization")
        .objects.select_for_update()
        .filter(pk=ORG, is_active=True, status="active")
        .exists(),
        "nezife_actor_tenant",
    )
    profile = apps.get_model("accounts.UserProfile").objects.select_for_update().get(user=user)
    require(
        str(profile.organization_id) == ORG
        and profile.access_state == "active"
        and not profile.is_deleted
        and profile.blocked_at is None,
        "nezife_actor_tenant",
    )
    schedule_lock.lock_schedule(ORG, PERIOD)
    course = (
        CourseOffering.objects.select_for_update(of=("self",))
        .select_related("period", "group", "subject", "instructor__profile")
        .get(pk=OFFERING, organization=organization)
    )
    require(
        str(course.period_id) == PERIOD
        and str(course.group_id) == GROUP
        and str(course.subject_id) == SUBJECT
        and course.instructor_id == TEACHER
        and course.is_active
        and not course.is_intensive,
        "nezife_course_changed",
    )
    require(
        course.period.is_active
        and course.period.is_current
        and course.period.locked_at is None
        and course.period.organization_id == organization.pk
        and course.group.organization_id == organization.pk
        and course.subject.organization_id == organization.pk,
        "nezife_scope_changed",
    )
    require(
        (
            course.instructor.username,
            course.instructor.first_name,
            course.instructor.last_name,
            course.instructor.profile.patronymic,
        )
        == ("nezife.asirova", "Nəzifə", "Aşırova", "Vilayət"),
        "nezife_teacher_changed",
    )
    lesson = Lesson.objects.select_for_update().get(pk=LESSON, offering=course, organization=organization)
    require(
        lesson.date == dt.date(2026, 10, 21)
        and lesson.start_time == dt.time(11, 50)
        and lesson.end_time == dt.time(13, 20)
        and lesson.kind == "seminar"
        and lesson.hours == 2
        and lesson.instructor_id == TEACHER
        and lesson.room_id == ROOM
        and lesson.off_schedule_reason in (REASON, ""),
        "nezife_lesson_changed",
    )
    slot = ScheduleSlot.objects.select_for_update().get(pk=SLOT, offering=course, organization=organization)
    require(
        slot.weekday == lesson.date.isoweekday() == 3
        and slot.start_time == lesson.start_time
        and slot.end_time == lesson.end_time
        and slot.kind == lesson.kind
        and slot.week_type == "all"
        and not slot.is_parked
        and not slot.is_deleted
        and slot.instructor_id in (None, TEACHER)
        and slot.room == "53",
        "nezife_schedule_changed",
    )
    room_model = Lesson._meta.get_field("room").remote_field.model
    room = room_model.objects.select_for_update().get(pk=ROOM)
    require(str(room.organization_id) == ORG and room.name == "53", "nezife_room_changed")
    require(
        LessonMark.objects.filter(lesson=lesson, organization=organization).count() == 21,
        "nezife_mark_inventory_changed",
    )
    roots = {"registrar.CourseOffering": [OFFERING]}
    student_ids = course.enrollments.values_list("student_id", flat=True)
    roots["registrar.StudentAcademicRecord"] = (
        apps.get_model("registrar.StudentAcademicRecord")
        .objects.filter(organization=organization, student_id__in=student_ids)
        .values_list("pk", flat=True)
    )
    return {
        "graph": graph(roots, organization_id=ORG),
        "period": rows(course.period.__class__.objects.filter(pk=PERIOD)),
        "group": rows(course.group.__class__.objects.filter(pk=GROUP)),
        "subject": rows(course.subject.__class__.objects.filter(pk=SUBJECT)),
        "room": rows(room_model.objects.filter(pk=ROOM)),
        "reason": lesson.off_schedule_reason,
    }


def protected(value):
    value = copy.deepcopy(value)
    value["reason"] = ""
    for row in value["graph"]["registrar.Lesson"]:
        if row["id"] == LESSON:
            row["off_schedule_reason"] = ""
    return value


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline="", undo=""):
    require(type(apply) is bool, "nezife_explicit_mode")
    before = snapshot(organization, user)
    baseline = digest(before)
    logs = (
        apps.get_model("audit.AuditLog")
        .objects.select_for_update()
        .filter(organization=organization, resource_type=RESOURCE)
    )
    previous = logs.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    if undo:
        require(previous is not None and previous.resource_id == undo, "nezife_exact_receipt")
        reversed_row = logs.filter(new_values__operation="undo", new_values__undo_of=undo).first()
        if reversed_row:
            require(
                before["reason"] == REASON and reversed_row.new_values["after_sha256"] == baseline,
                "nezife_undo_changed",
            )
            return dict(status="already_undone", applied=False, count=0, baseline=baseline, receipt=undo)
        require(not before["reason"] and previous.new_values["after_sha256"] == baseline, "nezife_undo_changed")
    elif not before["reason"]:
        require(previous is not None and previous.new_values["after_sha256"] == baseline, "nezife_unreceipted_clear")
        return dict(status="already_applied", applied=False, count=0, baseline=baseline, receipt=previous.resource_id)
    else:
        require(previous is None, "nezife_prior_receipt_review")
    result = dict(status="dry_run", applied=False, count=1, baseline=baseline, receipt=None)
    if not apply:
        return result
    require(expected_baseline == baseline, "nezife_fresh_baseline")
    desired = REASON if undo else ""
    changed = Lesson.objects.filter(pk=LESSON, organization=organization, off_schedule_reason=before["reason"]).update(
        off_schedule_reason=desired
    )
    require(changed == 1, "nezife_exact_write_count")
    after = snapshot(organization, user)
    require(protected(before) == protected(after), "nezife_academic_graph_changed")
    if undo:
        require(digest(after) == previous.old_values["before_sha256"], "nezife_exact_undo_failed")
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Nəzifə336F2: exact21Oct scheduled seminar; clear stale off-schedule label only, academic graph unchanged.",
        old_values={"before_sha256": baseline, "off_schedule_reason": before["reason"]},
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "after_sha256": digest(after),
            "protected_sha256": digest(protected(after)),
        },
    )
    return {**result, "status": "undone" if undo else "applied", "applied": True, "receipt": receipt}
