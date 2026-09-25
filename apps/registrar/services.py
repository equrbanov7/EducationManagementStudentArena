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
        .select_related(
            "offering__subject",
            "offering__course",
            "offering__assessment_scheme",
            # Ekran 10 — fənn kartında MÜƏLLİM adı göstərilir; `instructor`
            # olmadan hər sətir ayrıca sorğu edərdi (N+1).
            "offering__instructor",
        )
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
                "offering": enrollment.offering,
                "teacher": enrollment.offering.instructor,
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


# ── Plan → qruplar: qrupun kursu + qrupun açılışa TOPLU qeydiyyatı (2026-09-25) ──
#
# Sahib 2026-09-25: «tədris planı kafedralara göndəriləndə fənn avtomatik qruplara
# düşsün». Eyni yazını İKİ axın edir: dərs yükü zəncirinin təsdiqi
# (``apps.workload.services.offering_sync``, ``registrar.public.services`` ilə) və
# «Semestr açılışı» (``semester_open.generate_offerings``). Qaydalar ikisi üçün də
# BURADADIR ki, sürüşməsinlər: hansı qrup hansı semestri oxuyur və açılış
# yarananda kim qeydiyyata düşür.

#: Kurs nömrəsinin yuxarı sərhədi — qrup reyestrinin ``MAX_COURSE_YEAR``-ı ilə eyni.
MAX_GROUP_COURSE_YEAR = 6
#: :func:`enroll_group_students` hesabatının açarları (hamısı tam ədəd).
ENROLL_REPORT_KEYS = (
    "created",
    "existing",
    "conflict",
    "not_member",
    "guest_added",
    "guest_present",
    "guest_deferred",
    "guest_failed",
)


def _int_or_zero(value) -> int:
    try:
        return int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0


def group_course_year(group, academic_year) -> int:
    """Qrupun verilmiş tədris ilindəki KURSU; bilinmirsə ``0`` (heç bir semestrə düşmür).

    Üstünlük ``individual_plan._course_year`` ilə eynidir: (1) reyestrin açıq
    ``settings.course_year``-ı («Kursa keçir» hər il +1 edir); (2) köçürülmüş
    qrupların ``settings.admission_year``-ı: ``ilin başlanğıcı − qəbul ili + 1``.
    Sərhəddən kənar dəyər (2017 qəbullu qrup → 10-cu «kurs») ``0`` qaytarır.
    """
    import re

    blob = group.settings if isinstance(getattr(group, "settings", None), dict) else {}
    course = _int_or_zero(blob.get("course_year"))
    if course <= 0:
        admission = _int_or_zero(blob.get("admission_year"))
        match = re.search(r"(\d{4})", str(academic_year or ""))
        course = int(match.group(1)) - admission + 1 if (admission and match) else 0
    return course if 1 <= course <= MAX_GROUP_COURSE_YEAR else 0


def _insert_enrollments(rows, report) -> None:
    """Toplu INSERT; bir sətir DB qapısına dəysə — sətir-sətir (savepoint ilə)."""
    from django.db import IntegrityError

    try:
        with transaction.atomic():
            Enrollment.objects.bulk_create(rows, batch_size=500)
        report["created"] += len(rows)
        return
    except IntegrityError:
        pass
    for row in rows:
        try:
            with transaction.atomic():
                _, created = Enrollment.objects.get_or_create(
                    organization_id=row.organization_id,
                    student_id=row.student_id,
                    offering=row.offering,
                    defaults={"kind": row.kind},
                )
            report["created" if created else "existing"] += 1
        except IntegrityError:
            report["not_member"] += 1


def _enroll_own_students(org_id, offerings, records_by_group, kind, report) -> None:
    from django.apps import apps as django_apps

    own = [(offering, record) for offering in offerings for record in records_by_group.get(offering.group_id, ())]
    if not own:
        return
    student_ids = {record.student_id for _, record in own}
    existing = set(
        Enrollment.objects.filter(
            organization_id=org_id, offering_id__in=[o.pk for o in offerings], student_id__in=student_ids
        ).values_list("offering_id", "student_id")
    )
    # Eyni fənn + dövr üzrə BAŞQA açılışda AKTİV qeydiyyat = alt qrup birləşməsi
    # (``guest_roster``) və ya rəsmi köçürmə — tələbə iki jurnala düşməsin.
    elsewhere: dict = {}
    for student_id, offering_id, subject_id, period_id in Enrollment.objects.filter(
        organization_id=org_id,
        student_id__in=student_ids,
        status=Enrollment.Status.ENROLLED,
        offering__subject_id__in={o.subject_id for o in offerings},
        offering__period_id__in={o.period_id for o in offerings},
    ).values_list("student_id", "offering_id", "offering__subject_id", "offering__period_id"):
        elsewhere.setdefault((student_id, subject_id, period_id), set()).add(offering_id)
    # ``registrar_guard_active_member`` (0041) güzgüsü: aktiv üzvlük + aktiv eyni-tenant rolu.
    members = set(
        django_apps.get_model("organizations", "Membership")
        .objects.filter(
            organization_id=org_id,
            user_id__in=student_ids,
            is_active=True,
            role__is_active=True,
            role__organization_id=org_id,
        )
        .values_list("user_id", flat=True)
    )
    pending = []
    for offering, record in own:
        key = (offering.pk, record.student_id)
        if key in existing:
            report["existing"] += 1
        elif elsewhere.get((record.student_id, offering.subject_id, offering.period_id), set()) - {offering.pk}:
            report["conflict"] += 1
        elif record.student_id not in members:
            report["not_member"] += 1
        else:
            existing.add(key)
            pending.append(
                Enrollment(organization_id=org_id, student_id=record.student_id, offering=offering, kind=kind)
            )
    if pending:
        _insert_enrollments(pending, report)


