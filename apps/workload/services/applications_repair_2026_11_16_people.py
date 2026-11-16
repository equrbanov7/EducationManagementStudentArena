"""MR-000395 (505/6 MB proqramı) və MR-000396 (935 BM tələbəsinin jurnal köçürməsi) — 2026-11-16.

B: qrupun aktiv qeydləri «Genetika» proqramındadır; hədəf «Malekulyar biologiya» ixtisasının magistr proqramı (tək;
505/5 MB qeydləri başqa proqram işlədirsə atlanır) + qeydin qəbul ilinin planı (təsdiqlənmiş üstündür, ən yeni
versiya; yoxdursa ``b_curriculum_missing``). Bağlı jurnalda / kilidli semestrdə qiyməti olan qeyd toxunulmur.
Yazı birbaşa qeydə (məlumat girişi düzəlişi, hərəkət əmri deyil) + qeyd başına audit.

C: tələbə mənbə jurnalda (935 BM, Günay Əmirova) AD tokenləri ilə tapılır (tək ``enrolled``), hədəf — eyni fənn və
semestrdə Aytac Salmanlının «935 … ing» jurnalı (tək). Köçürmə jurnal modalının servisidir
(``registrar.public.add_guest_student``, ``release_source=True``): mənbə qeydiyyat ``dropped`` + ``superseded_by``,
xanalar və giriş balı mənbədə qalır (varis jurnal zəncirlə göstərir), qayıb saatı hədəfə daşınır. Superadmin
sənəd azadlığı modaldakı kimi səbəbə möhür vurur (``superadmin_waiver.stamp``).
"""

from __future__ import annotations

from django.utils import timezone

from .applications_repair_2026_11_16 import (
    B_DEGREE,
    B_FROM_PROGRAM,
    B_GROUP,
    B_PEER_GROUP,
    B_TO_SPECIALTY,
    C_SOURCE_GROUP,
    C_SOURCE_TEACHER,
    C_STUDENT,
    C_TARGET_GROUP_TOKENS,
    C_TARGET_TEACHER,
    REASONS,
    RES_MOVE,
    RES_PROGRAM,
    Skip,
    audit,
    groups_named,
    model,
    one_group,
    person_has,
    tokens,
)

# ── B — proqram + plan ───────────────────────────────────────────────────────


def _target_program(organization):
    Program, Record = model("registrar", "Program"), model("registrar", "StudentAcademicRecord")
    found = list(
        Program.objects.filter(
            organization=organization,
            specialty_unit__name__iexact=B_TO_SPECIALTY,
            degree_level=B_DEGREE,
            is_active=True,
        )
    )
    peers = groups_named(organization, B_PEER_GROUP)
    used = set(
        Record.objects.filter(organization=organization, group__in=peers, is_active=True).values_list(
            "program_id", flat=True
        )
    )
    if len(found) > 1:
        found = [program for program in found if program.pk in used]
    if len(found) != 1:
        raise Skip("program_unresolved")
    peer_mb = {
        pk
        for pk in used
        if Program.objects.filter(pk=pk, specialty_unit__name__iexact=B_TO_SPECIALTY, degree_level=B_DEGREE).exists()
    }
    if peer_mb and found[0].pk not in peer_mb:
        raise Skip("program_differs_from_peer_group")
    return found[0]


def _curriculum(program, year, counts):
    rows = list(model("registrar", "Curriculum").objects.filter(program=program, admission_year=year, is_active=True))
    approved = [row for row in rows if row.status == "approved"]
    pool = approved or rows
    if not pool:
        return None
    if not approved:
        counts["b_curriculum_not_approved"] += 1
    return max(pool, key=lambda row: (row.version or 0, row.created_at))


def _closed_grades(organization, student_id) -> bool:
    """Bağlı jurnalda və ya kilidli semestrdə yekun qiymət / ballı xana varmı."""
    from apps.registrar.public import handover

    Enrollment, Offering = model("registrar", "Enrollment"), model("registrar", "CourseOffering")
    enrollments = Enrollment.objects.filter(organization=organization, student_id=student_id)
    offering_ids = set(enrollments.values_list("offering_id", flat=True))
    if not offering_ids:
        return False
    closed = set(handover.closed_offering_ids(list(offering_ids)))
    closed |= set(
        Offering.objects.filter(pk__in=offering_ids, period__locked_at__isnull=False).values_list("pk", flat=True)
    )
    if not closed:
        return False
    scoped = enrollments.filter(offering_id__in=closed)
    return (
        model("registrar", "FinalGrade").objects.filter(enrollment__in=scoped).exists()
        or model("registrar", "LessonMark").objects.filter(enrollment__in=scoped, score__isnull=False).exists()
    )


