"""Tədris planı hazırlığı — MR-000393 / MR-000395 (sahib 2026-11-17: «et»).

A və B hissələri plan olmadığı üçün atlanırdı (``a_new_subject_not_in_block``, ``b_curriculum_missing``). Bu modul
həmin hissələrdən ƏVVƏL, öz savepoint-ində planı hazırlayır; sonra A / B dəyişməmiş qaydaları ilə işləyir.

* **PA — 2132T:** qrupun cari semestr qərarı «Genderin tarixi»dir (tək); qrup tələbələrinin İSTİFADƏ ETDİYİ hər planda
  həmin seçmə blokun «Genderin tarixi» sətrinin YANINA «Sosial tarix» sətri əlavə olunur (saat/kredit/kafedra/forma —
  «Genderin tarixi» sətrindən; fənn — 2132T + semestr yük sətrinin fənni, tək olmalıdır). Fənn həmin semestrdə planda
  başqa cür artıq varsa heç nə yazılmır (``pa_new_subject_elsewhere``).
* **PB — 505/6 MB:** «Malekulyar biologiya» (magistr) proqramında qrup qeydlərinin qəbul ili üçün plan yoxdursa,
  həmin proqramın ən yaxın ƏVVƏLKİ ilinin aktiv planı (təsdiqlənmiş üstündür, ən yeni versiya) bütün sətirləri ilə
  köçürülür; status mənbədən götürülür, səbəb ``last_reason``-da.

Hər yazı audit sətri (``RES_PLAN_ROW`` / ``RES_PLAN_CLONE``, ``batch``) daşıyır. ``undo``: plan sətri yalnız qrupun
qərarı ona bağlı deyilsə silinir; köçürülmüş plan yalnız heç bir qeyd ondan istifadə etmirsə silinir (A / B undo-su
daha yeni audit sətri olduğu üçün ƏVVƏL işləyir).
"""

from __future__ import annotations

from django.utils import timezone

from .applications_repair_2026_11_16 import (
    A_GROUP,
    A_NEW_SUBJECT,
    A_OLD_SUBJECT,
    B_FROM_PROGRAM,
    B_GROUP,
    RES_PLAN_CLONE,
    RES_PLAN_ROW,
    Skip,
    audit,
    model,
    one_group,
)

REASON_ROW = "MR-000393 (sahib 2026-11-17): «Sosial tarix» 2132T planının «Genderin tarixi» seçmə blokuna əlavə edildi"
REASON_CLONE = "MR-000395 (sahib 2026-11-17): «Malekulyar biologiya» planı əvvəlki ilin planından köçürüldü"

#: Plan sətrinin köçürülən sahələri (fənn, plan və sıra ayrıca).
ROW_FIELDS = (
    "semester_number",
    "is_elective",
    "elective_group",
    "required_choices",
    "row_code",
    "credits",
    "total_hours",
    "lecture_hours",
    "seminar_hours",
    "lab_hours",
    "selfwork_hours",
    "assessment_form",
    "language",
    "teaching_chair_id",
)


def _new_subject(organization, group, period):
    Row = model("workload", "TeachingTaskRow")
    ids = set(
        Row.objects.filter(organization=organization, groups=group, period=period, subject__name__iexact=A_NEW_SUBJECT)
        .exclude(task__status="cancelled")
        .values_list("subject_id", flat=True)
    )
    if len(ids) != 1:
        raise Skip("new_subject_unresolved")
    return model("registrar", "Subject").objects.get(pk=next(iter(ids)))


def prepare_block(*, organization, actor, period, batch, counts) -> None:
    Choice, Row = model("registrar", "GroupElectiveChoice"), model("registrar", "CurriculumSubject")
    Record = model("registrar", "StudentAcademicRecord")
    group = one_group(organization, A_GROUP, "group_unresolved")
    old = [
        choice
        for choice in Choice.objects.filter(organization=organization, group=group, period=period).select_related(
            "chosen_subject"
        )
        if choice.chosen_subject.name.strip() == A_OLD_SUBJECT
    ]
    if len(old) != 1:
        raise Skip("choice_unresolved")
    block, old_subject = old[0].elective_group, old[0].chosen_subject
    new_subject = _new_subject(organization, group, period)
    plan_ids = set(
        Record.objects.filter(
            organization=organization, group=group, is_active=True, curriculum__isnull=False
        ).values_list("curriculum_id", flat=True)
    )
    for source in Row.objects.filter(
        organization=organization,
        curriculum_id__in=plan_ids,
        subject=old_subject,
        elective_group=block,
        is_elective=True,
    ).order_by("pk"):
        same = Row.objects.filter(curriculum_id=source.curriculum_id, subject=new_subject)
        if same.filter(elective_group=block, is_elective=True).exists():
            counts["pa_rows_already"] += 1
            continue
        if same.filter(semester_number=source.semester_number).exists():
            raise Skip("new_subject_elsewhere")
        row = Row(organization=organization, curriculum_id=source.curriculum_id, subject=new_subject)
        for field in ROW_FIELDS:
            setattr(row, field, getattr(source, field))
        row.save()
        counts["pa_rows_added"] += 1
        audit(
            actor=actor,
            organization=organization,
            resource_type=RES_PLAN_ROW,
            resource_id=row.pk,
            repr_=f"{A_GROUP} planı: {A_NEW_SUBJECT}",
            reason=REASON_ROW,
            old_values={"copied_from_row": str(source.pk)},
            new_values={"batch": batch, "row": str(row.pk), "curriculum": str(source.curriculum_id), "block": block},
        )
    if not counts["pa_rows_added"] and not counts["pa_rows_already"]:
        raise Skip("block_row_missing")