def _rollup_combined_groups(org_id, offerings, *, by_user, reason, report) -> None:
    """Öz tələbəsi olmayan BİRLƏŞİK qrupun açılışı → alt qrup tələbələri «alt qrupdan əlavə».

    Sahib qərarı 2026-09-20 (:mod:`subgroup_rollup`): tələbələr öz alt qruplarında
    qalır, birləşik açılışa RƏSMİ yolla (:func:`guest_roster.add_guest_student` —
    provenans + audit) düşür. Dövr siyahıya bağlıdırsa (cari aktiv deyil) və ya
    icraçı yoxdursa əlavə TƏXİRƏ salınır (``guest_deferred``).
    """
    from django.apps import apps as django_apps
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError

    from . import guest_roster, subgroup_rollup

    groups = django_apps.get_model("organizations", "OrgUnit").objects.filter(
        organization_id=org_id, pk__in={o.group_id for o in offerings}
    )
    submap = subgroup_rollup.subgroup_map(org_id, list(groups.only("id", "name", "parent_id", "settings")))
    records: dict = {}
    for record in StudentAcademicRecord.objects.filter(
        organization_id=org_id,
        group_id__in={unit.pk for units in submap.values() for unit in units},
        is_active=True,
        status="enrolled",
    ).select_related("student", "group"):
        records.setdefault(record.group_id, []).append(record)
    for offering in offerings:
        candidates = [r for unit in submap.get(offering.group_id, ()) for r in records.get(unit.pk, ())]
        if candidates and (by_user is None or not guest_roster.period_allows_roster(offering.period)):
            report["guest_deferred"] += len(candidates)
            continue
        present = guest_roster.enrolled_student_ids(offering) if candidates else set()
        for record in candidates:
            if record.student_id in present:
                report["guest_present"] += 1
                continue
            try:
                guest_roster.add_guest_student(
                    offering=offering, student=record.student, by_user=by_user, source_group=record.group, reason=reason
                )
                present.add(record.student_id)
                report["guest_added"] += 1
            except (ValidationError, IntegrityError):
                report["guest_failed"] += 1


def enroll_group_students(*, offerings, kind=EnrollmentKind.MANDATORY, by_user=None, reason="") -> dict:
    """Açılış(lar)ın QRUPUNUN aktiv tələbələrini qeydiyyata alır — toplu, idempotent.

    :func:`enroll_student_in_subject`-in qrup səviyyəli forması; tarixçə qorunur:
    yalnız AKTİV + ``enrolled`` akademik qeyd; bu açılışda sətri olan tələbə
    (hətta ``dropped``/köçürmə tarixçəsi) TOXUNULMUR; eyni fənn+dövr üzrə başqa
    açılışda aktiv olan (birləşmə/köçürmə) ötürülür; aktiv üzvlüyü olmayan DB
    qapısına dəymədən ötürülür; öz tələbəsi olmayan birləşik qrupa alt qrup
    tələbələri :func:`_rollup_combined_groups` ilə düşür. Sorğu sayı açılış
    sayından asılı deyil. Qaytarır: ``created/existing/conflict/not_member/guest_*``.
    """
    report = dict.fromkeys(ENROLL_REPORT_KEYS, 0)
    by_org: dict = {}
    for offering in offerings:
        if offering is not None and offering.group_id and offering.is_active:
            by_org.setdefault(offering.organization_id, []).append(offering)
    for org_id, items in by_org.items():
        records_by_group: dict = {}
        for record in StudentAcademicRecord.objects.filter(
            organization_id=org_id, group_id__in={o.group_id for o in items}, is_active=True, status="enrolled"
        ).only("id", "student_id", "group_id"):
            records_by_group.setdefault(record.group_id, []).append(record)
        _enroll_own_students(org_id, items, records_by_group, kind, report)
        combined = [o for o in items if not records_by_group.get(o.group_id)]
        if combined:
            _rollup_combined_groups(org_id, combined, by_user=by_user, reason=reason, report=report)
    return report
