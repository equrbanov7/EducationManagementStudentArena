"""MR123: one mistaken catalogue link, never a global subject rename."""

import hashlib
import json

from django.apps import apps
from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from .integrity import eligible_instructor_user_ids
from .reviewed_catalog import create_reviewed_subject
from .subject_merge_apply import allow_offering_subject_change, clear_offering_subject_change

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
OFFERING = "90c22ceb-151f-4ba3-ae02-b7251ffd529e"
OLD = "4380e46b-e3f8-4052-b4c8-190ad89208e6"
NEW = "1736b9b6-0aaa-5b31-81b5-021663c24803"
GROUP = "6ec43661-08d7-4ad1-bb1c-c97ac98a999b"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TASK = "db6850fc-df57-43e1-80e1-f970378fc915"
CHAIR = "b17f7d56-7690-47ab-90c4-6cd3d402951a"
ROW = "f796518a-0b47-5109-b9d0-2146a6ce207a"
SYLLABUS = "462705d6-f911-4191-9816-4f054a9efaab"
TEACHER = 8227
RESOURCE = "registrar.mr123_subject_repair"
IDENTITY = dict(
    id=NEW, code="QKU-MR123-DE3", name="İxtisasyönümlü alman dili-3", ects=5, kind="core", chair_unit_id=CHAIR
)


class MR123Error(ValueError):
    pass


def model(name):
    return apps.get_model(name)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def rows(query):
    return list(query.order_by("pk").values())


def protected():
    """Academic identities/content stay unchanged while only two FK labels change."""
    enrollment = model("registrar.Enrollment").objects.filter(organization_id=ORG, offering_id=OFFERING)
    lessons = model("registrar.Lesson").objects.filter(organization_id=ORG, offering_id=OFFERING)
    versions = model("syllabus.SyllabusVersion").objects.filter(organization_id=ORG, syllabus_id=SYLLABUS)
    return {
        "enrollment": rows(enrollment),
        "lesson": rows(lessons),
        "marks": rows(model("registrar.LessonMark").objects.filter(organization_id=ORG, lesson__in=lessons)),
        "versions": rows(versions),
        "sections": rows(model("syllabus.SyllabusSection").objects.filter(version__in=versions)),
        "old_subject": rows(model("registrar.Subject").objects.filter(pk=OLD, organization_id=ORG)),
        "other_offerings": rows(
            model("registrar.CourseOffering").objects.filter(organization_id=ORG, subject_id=OLD).exclude(pk=OFFERING)
        ),
    }


def capture(offering, syllabus):
    return {
        "protected": protected(),
        "offering": rows(type(offering).objects.filter(pk=offering.pk)),
        "syllabus": rows(type(syllabus).objects.filter(pk=syllabus.pk)),
        "target_subject": rows(model("registrar.Subject").objects.filter(organization_id=ORG, pk=NEW)),
        "target_row": rows(model("workload.TeachingTaskRow").objects.filter(organization_id=ORG, pk=ROW)),
    }


