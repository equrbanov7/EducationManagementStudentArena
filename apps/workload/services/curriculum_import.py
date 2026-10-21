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
        .order_by("curriculum__program__name", "semester_number", "order")[:limit]
    )

    suggestions: list[dict] = []
    seen: set = set()
    for plan_row in plan_rows:
        subject = plan_row.subject
        program = plan_row.curriculum.program
        key = (subject.pk, plan_row.semester_number, program.pk)
        if key in seen:
            continue
        seen.add(key)
        credits = _credits_for(plan_row)
        suggestions.append(
            {
                "subject_id": str(subject.pk),
                "subject_code": subject.code,
                "subject_name": subject.name,
                "semester_number": plan_row.semester_number,
                "season": str(SEASON_BY_SEMESTER_PARITY.get(plan_row.semester_number % 2, Season.FALL)),
                "specialty_id": str(program.specialty_unit_id) if program.specialty_unit_id else "",
                "specialty_name": program.name,
                "degree_level": program.degree_level or DegreeLevel.BACHELOR,
                "row_kind": str(RowKind.TEACHING),
                "credits": str(credits) if credits else "",
                "credits_value": credits,
                "suggested_total_hours": credits * HOURS_PER_CREDIT,
                "is_elective": bool(plan_row.is_elective),
                "elective_group": plan_row.elective_group,
            }
        )
    return suggestions


__all__ = ["chair_specialty_ids", "curriculum_row_suggestions"]
