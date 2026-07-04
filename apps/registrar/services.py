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


# ── Bologna credits + absence (qayıb) eligibility (U2-UI) ────────────────────


def get_credit_summary(*, record):
    """Bologna ECTS graduation progress for a student's program.

    Earned = ECTS of COMPLETED enrollments; in-progress = ECTS of currently
    ENROLLED ones; required = ``program.ects_total``. ``can_graduate`` is True
    once earned ≥ required (mandatory-pass checks live in the grading layer, U3)."""
    completed = Enrollment.objects.filter(
        organization=record.organization, student=record.student, status=Enrollment.Status.COMPLETED
    ).select_related("offering__subject")
    active = Enrollment.objects.filter(
        organization=record.organization, student=record.student, status=Enrollment.Status.ENROLLED
    ).select_related("offering__subject")
    earned = sum(e.offering.subject.ects for e in completed)
    in_progress = sum(e.offering.subject.ects for e in active)
    required = record.program.ects_total or 0
    remaining = max(0, required - earned)
    percent = round(earned / required * 100, 1) if required else 0.0
    return {
        "earned": earned,
        "in_progress": in_progress,
        "required": required,
        "remaining": remaining,
        "percent": percent,
        "can_graduate": required > 0 and earned >= required,
    }


def get_exam_eligibility(*, enrollment, limit_percent):
    """Absence (qayıb) rule: a student is barred from the subject's exam when
    unexcused absence hours exceed ``limit_percent`` of the lesson hours.

    ``limit_percent`` comes from the student's program
    (``Program.absence_limit_percent``); it is tenant/program-configurable."""
    lesson_hours = enrollment.offering.lesson_hours or 0
    allowed_hours = lesson_hours * limit_percent / 100.0
    barred = lesson_hours > 0 and enrollment.absence_hours > allowed_hours
    return {
        "barred": barred,
        "absence_hours": enrollment.absence_hours,
        "lesson_hours": lesson_hours,
        "allowed_hours": allowed_hours,
        "limit_percent": limit_percent,
    }


def get_student_cabinet_data(*, record, period, semester_number):
    """Everything the student "Fənlərim" cabinet section renders.

    Combines the semester plan (enrollments + open elective blocks + group
    decisions) with per-subject credits + absence eligibility and the overall
    Bologna credit progress."""
    plan = get_student_semester_plan(record=record, period=period, semester_number=semester_number)
    limit_percent = record.program.absence_limit_percent
    subjects = []
    for enrollment in plan["enrollments"]:
        subject = enrollment.offering.subject
        eligibility = get_exam_eligibility(enrollment=enrollment, limit_percent=limit_percent)
        subjects.append(
            {
                "enrollment": enrollment,
                "subject": subject,
                "ects": subject.ects,
                "kind": enrollment.kind,
                "course": enrollment.offering.course,
                "eligibility": eligibility,
            }
        )
    return {
        "subjects": subjects,
        "elective_blocks": plan["elective_blocks"],
        "group_decisions": plan["group_decisions"],
        "credit_summary": get_credit_summary(record=record),
    }


# ── Fənn ↔ Kurs (LMS) körpüsü (W1) ───────────────────────────────────────────
#
# Registrar akademik planı ilə `courses` (məzmun) arasında bağ: offering üçün
# real Course yaradılır/bağlanır ki, tələbə "Fənlərim"də fənnə klik edəndə fənn
# içinə (mövzu/resurs) çatsın. `courses` modeli STATİK import olunmur (modul-
# sərhəd qrafı asiklik qalsın) — app registry ilə həll olunur.


def ensure_offering_course(*, offering, owner=None):
    """Idempotently link/create the LMS ``Course`` for *offering*.

    Owner precedence: explicit *owner* → the offering instructor → the org
    owner (Course.owner is required). Returns the linked Course."""
    from django.apps import apps as django_apps

    if offering.course_id:
        return offering.course

    Course = django_apps.get_model("courses", "Course")
    course_owner = owner or offering.instructor or offering.organization.owner
    course = Course.objects.create(
        owner=course_owner,
        title=offering.subject.name,
        organization=offering.organization,
        unit=offering.group,
        period=offering.period,
        status="published",
    )
    offering.course = course
    offering.save(update_fields=["course", "updated_at"])
    return course


def sync_offering_course_members(*, offering):
    """Grant the instructor + enrolled students access to the linked Course.

    So the "fənn içi" (course dashboard) is reachable by the section's students.
    Returns the number of student memberships created."""
    from django.apps import apps as django_apps

    if not offering.course_id:
        return 0
    CourseMembership = django_apps.get_model("courses", "CourseMembership")

    if offering.instructor_id:
        CourseMembership.objects.get_or_create(
            course_id=offering.course_id, user_id=offering.instructor_id, defaults={"role": "teacher"}
        )
    created = 0
    enrolled = offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related("student")
    for enrollment in enrolled:
        _, was_created = CourseMembership.objects.get_or_create(
            course_id=offering.course_id, user=enrollment.student, defaults={"role": "student"}
        )
        created += int(was_created)
    return created
