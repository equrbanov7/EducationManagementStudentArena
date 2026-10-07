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

from django.apps import apps as django_apps

from .models import CourseOffering, CurriculumSubject, PlanStatus, Program
from .plan_hours import _row_hours

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


def _workload_rows(organization_id, offerings) -> list:
    """Dərs yükü sətirləri (ən təzəsi birinci) + qrup id-ləri — iki sorğu."""
    try:
        TaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:
        return []
    subject_ids = {offering.subject_id for offering in offerings}
    period_ids = {offering.period_id for offering in offerings}
    queryset = (
        TaskRow.objects.filter(
            organization_id=organization_id, subject_id__in=list(subject_ids), period_id__in=list(period_ids)
        )
        .order_by("-updated_at")
        .prefetch_related("groups")
    )
    return [(row, {group.pk for group in row.groups.all()}) for row in queryset]


def _workload_hours(row) -> dict:
    hours = {}
    for kind in ("lecture", "seminar", "lab"):
        value = int(getattr(row, f"{kind}_plan") or 0) or int(getattr(row, f"{kind}_total") or 0)
        if value > 0:
            hours[kind] = value
    return hours


def plan_hours_by_offering(offerings) -> dict:
    """``{açılış_id: saat bölgüsü}`` — ``plan_hours_for_offering`` ilə eyni nəticə, toplu."""
    offerings = [offering for offering in offerings if offering is not None]
    if not offerings:
        return {}
    organization_id = offerings[0].organization_id
    unit_ids = {offering.group.parent_id for offering in offerings if offering.group_id and offering.group.parent_id}
    programs = _programs_by_unit(organization_id, unit_ids)
    plan_rows = _plan_rows_by_subject(organization_id, {offering.subject_id for offering in offerings})
    result, missing = {}, []
    for offering in offerings:
        rows = plan_rows.get(offering.subject_id, [])
        program = programs.get(offering.group.parent_id) if offering.group_id else None
        chosen = None
        if program is not None:
            chosen = next((row for row in rows if row.curriculum.program_id == program.pk), None)
        chosen = chosen or (rows[0] if rows else None)
        hours = _row_hours(chosen) if chosen is not None else {}
        result[offering.pk] = hours
        if not hours and offering.subject_id and offering.period_id:
            missing.append(offering)
    if missing:
        task_rows = _workload_rows(organization_id, missing)
        for offering in missing:
            match = next(
                (
                    row
                    for row, groups in task_rows
                    if row.subject_id == offering.subject_id
                    and row.period_id == offering.period_id
                    and (not offering.group_id or offering.group_id in groups)
                ),
                None,
            )
            result[offering.pk] = _workload_hours(match) if match is not None else {}
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
