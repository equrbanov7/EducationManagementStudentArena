"""Bind one reviewed workload to its existing historical journal, without copying cells."""

import hashlib
import json

from django.apps import apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason
from .row_edit import save_row_amended
from .scoping import resolve_actor

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
FILLED = "0858f3cf-76eb-47b3-8842-4098e32c17a2"
EMPTY = "2241fd3f-735a-4a78-a2c2-14ec7a7edf92"
ROW = "fd924dd7-1799-4810-a0d7-d0277f9e55a4"
TASK = "f9e57565-648f-4365-b533-db04007796d2"
FILLED_SUBJECT = "0081ceca-f270-44df-af3c-da1fe2b1ac0a"
OFFICIAL_SUBJECT = "ac53d96a-97d6-4402-b45a-6bc2da5088da"
GROUP = "4c8e770a-f2a1-4db4-8337-6bbe4505e6d4"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TEACHER = 7942
SOURCE_CELLS = "c0050f1ed290f415c00630bad378fef889e86984db7b7718e6dbfa58d78505e4"
RESOURCE = "workload.mr118_journal_binding"


class MR118Error(ValueError):
    pass


def model(name):
    return apps.get_model(name)


def rows(query):
    return list(query.order_by("pk").values())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def capture():
    offerings = model("registrar.CourseOffering").objects.filter(pk__in=(FILLED, EMPTY), organization_id=ORG)
    lessons = model("registrar.Lesson").objects.filter(offering__in=offerings)
    syllabi = model("syllabus.Syllabus").objects.filter(offering__in=offerings)
    versions = model("syllabus.SyllabusVersion").objects.filter(syllabus__in=syllabi)
    return {
        "offerings": rows(offerings),
        "lessons": rows(lessons),
        "marks": rows(model("registrar.LessonMark").objects.filter(lesson__in=lessons)),
        "enrollments": rows(model("registrar.Enrollment").objects.filter(offering__in=offerings)),
        "syllabi": rows(syllabi),
        "versions": rows(versions),
        "sections": rows(model("syllabus.SyllabusSection").objects.filter(version__in=versions)),
        "shares": rows(model("syllabus.SyllabusShare").objects.filter(offering__in=offerings)),
        "slots": rows(model("registrar.ScheduleSlot").objects.filter(offering__in=offerings)),
        "row": rows(model("workload.TeachingTaskRow").objects.filter(pk=ROW)),
        "groups": sorted(
            str(x) for x in model("workload.TeachingTaskRow").objects.get(pk=ROW).groups.values_list("pk", flat=True)
        ),
        "assignments": rows(model("workload.TeacherAssignment").objects.filter(row_id=ROW)),
        "task": rows(model("workload.TeachingTask").objects.filter(pk=TASK)),
        "subjects": rows(model("registrar.Subject").objects.filter(pk__in=(FILLED_SUBJECT, OFFICIAL_SUBJECT))),
    }


def academic(value):
    result = {k: v for k, v in value.items() if k not in ("row", "task")}
    result["row"] = [{k: v for k, v in r.items() if k not in ("subject_id", "updated_at")} for r in value["row"]]
    return result


def source_fingerprint():
    marks = (
        model("registrar.LessonMark")
        .objects.filter(organization_id=ORG, lesson__offering_id=FILLED)
        .select_related("lesson", "enrollment")
    )
    values = sorted(
        (
            str(m.lesson.date),
            str(m.lesson.start_time),
            m.lesson.kind,
            m.enrollment.student_id,
            m.status,
            None if m.score is None else str(float(m.score)),
        )
        for m in marks
    )
    return digest(values)


