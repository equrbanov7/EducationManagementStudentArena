"""Təsdiqlənmiş tədris planından tapşırıq sətirlərinin TÖRƏDİLMƏSİ (ekran 12).

Zəncir (Mərhələ 2 → Mərhələ 4):

    Curriculum(status=approved) × ixtisasın QRUPLARI × semestr
        → TeachingTaskRow (fənn, ixtisas, fakültə, qruplar, saat bölgüsü)

⚠️ ``curriculum_import.curriculum_row_suggestions``-dan FƏRQİ: o, kafedra
müdirinə TƏKLİF verirdi (sətir yazmırdı) və plan sətrində saat sütunu yox idi.
Mərhələ 2 ``CurriculumSubject``-ə ``credits`` + ``lecture/seminar/lab_hours``
əlavə etdi, ona görə tədris şöbəsi indi sətri BİRBAŞA doldura bilir.

QAYDALAR
--------
* Mənbə YALNIZ ``PlanStatus.APPROVED`` plandır — qaralama plan sətir vermir
  (ekran 07-nin «Plan yoxdur» bloklayıcısı ilə eyni meyar).
* **İDEMPOTENT**: eyni (fənn, ixtisas, semestr nömrəsi) üçün sətir varsa
  təkrarlanmır; mövcud sətrin saatları ƏZİLMİR (tədris şöbəsi əl ilə
  düzəldibsə itmir).
* Qruplar ixtisasın alt-ağacından, kursa görə seçilir
  (``kurs = ceil(semestr / 2)``, qrup metadatası ``OrgUnit.settings``-dədir).
  Kursu uyğun gələn qrup yoxdursa sətir YENƏ yaranır — qruplar sonra əl ilə
  bağlanır (``groups_text`` boş qalır).
* Fəsil semestr nömrəsinin paritetindən: tək → Payız, cüt → Yaz.
"""

from __future__ import annotations

import math

from django.apps import apps as django_apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

from ..constants import (
    HOURS_PER_CREDIT,
    SEASON_BY_SEMESTER_PARITY,
    DegreeLevel,
    RowKind,
    Season,
)
from ..models import TeachingTaskRow
from .curriculum_import import chair_specialty_ids
from .scoping import WorkloadDenied, ensure_can_manage
from .tasks import resolve_specialty_and_faculty

_APPROVED = "approved"
_DEGREE_VALUES = {str(value) for value, _ in DegreeLevel.choices}


def _plan_rows_for(organization, program_ids):
    """Təsdiqlənmiş planların sətirləri (proqram üzrə ən yeni versiya)."""
    Curriculum = django_apps.get_model("registrar", "Curriculum")
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    latest: dict = {}
    for plan in Curriculum.objects.filter(
        organization=organization, program_id__in=list(program_ids), status=_APPROVED
    ).order_by("program_id", "-version", "-admission_year"):
        latest.setdefault(plan.program_id, plan)
    if not latest:
        return [], {}
    rows = list(
        CurriculumSubject.objects.filter(curriculum_id__in=[plan.pk for plan in latest.values()])
        .select_related("subject", "curriculum", "curriculum__program")
        .order_by("curriculum__program__name", "semester_number", "order")
    )
    return rows, latest