def apply_programs(*, organization, actor, period, batch, counts) -> None:
    Record = model("registrar", "StudentAcademicRecord")
    group = one_group(organization, B_GROUP, "group_unresolved")
    records = list(
        Record.objects.select_for_update(of=("self",))
        .filter(organization=organization, group=group, is_active=True)
        .select_related("program")
        .order_by("pk")
    )
    if not records:
        raise Skip("records_missing")
    target = _target_program(organization)
    pending = []
    for record in records:
        if record.program_id == target.pk:
            counts["b_already_done"] += 1
        elif record.program.name.strip() != B_FROM_PROGRAM:
            counts["b_program_unexpected"] += 1
        else:
            pending.append(record)
    counts["b_genetika_records"] += len(pending)
    for record in pending:
        curriculum = _curriculum(target, record.admission_year, counts)
        if curriculum is None:
            counts["b_curriculum_missing"] += 1
            continue
        if _closed_grades(organization, record.student_id):
            counts["b_closed_grades_skipped"] += 1
            continue
        if Record.objects.filter(organization=organization, student_id=record.student_id, program=target).exists():
            counts["b_program_taken"] += 1
            continue
        old = {"program": str(record.program_id), "curriculum": str(record.curriculum_id)}
        Record.objects.filter(pk=record.pk).update(program=target, curriculum=curriculum, updated_at=timezone.now())
        counts["b_records_moved"] += 1
        audit(
            actor=actor,
            organization=organization,
            resource_type=RES_PROGRAM,
            resource_id=record.pk,
            repr_=f"{group.name}: {B_FROM_PROGRAM} → {target.name}",
            reason=REASONS["b"],
            old_values=old,
            new_values={
                "batch": batch,
                "group": str(group.pk),
                "program": str(target.pk),
                "curriculum": str(curriculum.pk),
            },
        )


def undo_program(*, organization, actor, row, batch, counts) -> None:
    Record = model("registrar", "StudentAcademicRecord")
    values, old = row.new_values or {}, row.old_values or {}
    record = (
        Record.objects.select_for_update(of=("self",)).filter(organization=organization, pk=row.resource_id).first()
    )
    if record is None:
        raise Skip("record_missing")
    if (str(record.program_id), str(record.curriculum_id)) != (values.get("program"), values.get("curriculum")):
        raise Skip("record_changed")
    Record.objects.filter(pk=record.pk).update(
        program_id=old["program"], curriculum_id=old["curriculum"], updated_at=timezone.now()
    )
    counts["b_undo_restored"] += 1
    audit(
        actor=actor,
        organization=organization,
        resource_type=f"{RES_PROGRAM}.undo",
        resource_id=row.resource_id,
        repr_="MR-000395 geri qaytarıldı",
        reason=f"{REASONS['b']} — geri qaytarma",
        old_values={"batch": batch},
        new_values={"undone_batch": batch},
    )


# ── C — tələbənin jurnal köçürməsi ───────────────────────────────────────────


def _source(organization, period):
    """``(mənbə açılış, tələbənin qeydiyyatı)`` — tələbə ad tokenləri ilə, tək ``enrolled``."""
    Offering, Enrollment = model("registrar", "CourseOffering"), model("registrar", "Enrollment")
    offerings = [
        offering
        for offering in Offering.objects.filter(
            organization=organization,
            period=period,
            is_active=True,
            group__in=groups_named(organization, C_SOURCE_GROUP),
        ).select_related("instructor", "group", "subject")
        if person_has(offering.instructor, C_SOURCE_TEACHER)
    ]
    enrolled, moved = [], 0
    for enrollment in Enrollment.objects.filter(offering__in=offerings).select_related("student", "offering"):
        if not person_has(enrollment.student, C_STUDENT):
            continue
        if enrollment.status == "enrolled":
            enrolled.append(enrollment)
        elif enrollment.superseded_by_id is not None:
            moved += 1
    if len(enrolled) != 1:
        raise Skip("already_done" if not enrolled and moved else "student_unresolved")
    return enrolled[0].offering, enrolled[0]


