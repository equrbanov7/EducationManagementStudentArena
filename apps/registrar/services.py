"""Enrollment services (U2): mandatory auto-enroll + group-level elective choice.

The student academic flow from docs/architecture/UNIVERSITY_SYSTEM_ROADMAP.md §2:

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

from . import exam_eligibility
from .integrity import (
    validate_group_elective_target,
    validate_offering_target,
    validate_same_organization,
)
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
    validate_offering_target(
        organization=organization,
        subject=subject,
        period=period,
        group=group,
        course=course,
    )
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
    """Ensure the student is enrolled in *subject* for *period* (their group section).

    Existing rows, including historical ones, are never reactivated implicitly;
    callers that require a current enrollment must inspect ``status``.
    """
    validate_same_organization(
        organization=record.organization,
        record=record,
        subject=subject,
        period=period,
    )
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


class RegistrationWindowClosed(Exception):
    """Seçmə-fənn qərarı qeydiyyat pəncərəsindən kənarda cəhd edildi (U14).

    ``AcademicPeriod.registration_start/end`` müəyyən edilibsə və bugünkü tarix
    pəncərədən kənardadırsa qaldırılır. Registrar/inzibati axınlar
    ``enforce_window=False`` ilə keçə bilər (staff override)."""


@transaction.atomic
def choose_group_elective(
    *, organization, group, curriculum, period, elective_group, subject, decided_by=None, enforce_window=True
):
    """Record a group's elective-block decision and enroll EVERY group member.

    In the AZ model the elective is a group decision: once chosen, all active
    students of the group are enrolled in the chosen subject. Returns
    ``(choice, enrolled_count)``. Idempotent — changing the choice re-points the
    record; already-enrolled members are not duplicated.

    Akademik təqvim (U11/U14): period qeydiyyat pəncərəsi konfiqurasiya edibsə,
    qərar yalnız pəncərə AÇIQ olanda verilə bilər (staff ``enforce_window=False``
    ilə keçə bilər)."""
    validate_group_elective_target(
        organization=organization,
        group=group,
        curriculum=curriculum,
        period=period,
        elective_group=elective_group,
        subject=subject,
        decided_by=decided_by,
    )
    if enforce_window:
        state = getattr(period, "registration_state", None)
        if state is not None and state != "open":
            raise RegistrationWindowClosed(
                f"Qeydiyyat pəncərəsi {'hələ açılmayıb' if state == 'upcoming' else 'bağlanıb'}: "
                f"{period.registration_start} — {period.registration_end}"
            )

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
        Enrollment.objects.filter(organization=record.organization, student=record.student, offering__period=period)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering__subject", "offering__course", "offering__assessment_scheme")
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


def get_credit_summary(*, record, today=None):
    """Bologna ECTS graduation progress for a student's program.

    Earned = ECTS of **passed** subjects, in-progress = ECTS of not-yet-passed
    subjects in a period that has not ended; required = ``program.ects_total``.
    ``can_graduate`` is True once earned ≥ required (mandatory-pass checks live
    in the grading layer, U3).

    Kredit ``Enrollment.status``-dan DEYİL, qiymətlərdən oxunur — transkript
    qatı ilə eyni mənbədən, ona görə «Fənlərim» ECTS qutusu ilə «Ümumi tədris
    məlumatı» bir daha ayrılmır (səbəb + performans qərarı:
    :func:`transcript.student_credit_totals` docstring-i). Import funksiya
    daxilindədir: ``transcript`` → ``analytics`` → ``finals`` → ``services``
    zənciri modul səviyyəsində dövri import yaradardı."""
    from apps.registrar import transcript as transcript_service

    totals = transcript_service.student_credit_totals(
        student=record.student, organization=record.organization, today=today
    )
    earned = totals["earned"]
    in_progress = totals["in_progress"]
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


def get_exam_eligibility(*, enrollment, limit_percent, exempt=False, resit_done=False, frozen=None, hours_map=None):
    """Absence (qayıb) rule: a student is barred from the subject's exam when
    unexcused absence hours exceed ``limit_percent`` of the lesson hours.

    ``limit_percent`` comes from the student's program
    (``Program.absence_limit_percent``); it is tenant/program-configurable.

    ``exempt`` — rəsmi idmançı-tələbə istisnası (milli yığma;
    ``StudentAcademicRecord.national_athlete_exemption``).  ``True`` olduqda
    saatlar olduğu kimi qalır (``absence_hours`` dəyişmir, davamiyyət balı yenə
    real qayıba görə hesablanır), sadəcə ``barred`` heç vaxt qalxmır.

    ``frozen`` — ``None`` olduqda açılış üçün özü yoxlanılır
    (:func:`exam_eligibility.is_frozen`).  Toplu səthlər bunu
    :func:`exam_eligibility.frozen_offering_ids` ilə əvvəlcədən hesablayıb
    ötürməlidir (N+1-in qarşısını alır).

    ⚠️ Bu funksiya artıq yalnız **nazik sarğıdır**: qərarın özü
    :func:`apps.registrar.exam_eligibility.resolve`-dadır — sistemdə yeganə
    yerdir.  2026-08-31 auditinə qədər eyni müqayisə doqquz yerdə təkrarlanırdı;
    yeni buraxılış qaydası ARTIQ təkrarlanmamalıdır, o qapıdan keçməlidir.
    """
    return exam_eligibility.resolve(
        absence_hours=enrollment.absence_hours,
        # Məxrəc TƏK tərifdən (``lesson_hours`` boşdursa dərslərin saat cəmi) —
        # əvvəl bu səth xam sahəyə baxırdı, jurnal qridi isə fallback-a, yəni
        # eyni sətir iki ekranda fərqli cavab alırdı.  ``hours_map`` verilibsə
        # sorğu yaranmır (döngüdə çağıranlar onu əvvəlcədən qurur).
        lesson_hours=exam_eligibility.lesson_hours_for(enrollment.offering, hours_map=hours_map),
        limit_percent=limit_percent,
        exempt=exempt,
        resit_done=resit_done,
        frozen=exam_eligibility.is_frozen(enrollment.offering) if frozen is None else frozen,
    )


def get_student_cabinet_data(*, record, period, semester_number):
    """Everything the student "Fənlərim" cabinet section renders.

    Combines the semester plan (enrollments + open elective blocks + group
    decisions) with per-subject credits + absence eligibility and the overall
    Bologna credit progress."""
    plan = get_student_semester_plan(record=record, period=period, semester_number=semester_number)
    limit_percent = record.program.absence_limit_percent
    # Donma dəsti bir dəfə (iki sorğu) — hər fənn üçün ayrıca yoxlama N+1 olardı.
    offering_ids = [e.offering_id for e in plan["enrollments"]]
    frozen_ids = exam_eligibility.frozen_offering_ids(offering_ids)
    # Məxrəc fallback-ı da toplu (tək aqreqat sorğu) — 25,314 köçürülmüş
    # yazılışda ``lesson_hours=0`` olduğu üçün sətir-sətir oxumaq N+1 olardı.
    hours_map = exam_eligibility.lesson_hours_map(offering_ids)
    subjects = []
    for enrollment in plan["enrollments"]:
        subject = enrollment.offering.subject
        eligibility = get_exam_eligibility(
            enrollment=enrollment,
            limit_percent=limit_percent,
            exempt=record.national_athlete_exemption,
            frozen=enrollment.offering_id in frozen_ids,
            hours_map=hours_map,
        )
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