def _groups_by_specialty(organization, specialty_ids) -> dict:
    """ixtisas id → [(qrup, kurs)] — kursa görə süzmək üçün."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    specialties = {
        unit.pk: unit for unit in OrgUnit.objects.filter(organization=organization, pk__in=list(specialty_ids))
    }
    result: dict = {pk: [] for pk in specialties}
    for unit in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True).only(
        "id", "name", "path", "settings"
    ):
        path = unit.path or ""
        for pk, specialty in specialties.items():
            if specialty.path and path.startswith(f"{specialty.path}/"):
                settings = unit.settings if isinstance(unit.settings, dict) else {}
                try:
                    course = int(settings.get("course_year") or 0)
                except (TypeError, ValueError):
                    course = 0
                result[pk].append((unit, course))
                break
    return result


def plan_preview(*, organization, chair, academic_year: str) -> dict:
    """Törədiləcək sətirlərin xülasəsi (yazmadan) — «Plandan gətir» dialoqu."""
    specialty_ids = chair_specialty_ids(organization, chair)
    if not specialty_ids:
        return {"programs": [], "row_count": 0, "blocked": []}
    Program = django_apps.get_model("registrar", "Program")
    programs = list(
        Program.objects.filter(
            organization=organization, specialty_unit_id__in=specialty_ids, is_active=True
        ).select_related("specialty_unit")
    )
    plan_rows, latest = _plan_rows_for(organization, [program.pk for program in programs])
    blocked = [program.name for program in programs if program.pk not in latest]
    return {
        "programs": [
            {"id": str(program.pk), "name": program.name, "has_plan": program.pk in latest} for program in programs
        ],
        "row_count": len(plan_rows),
        "blocked": blocked,
        "academic_year": academic_year,
    }


@transaction.atomic
def generate_rows_from_plan(*, task, actor, program_ids=None, request=None) -> dict:
    """Təsdiqlənmiş plandan tapşırıq sətirlərini yaradır (idempotent)."""
    ensure_can_manage(actor, task.chair_id)
    from .. import state_machine as sm

    if task.status not in sm.OFFICE_EDITABLE:
        raise WorkloadDenied(
            "workload.task_not_editable",
            "Sətir yalnız qaralama və ya qaytarılmış sənədə əlavə oluna bilər.",
        )

    organization = task.organization
    specialty_ids = chair_specialty_ids(organization, task.chair)
    if not specialty_ids:
        raise WorkloadDenied("workload.no_specialty", "Kafedranın alt-ağacında ixtisas yoxdur.")

    Program = django_apps.get_model("registrar", "Program")
    programs = Program.objects.filter(organization=organization, specialty_unit_id__in=specialty_ids, is_active=True)
    if program_ids:
        programs = programs.filter(pk__in=list(program_ids))
    programs = list(programs.select_related("specialty_unit"))
    if not programs:
        raise WorkloadDenied("workload.no_program", "İxtisas seçilməyib və ya aktiv ixtisas yoxdur.")

    plan_rows, latest = _plan_rows_for(organization, [program.pk for program in programs])
    blocked = sorted({program.name for program in programs if program.pk not in latest})
    if not plan_rows:
        return {"created": 0, "existing": 0, "blocked": blocked}

    program_by_id = {program.pk: program for program in programs}
    group_map = _groups_by_specialty(organization, specialty_ids)
    # İdempotentlik açarı: (fənn, ixtisas, fəsil, semestr). `order` sahəsi
    # QƏSDƏN semestr nömrəsini daşıyır (aşağıda `order=semester`), ona görə
    # mövcud sətirlər eyni açarla oxunur.
    existing = {
        (row.subject_id, row.specialty_id, row.season, row.order)
        for row in TeachingTaskRow.objects.filter(task=task).only("subject_id", "specialty_id", "season", "order")
    }

    created = 0
    skipped = 0
    for plan_row in plan_rows:
        program = program_by_id.get(plan_row.curriculum.program_id)
        if program is None or not program.specialty_unit_id:
            skipped += 1
            continue
        semester = int(plan_row.semester_number or 0)
        season = str(SEASON_BY_SEMESTER_PARITY.get(semester % 2, Season.FALL))
        key = (plan_row.subject_id, program.specialty_unit_id, season, semester)
        if key in existing:
            skipped += 1
            continue

        specialty, faculty = resolve_specialty_and_faculty(organization, program.specialty_unit_id)
        course = max(math.ceil(semester / 2), 1) if semester else 0
        groups = [unit for unit, group_course in group_map.get(program.specialty_unit_id, []) if group_course == course]

        credits = int(plan_row.credits or getattr(plan_row.subject, "ects", 0) or 0)
        row = TeachingTaskRow(
            organization=organization,
            task=task,
            season=season,
            subject=plan_row.subject,
            subject_text=plan_row.subject.name,
            row_kind=RowKind.TEACHING,
            specialty=specialty,
            faculty=faculty,
            degree_level=(
                program.degree_level if program.degree_level in _DEGREE_VALUES else str(DegreeLevel.BACHELOR)
            ),
            union_count=1,
            subgroup_count=max(len(groups), 1),
            lecture_total=int(plan_row.lecture_hours or 0),
            lecture_plan=int(plan_row.lecture_hours or 0),
            seminar_total=int(plan_row.seminar_hours or 0),
            seminar_plan=int(plan_row.seminar_hours or 0),
            lab_total=int(plan_row.lab_hours or 0),
            lab_plan=int(plan_row.lab_hours or 0),
            credits=str(credits) if credits else "",
            credits_value=credits,
            groups_text=" / ".join(unit.name for unit in groups),
            order=semester,
        )
        row.total_hours = row.computed_total_hours or (credits * HOURS_PER_CREDIT)
        row.save()
        if groups:
            row.groups.set(groups)
        existing.add(key)
        created += 1

    log_action(
        AuditAction.CREATE,
        user=getattr(actor, "user", None),
        organization=organization,
        obj=task,
        new_values={"created": created, "existing": skipped, "blocked": blocked},
        reason="workload.rows_generated_from_plan",
        request=request,
        resource_type="workload.TeachingTask",
        resource_id=str(task.pk),
        resource_repr=f"{task.chair_id} · {task.academic_year}",
    )
    return {"created": created, "existing": skipped, "blocked": blocked}


__all__ = ["generate_rows_from_plan", "plan_preview"]