def _source_plan(program, year):
    Curriculum = model("registrar", "Curriculum")
    pool = list(Curriculum.objects.filter(program=program, admission_year__lt=year, is_active=True))
    if not pool:
        return None
    latest = max(row.admission_year for row in pool)
    pool = [row for row in pool if row.admission_year == latest]
    approved = [row for row in pool if row.status == "approved"] or pool
    return max(approved, key=lambda row: (row.version or 0, row.created_at))


def prepare_plans(*, organization, actor, period, batch, counts) -> None:
    from .applications_repair_2026_11_16_people import _target_program

    Curriculum, Row = model("registrar", "Curriculum"), model("registrar", "CurriculumSubject")
    Record = model("registrar", "StudentAcademicRecord")
    group = one_group(organization, B_GROUP, "group_unresolved")
    target = _target_program(organization)
    years = sorted(
        set(
            Record.objects.filter(organization=organization, group=group, is_active=True)
            .filter(program__name__iexact=B_FROM_PROGRAM)
            .values_list("admission_year", flat=True)
        )
        - {None}
    )
    for year in years:
        if Curriculum.objects.filter(program=target, admission_year=year, is_active=True).exists():
            counts["pb_plan_exists"] += 1
            continue
        source = _source_plan(target, year)
        if source is None:
            counts["pb_source_plan_missing"] += 1  # bu il üçün mənbə yoxdur — digər illər yenə hazırlanır
            continue
        now = timezone.now()
        clone = Curriculum.objects.create(
            organization=organization,
            program=target,
            admission_year=year,
            name="",
            status=source.status,
            version=1,
            submitted_at=source.submitted_at and now,
            submitted_by=actor if source.submitted_at else None,
            approved_at=source.approved_at and now,
            approved_by=actor if source.approved_at else None,
            protocol_number=source.protocol_number,
            last_reason=REASON_CLONE[:255],
        )
        rows = []
        for item in Row.objects.filter(curriculum=source).order_by("semester_number", "order", "pk"):
            row = Row(organization=organization, curriculum=clone, subject_id=item.subject_id, order=item.order)
            for field in ROW_FIELDS:
                setattr(row, field, getattr(item, field))
            rows.append(row)
        Row.objects.bulk_create(rows)
        counts["pb_plans_cloned"] += 1
        counts["pb_rows_copied"] += len(rows)
        audit(
            actor=actor,
            organization=organization,
            resource_type=RES_PLAN_CLONE,
            resource_id=clone.pk,
            repr_=f"{target} · {year}",
            reason=REASON_CLONE,
            old_values={"source_curriculum": str(source.pk), "source_year": source.admission_year},
            new_values={"batch": batch, "curriculum": str(clone.pk), "year": year, "rows": len(rows)},
        )
    if not years:
        raise Skip("records_missing")


def undo_row(*, organization, actor, row, batch, counts) -> None:
    Row, Choice = model("registrar", "CurriculumSubject"), model("registrar", "GroupElectiveChoice")
    entry = row
    row = Row.objects.filter(organization=organization, pk=(entry.new_values or {}).get("row")).first()
    if row is None:
        counts["pa_undo_already"] += 1
        return
    if Choice.objects.filter(
        organization=organization, chosen_subject=row.subject, elective_group=row.elective_group
    ).exists():
        counts["pa_undo_in_use"] += 1
        return
    row.delete()
    counts["pa_undo_rows_deleted"] += 1


def undo_clone(*, organization, actor, row, batch, counts) -> None:
    Curriculum, Record = model("registrar", "Curriculum"), model("registrar", "StudentAcademicRecord")
    entry = row
    clone = Curriculum.objects.filter(organization=organization, pk=(entry.new_values or {}).get("curriculum")).first()
    if clone is None:
        counts["pb_undo_already"] += 1
        return
    if Record.objects.filter(curriculum=clone).exists():
        counts["pb_undo_in_use"] += 1
        return
    model("registrar", "CurriculumSubject").objects.filter(curriculum=clone).delete()
    clone.delete()
    counts["pb_undo_plans_deleted"] += 1


__all__ = ["RES_PLAN_CLONE", "RES_PLAN_ROW", "prepare_block", "prepare_plans", "undo_clone", "undo_row"]
