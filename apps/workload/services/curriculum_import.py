"""Tədris planından sətir təklifi (spec §7, NK №348 zənciri).

Kredit (R01, 2026-10-21): plan sətrinin ÖZ krediti (``CurriculumSubject.credits`` > 0), yoxdursa fənn
kataloqunun ``Subject.ects``-i — qayda registrar-ın YEGANƏ həlledicisindədir
(``registrar.public.credit_source.plan_row_credit``; tələbə krediti də oradan oxunur).

* kredit — yuxarıdakı qayda;
* saat TƏKLİF olunur: ``credits × 30`` (1 kredit = 30 saat ümumi tədris yükü)
  — bu KONTAKT saatı DEYİL, ona görə ``suggested_total_hours`` ayrıca sahədə
  qaytarılır və sətrə AVTOMATİK yazılmır: kafedra mühazirə/seminar/lab bölgüsünü
  özü doldurur;
* fəsil semestr nömrəsinin paritetindən təklif olunur (tək → Payız, cüt → Yaz).
"""

from __future__ import annotations

from itertools import groupby
from operator import attrgetter

from django.apps import apps as django_apps

from ..constants import HOURS_PER_CREDIT, SEASON_BY_SEMESTER_PARITY, DegreeLevel, RowKind, Season


def _curriculum_subject_model():
    return django_apps.get_model("registrar", "CurriculumSubject")


def _program_model():
    return django_apps.get_model("registrar", "Program")


def chair_specialty_ids(organization, chair) -> list:
    """Kafedranın alt-ağacındakı ixtisas (specialty) ``OrgUnit`` id-ləri."""
    from core.constants import OrgUnitType

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return list(
        OrgUnit.objects.filter(
            organization=organization,
            unit_type=OrgUnitType.SPECIALTY,
            path__startswith=f"{chair.path}/",
        ).values_list("pk", flat=True)
    )


def _credits_for(plan_row) -> int:
    """Kredit dəyəri — plan sətrinin krediti (> 0), yoxdursa fənn kataloqundan (``credit_source.plan_row_credit``)."""
    from apps.registrar.public import credit_source

    return credit_source.plan_row_credit(plan_row)


def curriculum_row_suggestions(*, organization, chair, limit: int = 200) -> list[dict]:
    """Kafedranın ixtisaslarının aktiv tədris planlarından sətir təklifləri."""
    if limit <= 0:
        return []
    specialty_ids = chair_specialty_ids(organization, chair)
    if not specialty_ids:
        return []
    program_ids = list(
        _program_model()
        .objects.filter(organization=organization, specialty_unit_id__in=specialty_ids, is_active=True)
        .values_list("pk", flat=True)
    )
    if not program_ids:
        return []
    plan_rows = (
        _curriculum_subject_model()
        .objects.filter(
            organization=organization,
            curriculum__program_id__in=program_ids,
            curriculum__is_active=True,
        )
        .select_related("subject", "curriculum", "curriculum__program", "curriculum__program__specialty_unit")
        .order_by(
            "curriculum__program__name",
            "curriculum__program_id",
            "semester_number",
            "subject__name",
            "subject_id",
            "-curriculum__admission_year",
            "-curriculum__version",
            "pk",
        )
    )
    suggestions = []
    families = groupby(plan_rows.iterator(), key=attrgetter("curriculum.program_id", "semester_number", "subject_id"))
    for _, family in families:
        variants = {}
        for row in family:
            credits = _credits_for(row)
            contact = (row.lecture_hours, row.seminar_hours, row.lab_hours)
            block = row.elective_group if row.is_elective else ""
            key = (credits, contact, row.is_elective, block)
            year = row.curriculum.admission_year
            if key in variants:
                years = variants[key]["admission_years"]
                if years[-1] != year:  # The family is ordered by newest admission year first.
                    years.append(year)
                continue
            subject = row.subject
            program = row.curriculum.program
            variants[key] = {
                "subject_id": str(subject.pk),
                "subject_code": subject.code,
                "subject_name": subject.name,
                "semester_number": row.semester_number,
                "season": str(SEASON_BY_SEMESTER_PARITY.get(row.semester_number % 2, Season.FALL)),
                "specialty_id": str(program.specialty_unit_id) if program.specialty_unit_id else "",
                "specialty_name": program.name,
                "degree_level": program.degree_level or DegreeLevel.BACHELOR,
                "row_kind": str(RowKind.TEACHING),
                "credits": str(credits) if credits else "",
                "credits_value": credits,
                "suggested_total_hours": credits * HOURS_PER_CREDIT,
                "lecture_hours": row.lecture_hours,
                "seminar_hours": row.seminar_hours,
                "lab_hours": row.lab_hours,
                "is_elective": row.is_elective,
                "elective_group": block,
                "admission_years": [year],
            }
        for variant in variants.values():
            variant["has_variants"] = len(variants) > 1
            suggestions.append(variant)
            if len(suggestions) >= limit:
                return suggestions
    return suggestions


__all__ = ["chair_specialty_ids", "curriculum_row_suggestions"]
