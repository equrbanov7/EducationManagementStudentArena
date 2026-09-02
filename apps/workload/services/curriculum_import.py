"""Tədris planından sətir təklifi (spec §7, NK №348 zənciri).

⚠️ MÖVCUD SXEMİN HƏQİQƏTİ (2026-09 auditi): ``registrar.CurriculumSubject``-də
NƏ kredit, NƏ saat sütunu var — plan sətri yalnız ``subject`` + ``semester_number``
+ seçmə blok məlumatını daşıyır. Ona görə idxal DEQRADASİYA İLƏ işləyir:

* kredit ``Subject.ects``-dən götürülür (fənn kataloqunun dəyəri);
* saat TƏKLİF olunur: ``credits × 30`` (1 kredit = 30 saat ümumi tədris yükü)
  — bu KONTAKT saatı DEYİL, ona görə ``suggested_total_hours`` ayrıca sahədə
  qaytarılır və sətrə AVTOMATİK yazılmır: kafedra mühazirə/seminar/lab bölgüsünü
  özü doldurur;
* fəsil semestr nömrəsinin paritetindən təklif olunur (tək → Payız, cüt → Yaz).

``CurriculumSubject``-ə kredit/saat sütunları əlavə olunanda burada YALNIZ
``_credits_for`` dəyişir (çağıran səth eyni qalır).
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
    """Kredit dəyəri — plan sətrində sütun yoxdursa fənn kataloqundan."""
    for attribute in ("credits", "ects", "credit_value"):
        value = getattr(plan_row, attribute, None)
        if value:
            return int(value)
    subject = getattr(plan_row, "subject", None)
    return int(getattr(subject, "ects", 0) or 0)


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