def _target(organization, period, source):
    head = C_TARGET_GROUP_TOKENS[0]
    found = [
        offering
        for offering in model("registrar", "CourseOffering")
        .objects.filter(
            organization=organization,
            period=period,
            is_active=True,
            subject_id=source.subject_id,
            group__name__istartswith=head,
        )
        .exclude(pk=source.pk)
        .select_related("instructor", "group")
        if person_has(offering.instructor, C_TARGET_TEACHER)
        and {item.casefold() for item in C_TARGET_GROUP_TOKENS} <= tokens(offering.group.name)
    ]
    if len(found) != 1:
        raise Skip("target_unresolved")
    return found[0]


def apply_move(*, organization, actor, period, batch, counts) -> None:
    from apps.registrar.public import add_guest_student, recompute_absence_hours_many
    from core import superadmin_waiver

    Enrollment, LessonMark = model("registrar", "Enrollment"), model("registrar", "LessonMark")
    source, src = _source(organization, period)
    target = _target(organization, period, source)
    student = src.student
    cells = LessonMark.objects.filter(enrollment=src).count()
    before = Enrollment.objects.filter(organization=organization, student=student, offering=target).first()
    reason = superadmin_waiver.stamp(REASONS["c"], actor, scope=superadmin_waiver.SUBGROUP)
    enrollment = add_guest_student(offering=target, student=student, by_user=actor, reason=reason, release_source=True)
    src.refresh_from_db()
    if src.status != "dropped" or src.superseded_by_id != enrollment.pk:
        raise Skip("source_not_released")
    if LessonMark.objects.filter(enrollment=src).count() != cells:
        raise Skip("cells_changed")
    recompute_absence_hours_many([enrollment])
    enrollment.refresh_from_db()
    counts["c_moved"] += 1
    counts["c_cells_kept"] += cells
    counts["c_absence_hours"] += int(enrollment.absence_hours or 0)
    audit(
        actor=actor,
        organization=organization,
        resource_type=RES_MOVE,
        resource_id=enrollment.pk,
        repr_=f"{source.subject.name}: {source.group.name} → {target.group.name}",
        reason=reason,
        old_values={"source_enrollment": str(src.pk), "target_status": getattr(before, "status", "")},
        new_values={
            "batch": batch,
            "source_offering": str(source.pk),
            "target_offering": str(target.pk),
            "source_enrollment": str(src.pk),
            "target_enrollment": str(enrollment.pk),
            "target_created": before is None,
            "cells": cells,
        },
    )


def undo_move(*, organization, actor, row, batch, counts) -> None:
    from apps.registrar.public import recompute_absence_hours_many

    Enrollment, LessonMark = model("registrar", "Enrollment"), model("registrar", "LessonMark")
    values = row.new_values or {}
    found = {
        str(item.pk): item
        for item in Enrollment.objects.select_for_update(of=("self",)).filter(
            organization=organization, pk__in=[values.get("source_enrollment"), values.get("target_enrollment")]
        )
    }
    source, target = found.get(values.get("source_enrollment")), found.get(values.get("target_enrollment"))
    if source is None or target is None:
        raise Skip("enrollment_missing")
    if target.status != "enrolled" or source.status != "dropped" or source.superseded_by_id != target.pk:
        raise Skip("state_changed")
    if LessonMark.objects.filter(enrollment=target).exists():
        raise Skip("target_has_cells")
    now = timezone.now()
    Enrollment.objects.filter(pk=target.pk).update(status="dropped", updated_at=now)
    Enrollment.objects.filter(pk=source.pk).update(status="enrolled", superseded_by=None, updated_at=now)
    recompute_absence_hours_many(list(Enrollment.objects.filter(pk__in=[source.pk, target.pk])))
    counts["c_undo_restored"] += 1
    audit(
        actor=actor,
        organization=organization,
        resource_type=f"{RES_MOVE}.undo",
        resource_id=row.resource_id,
        repr_="MR-000396 geri qaytarıldı",
        reason=f"{REASONS['c']} — geri qaytarma",
        old_values={"batch": batch},
        new_values={"undone_batch": batch},
    )
