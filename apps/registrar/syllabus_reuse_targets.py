"""Sillabusun təkrar istifadəsi üçün AÇILIŞ tərəfi (registrar sahibliyində).

``apps.syllabus`` registrar-ı idxal etmir; «müəllimin bu fənn + semestr üzrə
açılışları» və onların saat bölgüsü məhz burada, açılış modelinin sahibində
hesablanır (accounts glue ``registrar.public`` vasitəsilə çağırır).

``plan_hours_by_offering`` — :func:`.plan_hours.plan_hours_for_offering`-in TOPLU
qarşılığı: açılış sayından asılı olmayaraq SABİT sayda sorğu (ixtisas, plan
sətirləri, dərs yükü sətirləri + onların qrupları).  Seçim qaydası tək-açılış
funksiyası ilə EYNİDİR (paritet testi: ``apps/syllabus/tests/test_reuse_queries.py``).
"""

from __future__ import annotations

from .models import CourseOffering, CurriculumSubject, PlanStatus, Program
from .plan_hours import _row_hours
from .plan_hours_load import workload_hours_by_offering

#: Kafedra həlli ``group → ixtisas → fakültə → universitet`` ağacında gəzir —
#: üç səviyyə əvvəlcədən yüklənir ki, ``resolve_ancestor`` əlavə sorğu açmasın.
_RELATED = (
    "subject",
    "period",
    "group",
    "group__parent",
    "group__parent__parent",
    "group__parent__parent__parent",
)


def instructor_offering(*, organization, user, offering_id):
    """Aktorun ÖZ aktiv açılışı (başqasınınkı ``None`` — fail-closed)."""
    if organization is None or user is None or not offering_id:
        return None
    return (
        CourseOffering.objects.filter(organization=organization, pk=offering_id, instructor=user, is_active=True)
        .select_related(*_RELATED)
        .first()
    )


def instructor_offerings(*, organization, user, subject_id, period_id) -> list:
    """Aktorun bu fənn + semestr üzrə BÜTÜN aktiv açılışları (qrup adına görə)."""
    if organization is None or user is None or subject_id is None or period_id is None:
        return []
    return list(
        CourseOffering.objects.filter(
            organization=organization, instructor=user, is_active=True, subject_id=subject_id, period_id=period_id
        )
        .select_related(*_RELATED)
        .order_by("group__name", "pk")
    )


def _programs_by_unit(organization_id, unit_ids) -> dict:
    """``{ixtisas_bölməsi_id: Program}`` — ``program_for_offering``-in ``.first()`` sırası ilə."""
    if not unit_ids:
        return {}
    programs: dict = {}
    for program in Program.objects.filter(organization_id=organization_id, specialty_unit_id__in=list(unit_ids)):
        programs.setdefault(program.specialty_unit_id, program)
    return programs


def _plan_rows_by_subject(organization_id, subject_ids) -> dict:
    """``{fənn_id: [CurriculumSubject…]}`` — ən yeni qəbul ili / versiya birinci."""
    rows: dict = {}
    queryset = (
        CurriculumSubject.objects.filter(
            organization_id=organization_id,
            subject_id__in=list(subject_ids),
            curriculum__status=PlanStatus.APPROVED,
        )
        .select_related("curriculum")
        .order_by("-curriculum__admission_year", "-curriculum__version")
    )
    for row in queryset:
        rows.setdefault(row.subject_id, []).append(row)
    return rows


def plan_hours_by_offering(offerings) -> dict:
    """``{açılış_id: saat bölgüsü}`` — ``plan_hours_for_offering`` ilə eyni sıra, toplu.

    Sahib 2026-10-25: (1) qrupun ÖZ ixtisasının planı, (2) yükdə BİR QRUPA düşən pay
    (``plan_hours_load``), (3) fənnin istənilən planı; RİM açarı söndürülüdə plan → yük.
    """
    from core.academic_rules import syllabus_hours_from_load

    offerings = [offering for offering in offerings if offering is not None]
    if not offerings:
        return {}
    organization_id = offerings[0].organization_id
    unit_ids = {offering.group.parent_id for offering in offerings if offering.group_id and offering.group.parent_id}
    programs = _programs_by_unit(organization_id, unit_ids)
    plan_rows = _plan_rows_by_subject(organization_id, {offering.subject_id for offering in offerings})
    load_first = syllabus_hours_from_load()
    own, fallback = {}, {}
    for offering in offerings:
        rows = plan_rows.get(offering.subject_id, [])
        program = programs.get(offering.group.parent_id) if offering.group_id else None
        chosen = None
        if program is not None:
            chosen = next((row for row in rows if row.curriculum.program_id == program.pk), None)
        own[offering.pk] = _row_hours(chosen) if chosen is not None else {}
        fallback[offering.pk] = own[offering.pk] if chosen is not None else (_row_hours(rows[0]) if rows else {})
    missing = [
        offering
        for offering in offerings
        if not (own if load_first else fallback)[offering.pk] and offering.subject_id and offering.period_id
    ]
    load = workload_hours_by_offering(missing) if missing else {}
    result = {}
    for offering in offerings:
        first = own[offering.pk] if load_first else fallback[offering.pk]
        result[offering.pk] = first or load.get(offering.pk) or (fallback[offering.pk] if load_first else {})
    return result


def programs_by_offering(offerings) -> dict:
    """``{açılış_id: Program|None}`` — ``program_for_offering``-in toplu qarşılığı (1 sorğu)."""
    offerings = [offering for offering in offerings if offering is not None]
    if not offerings:
        return {}
    unit_ids = {offering.group.parent_id for offering in offerings if offering.group_id and offering.group.parent_id}
    programs = _programs_by_unit(offerings[0].organization_id, unit_ids)
    return {
        offering.pk: (programs.get(offering.group.parent_id) if offering.group_id else None) for offering in offerings
    }


__all__ = [
    "instructor_offering",
    "instructor_offerings",
    "plan_hours_by_offering",
    "programs_by_offering",
]