@transaction.atomic
def repair_mr123_subject(*, organization, user, apply=False, expected_baseline=""):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise MR123Error("fixed_tenant_active_superadmin_required")
    if TEACHER not in eligible_instructor_user_ids(organization=organization):
        raise MR123Error("teacher_current_authority_missing")
    offering = model("registrar.CourseOffering").objects.select_for_update().get(pk=OFFERING, organization_id=ORG)
    if (str(offering.group_id), str(offering.period_id), offering.instructor_id, offering.lesson_hours) != (
        GROUP,
        PERIOD,
        TEACHER,
        60,
    ) or not offering.is_active:
        raise MR123Error("offering_scope_changed")
    syllabus = (
        model("syllabus.Syllabus")
        .objects.select_for_update()
        .get(pk=SYLLABUS, organization_id=ORG, offering=offering, author_id=TEACHER, period_id=PERIOD)
    )
    if not syllabus.is_active or syllabus.reused_from_id:
        raise MR123Error("syllabus_scope_changed")
    if (
        model("syllabus.SyllabusShare").objects.filter(syllabus=syllabus).exists()
        or model("syllabus.Syllabus").objects.filter(reused_from=syllabus).exists()
    ):
        raise MR123Error("shared_syllabus_requires_separate_review")
    Version = model("syllabus.SyllabusVersion")
    if (
        Version.objects.filter(source_version__syllabus_id=SYLLABUS).exclude(syllabus_id=SYLLABUS).exists()
        or Version.objects.filter(syllabus_id=SYLLABUS, source_version__isnull=False)
        .exclude(source_version__syllabus_id=SYLLABUS)
        .exists()
    ):
        raise MR123Error("linked_syllabus_version_requires_review")
    task = (
        model("workload.TeachingTask")
        .objects.select_for_update()
        .get(pk=TASK, organization_id=ORG, chair_id=CHAIR, academic_year="2026/2027")
    )
    before = capture(offering, syllabus)
    baseline = digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise MR123Error("live_baseline_changed")
    if str(offering.subject_id) == NEW:
        if (
            str(syllabus.subject_id) != NEW
            or not model("audit.AuditLog")
            .objects.filter(organization_id=ORG, resource_type=RESOURCE, new_values__offering=OFFERING)
            .exists()
        ):
            raise MR123Error("unverified_previous_correction")
        row = model("workload.TeachingTaskRow").objects.get(
            pk=ROW, organization_id=ORG, task=task, subject_id=NEW, period_id=PERIOD
        )
        if (row.lecture_total, row.seminar_total, row.lab_total) != (0, 60, 0):
            raise MR123Error("corrected_workload_changed")
        if list(row.assignments.values_list("teacher_id", "activity", "hours")) != [(TEACHER, "seminar", 60)] or set(
            map(str, row.groups.values_list("pk", flat=True))
        ) != {GROUP}:
            raise MR123Error("corrected_workload_changed")
        return {"already_present": 1, "baseline": baseline}
    if str(offering.subject_id) != OLD or str(syllabus.subject_id) != OLD:
        raise MR123Error("original_subject_scope_changed")
    existing_rows = (
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, period_id=PERIOD, groups__pk=GROUP, subject_id__in=(OLD, NEW))
        .distinct()
    )
    if existing_rows.exists():
        raise MR123Error("existing_workload_requires_review")
    if (
        model("registrar.Subject").objects.filter(pk=NEW).exists()
        or model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, subject_id=NEW, period_id=PERIOD, group_id=GROUP)
        .exists()
    ):
        raise MR123Error("target_catalogue_collision")
    if not apply:
        return {
            "baseline": baseline,
            "subjects_to_create": 1,
            "offering_links_to_correct": 1,
            "syllabus_links_to_correct": 1,
            "rows_to_create": 1,
        }
    if not expected_baseline:
        raise MR123Error("fresh_live_baseline_required")
    subject = create_reviewed_subject(
        organization=organization,
        user=user,
        identity=IDENTITY,
        reason="MR-000123 exact German journal catalogue correction",
    )
    allow_offering_subject_change([OLD], NEW)
    try:
        model("registrar.CourseOffering").objects.filter(pk=OFFERING, organization_id=ORG, subject_id=OLD).update(
            subject=subject
        )
    finally:
        if not connection.needs_rollback:
            clear_offering_subject_change()
    model("syllabus.Syllabus").objects.filter(pk=SYLLABUS, organization_id=ORG, subject_id=OLD).update(subject=subject)
    row = model("workload.TeachingTaskRow").objects.create(
        id=ROW,
        organization=organization,
        task=task,
        subject=subject,
        subject_text=IDENTITY["name"],
        period_id=PERIOD,
        season="fall",
        row_kind="teaching",
        groups_text="534 TB 1",
        lecture_plan=0,
        lecture_total=0,
        seminar_plan=60,
        seminar_total=60,
        lab_plan=0,
        lab_total=0,
        total_hours=60,
        credits_value=5,
        union_count=1,
        subgroup_count=1,
    )
    row.groups.add(GROUP)
    assignment = model("workload.TeacherAssignment")(
        organization=organization, row=row, teacher_id=TEACHER, activity="seminar", hours=60, assigned_by=user
    )
    assignment.full_clean()
    assignment.save()
    if digest(protected()) != digest(before["protected"]):
        raise MR123Error("academic_or_unrelated_subject_data_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=OFFERING,
        reason="MR-000123 teacher-requested scoped German subject correction",
        new_values={
            "offering": OFFERING,
            "old_subject": OLD,
            "new_subject": NEW,
            "syllabus": SYLLABUS,
            "row": ROW,
            "source_journal": 15053,
            "source_subject": 2678,
            "source_teacher": 784,
            "source_group": 826,
            "source_hours": 60,
            "source_credits": 5,
            "before_baseline": baseline,
            "protected_hash": digest(before["protected"]),
        },
    )
    return {
        "subjects_created": 1,
        "offering_links_corrected": 1,
        "syllabus_links_corrected": 1,
        "rows_created": 1,
        "baseline": baseline,
    }
