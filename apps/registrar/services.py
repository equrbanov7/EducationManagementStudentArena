"""Enrollment services (U2): mandatory auto-enroll + group-level elective choice.

The student academic flow from docs/UNIVERSITY_SYSTEM_ROADMAP.md §2:

  * ``enroll_mandatory_subjects`` — on specialty/curriculum assignment, enroll the
    student in every mandatory subject of the semester.
  * ``choose_group_elective`` — the elective is decided at GROUP level; one
    decision enrolls every active member of the group in the chosen subject
    (roadmap §2.5). Idempotent and late-joiner safe.
  * ``get_student_semester_plan`` — the data the student cabinet renders:
    current enrollments + open elective blocks + the group's decisions.

These are plain services called from the request path (RLS context already set)
or a caller that manages tenant scope; they do not open their own transaction.
"""

from __future__ import annotations

from django.db import transaction

from .models import (
    CourseOffering,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    GroupElectiveChoice,
    StudentAcademicRecord,
)


def get_or_create_offering(*, organization, subject, period, group, course=None):
    """The section for (subject, semester, group). Reuses the LMS course if given."""
    offering, created = CourseOffering.objects.get_or_create(
        organization=organization,
        subject=subject,
        period=period,
        group=group,
        defaults={"course": course},
    )
    if course is not None and offering.course_id is None:
        offering.course = course
        offering.save(update_fields=["course", "updated_at"])
    return offering


def enroll_student_in_subject(*, record, subject, period, kind):
    """Ensure the student is enrolled in *subject* for *period* (their group section)."""
    offering = get_or_create_offering(
        organization=record.organization, subject=subject, period=period, group=record.group
    )
    enrollment, created = Enrollment.objects.get_or_create(
        organization=record.organization,
        student=record.student,
        offering=offering,
        defaults={"kind": kind},
    )
    return enrollment, created


@transaction.atomic
def enroll_mandatory_subjects(*, record, period, semester_number):
    """Enroll the student in every MANDATORY subject of their curriculum semester.

    Returns the number of new enrollments created (idempotent — re-running is a
    no-op for already-enrolled subjects)."""
    rows = CurriculumSubject.objects.filter(
        curriculum=record.curriculum, semester_number=semester_number, is_elective=False
    ).select_related("subject")
    created = 0
    for row in rows:
        _, was_created = enroll_student_in_subject(
            record=record, subject=row.subject, period=period, kind=EnrollmentKind.MANDATORY
        )
        created += int(was_created)
    return created


@transaction.atomic
def choose_group_elective(*, organization, group, curriculum, period, elective_group, subject, decided_by=None):
    """Record a group's elective-block decision and enroll EVERY group member.

    In the AZ model the elective is a group decision: once chosen, all active
    students of the group are enrolled in the chosen subject. Returns
    ``(choice, enrolled_count)``. Idempotent — changing the choice re-points the
    record; already-enrolled members are not duplicated.
    """
    choice, _ = GroupElectiveChoice.objects.update_or_create(
        organization=organization,
        group=group,
        period=period,
        elective_group=elective_group,
        defaults={"chosen_subject": subject, "decided_by": decided_by},
    )
    offering = get_or_create_offering(organization=organization, subject=subject, period=period, group=group)
    records = StudentAcademicRecord.objects.filter(
        organization=organization, group=group, curriculum=curriculum, is_active=True
    )
    enrolled = 0
    for rec in records:
        _, created = Enrollment.objects.get_or_create(
            organization=organization,
            student=rec.student,
            offering=offering,
            defaults={"kind": EnrollmentKind.ELECTIVE},
        )
        enrolled += int(created)
    return choice, enrolled


def get_student_semester_plan(*, record, period, semester_number):
    """Return the student cabinet's semester view: enrollments + elective blocks.

    Shape::

        {
          "enrollments": [Enrollment, ...],          # mandatory + elective
          "elective_blocks": {group: {"required_choices": n, "options": [Subject, ...]}},
          "group_decisions": {group: Subject},       # already chosen for the group
        }
    """
    enrollments = list(
        Enrollment.objects.filter(
            organization=record.organization, student=record.student, offering__period=period
        ).select_related("offering__subject", "offering__course")
    )

    elective_rows = CurriculumSubject.objects.filter(
        curriculum=record.curriculum, semester_number=semester_number, is_elective=True
    ).select_related("subject")
    blocks: dict[str, dict] = {}
    for row in elective_rows:
        block = blocks.setdefault(row.elective_group, {"required_choices": row.required_choices, "options": []})
        block["options"].append(row.subject)

    decisions = {
        c.elective_group: c.chosen_subject
        for c in GroupElectiveChoice.objects.filter(
            organization=record.organization, group=record.group, period=period
        ).select_related("chosen_subject")
    }

    return {"enrollments": enrollments, "elective_blocks": blocks, "group_decisions": decisions}