@transaction.atomic
def repair_mr118_journal_binding(*, organization, user, apply=False, expected_baseline="", undo=False):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise MR118Error("fixed_tenant_active_superadmin_required")
    offerings = {
        str(o.pk): o
        for o in model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(pk__in=(FILLED, EMPTY), organization_id=ORG)
    }
    if set(offerings) != {FILLED, EMPTY}:
        raise MR118Error("fixed_offerings_missing")
    for oid, subject in ((FILLED, FILLED_SUBJECT), (EMPTY, OFFICIAL_SUBJECT)):
        o = offerings[oid]
        if (str(o.subject_id), str(o.group_id), str(o.period_id), o.instructor_id, o.lesson_hours) != (
            subject,
            GROUP,
            PERIOD,
            TEACHER,
            45,
        ):
            raise MR118Error("offering_identity_changed")
    if (offerings[FILLED].subject.code, offerings[EMPTY].subject.code) != ("QKU-2499", "QKU-2717"):
        raise MR118Error("reviewed_catalogue_equivalence_changed")
    if (
        model("workload.TeachingTaskRow")
        .objects.filter(
            organization_id=ORG, period_id=PERIOD, subject_id__in=(FILLED_SUBJECT, OFFICIAL_SUBJECT), groups__pk=GROUP
        )
        .exclude(pk=ROW)
        .exists()
    ):
        raise MR118Error("alternate_workload_requires_review")
    if not offerings[FILLED].is_active:
        raise MR118Error("historical_offering_inactive")
    if model("registrar.Lesson").objects.filter(offering_id=EMPTY).exists():
        raise MR118Error("empty_offering_now_has_lessons")
    if source_fingerprint() != SOURCE_CELLS:
        raise MR118Error("reviewed_source_cells_changed")
    row = (
        model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .select_related("task")
        .get(pk=ROW, task_id=TASK, organization_id=ORG, period_id=PERIOD)
    )
    if (row.lecture_total, row.seminar_total, row.lab_total, row.lecture_plan, row.seminar_plan, row.lab_plan) != (
        45,
        0,
        0,
        45,
        0,
        0,
    ) or set(map(str, row.groups.values_list("pk", flat=True))) != {GROUP}:
        raise MR118Error("official_workload_changed")
    if list(row.assignments.values_list("teacher_id", "activity", "hours")) != [(TEACHER, "lecture", 45)]:
        raise MR118Error("official_assignment_changed")
    if not row.subject_text.strip():
        raise MR118Error("official_subject_label_missing")
    before = capture()
    baseline = digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise MR118Error("live_baseline_changed")
    receipt = (
        model("audit.AuditLog")
        .objects.filter(organization_id=ORG, resource_type=RESOURCE, resource_id=ROW)
        .order_by("-created_at")
        .first()
    )
    if undo:
        if not receipt or receipt.new_values.get("after_hash") != baseline or str(row.subject_id) != FILLED_SUBJECT:
            raise MR118Error("undo_live_state_changed")
    elif str(row.subject_id) == FILLED_SUBJECT:
        if receipt and offerings[EMPTY].is_active:
            return {"already_present": 1, "baseline": baseline}
        raise MR118Error("unverified_previous_binding")
    elif str(row.subject_id) != OFFICIAL_SUBJECT or not offerings[EMPTY].is_active:
        raise MR118Error("original_binding_changed")
    if not apply:
        return {"baseline": baseline, "bindings_to_restore" if undo else "bindings_to_correct": 1}
    if not expected_baseline:
        raise MR118Error("fresh_live_baseline_required")
    save_row_amended(
        task=row.task,
        row=row,
        actor=resolve_actor(user, organization),
        data={"subject_id": OFFICIAL_SUBJECT if undo else FILLED_SUBJECT},
        amend={
            "reason": AmendmentReason.CORRECTION,
            "note": "MR-000118: mənbə14676 jurnalının mövcud8dərs/16xanasını saxlayan yük bağlantısı",
        },
        sync_offerings=False,
    )
    after = capture()
    if digest(academic(before)) != digest(academic(after)):
        raise MR118Error("academic_or_syllabus_content_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE + (".undo" if undo else ""),
        resource_id=ROW,
        reason="MR-000118 exact existing journal binding",
        new_values={
            "before_hash": baseline,
            "after_hash": digest(after),
            "old_subject": OFFICIAL_SUBJECT,
            "filled_subject": FILLED_SUBJECT,
            "source_journal": 14676,
            "source_subject": 2499,
            "official_catalogue_subject": 2717,
            "source_cells_sha256": SOURCE_CELLS,
        },
    )
    return {"bindings_restored" if undo else "bindings_corrected": 1, "baseline": baseline}
