"""Ekran 07 «Semestr açılışı» — OXU + AÇILIŞ TÖRƏTMƏ servisi.

Nə edir: TƏSDİQLƏNMİŞ tədris planının verilmiş semestr sətirlərindən hər qrup
üçün ``CourseOffering`` yaradır, əhatə (coverage) KPI-larını hesablayır,
bloklayıcıları («Plan yoxdur», müəllimsiz açılış, jurnalsız açılış) sadalayır
və 5 addımlı stepper-in vəziyyətini verir.

──────────────────────────────────────────────────────────────────────────────
ZƏMANƏTLƏR
──────────────────────────────────────────────────────────────────────────────
* **İDEMPOTENT** — eyni parametrlərlə təkrar çağırış YENİ sətir yaratmır
  (``get_or_create`` unikal açar: organization + subject + period + group).
* **HEÇ NƏ SİLİNMİR** — mövcud açılışın müəllimi, saatı və jurnalı toxunulmur;
  yalnız ÇATIŞMAYAN sətirlər əlavə olunur (handoff §8 qayda 5).
* **Müəllim OPSİONALDIR** — təyinat sonra dərs yükü modulundan gəlir
  (``apps.workload.services.distribution.sync_offerings``); açılış «Müəllim
  gözləyir» statusunda yaranır.
* **«Plan yoxdur» = BLOKLAYICI** (§6.1) — təsdiqlənmiş planı olmayan ixtisas
  üçün açılış YARADILMIR və səbəb istifadəçiyə ADLA göstərilir.

MODUL SƏRHƏDİ: ``apps.organizations`` STATİK import EDİLMİR.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils.translation import pgettext

from core.permissions import has_permission

from .curriculum_registry import programs_without_approved_plan
from .models import CourseOffering, Curriculum, CurriculumSubject, Program, StudentAcademicRecord
from .models.curriculum_meta import PlanStatus

_CTX = "accounts.semester"

PERM_VIEW = "semester.view"
PERM_OPEN = "semester.open"
PERM_LOCK = "semester.lock"
PERM_UNLOCK = "semester.unlock"


def actor_permissions(request) -> list:
    return list(getattr(request, "org_permissions", []) or [])


def can_view_semester(request) -> bool:
    return has_permission(actor_permissions(request), PERM_VIEW)


def can_open_semester(request) -> bool:
    return has_permission(actor_permissions(request), PERM_OPEN)


def can_lock_semester(request) -> bool:
    return has_permission(actor_permissions(request), PERM_LOCK)


def can_unlock_semester(request) -> bool:
    return has_permission(actor_permissions(request), PERM_UNLOCK)


def _period_model():
    return django_apps.get_model("organizations", "AcademicPeriod")


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def groups_for_program(organization, program):
    """İxtisasın altındakı AKTİV qruplar (materialized path ilə tək sorğu)."""
    OrgUnit = _org_unit_model()
    unit = program.specialty_unit
    if unit is None:
        return OrgUnit.objects.none()
    return OrgUnit.objects.filter(
        organization=organization, is_active=True, unit_type="group", path__startswith=f"{unit.path}/"
    ).order_by("name")


def approved_plan_for(organization, program):
    """İxtisasın ƏN SON təsdiqlənmiş planı (yoxdursa None → bloklayıcı)."""
    return (
        Curriculum.objects.filter(
            organization=organization, program=program, status=PlanStatus.APPROVED, is_active=True
        )
        .order_by("-admission_year", "-version")
        .first()
    )


@transaction.atomic
def generate_offerings(*, organization, period, programs, semester_number, actor=None):
    """Təsdiqlənmiş plandan açılış yaradır — İDEMPOTENT, heç nə silmir.

    Qaytarır: ``{"created", "existing", "skipped_no_plan", "skipped_no_group",
    "blocked_programs", "offering_ids"}``.
    """
    counters = {"created": 0, "existing": 0, "skipped_no_plan": 0, "skipped_no_group": 0}
    blocked: list = []
    offering_ids: list = []

    for program in programs:
        plan = approved_plan_for(organization, program)
        if plan is None:
            counters["skipped_no_plan"] += 1
            blocked.append({"id": str(program.id), "label": program.display_label})
            continue

        groups = list(groups_for_program(organization, program))
        if not groups:
            counters["skipped_no_group"] += 1
            continue

        rows = list(
            CurriculumSubject.objects.filter(curriculum=plan, semester_number=semester_number).select_related("subject")
        )
        for row in rows:
            lesson_hours = row.lecture_hours + row.seminar_hours + row.lab_hours
            for group in groups:
                offering, created = CourseOffering.objects.get_or_create(
                    organization=organization,
                    subject=row.subject,
                    period=period,
                    group=group,
                    # ⚠️ `instructor` DEFAULTS-da YOXDUR: mövcud açılışın müəllimi
                    # heç vaxt sıfırlanmır (idempotentlik = mövcud data toxunulmazlığı).
                    defaults={"lesson_hours": lesson_hours},
                )
                offering_ids.append(str(offering.pk))
                if created:
                    counters["created"] += 1
                else:
                    counters["existing"] += 1
                    # Saat plandan gəlir: sətir dəyişibsə açılışın saatı yenilənir,
                    # amma YALNIZ o hələ 0-dırsa və ya plandan fərqlidirsə.
                    if lesson_hours and offering.lesson_hours != lesson_hours:
                        offering.lesson_hours = lesson_hours
                        offering.save(update_fields=["lesson_hours", "updated_at"])

    return {**counters, "blocked_programs": blocked, "offering_ids": offering_ids}


def coverage(organization, period) -> dict:
    """Açılış əhatəsi — KPI sırasının mənbəyi (heç nə saxlanılmır, §8/13)."""
    offerings = CourseOffering.objects.filter(organization=organization, period=period, is_active=True)
    total = offerings.count()
    with_instructor = offerings.filter(instructor__isnull=False).count()
    with_course = offerings.filter(course__isnull=False).count()
    hours = offerings.aggregate(total=Sum("lesson_hours"))["total"] or 0
    # Sillabusu olmayan fənlər (handoff §8 qayda 12) — sillabus modulu yoxdursa
    # sayğac None qalır və UI xanası «—» göstərir (uydurma 0 YAZILMIR).
    without_syllabus = None
    try:
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        approved_subjects = set(
            Syllabus.objects.filter(organization=organization, status="approved").values_list("subject_id", flat=True)
        )
        without_syllabus = offerings.exclude(subject_id__in=approved_subjects).count()
    except Exception:  # pragma: no cover — sillabus modeli yoxdursa KPI boş qalır
        without_syllabus = None

    return {
        "total": total,
        "with_instructor": with_instructor,
        "without_instructor": total - with_instructor,
        "with_journal": with_course,
        "without_journal": total - with_course,
        "without_syllabus": without_syllabus,
        "hours": hours,
        "instructor_pct": round(100 * with_instructor / total, 1) if total else 0,
    }


def offering_status_key(offering) -> str:
    """`offering` status ailəsinin açarı (saxlanılmır — hesablanır)."""
    if not offering.is_active:
        return "cancelled"
    if offering.course_id:
        return "journal_open"
    if offering.instructor_id:
        return "teacher_assigned"
    return "awaiting_teacher"


def semester_steps(period, stats: dict, blockers: list) -> list:
    """5 addımlı stepper — «done / current / todo / error» vəziyyətləri.

    Yalnız «göndərildi» və «kilidləndi» SAXLANILIR (``opening_status``); qalan
    üç addım açılış sətirlərindən hesablanır.
    """
    total = stats["total"]
    created_done = total > 0
    sent_done = period.opening_status in ("sent", "locked")
    assigned_done = created_done and stats["without_instructor"] == 0
    journal_done = created_done and stats["without_journal"] == 0
    locked_done = period.locked_at is not None

    flags = [created_done, sent_done, assigned_done, journal_done, locked_done]
    labels = [
        pgettext(_CTX, "Plandan açılış yaradıldı"),
        pgettext(_CTX, "Kafedraya göndərildi"),
        pgettext(_CTX, "Müəllim təyin olundu"),
        pgettext(_CTX, "Jurnal açıldı"),
        pgettext(_CTX, "Semestr kilidləndi"),
    ]
    notes = [
        pgettext(_CTX, "%(n)d açılış sətri") % {"n": total},
        pgettext(_CTX, "Kafedralar müəllim təyinatına başlaya bilər"),
        pgettext(_CTX, "%(n)d açılış müəllim gözləyir") % {"n": stats["without_instructor"]},
        pgettext(_CTX, "%(n)d açılışın jurnalı açılmayıb") % {"n": stats["without_journal"]},
        pgettext(_CTX, "Kilid geri qaytarılmır — açmaq üçün ayrıca səlahiyyət lazımdır"),
    ]

    steps = []
    current_assigned = False
    for index, done in enumerate(flags):
        if done:
            state = "done"
        elif not current_assigned:
            state = "error" if (index == 0 and blockers) else "current"
            current_assigned = True
        else:
            state = "todo"
        steps.append({"label": labels[index], "note": notes[index], "state": state})
    return steps


def build_semester_opening(request, organization) -> dict:
    """«Semestr açılışı» konteksti (dövr seçimi URL sorğusundan)."""
    if not can_view_semester(request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(
                _CTX, "Semestr açılışına baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin."
            ),
        }

    AcademicPeriod = _period_model()
    period_id = (request.GET.get("sm_period") or "").strip()
    periods = list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")[:40])
    period = None
    if period_id:
        period = next((item for item in periods if str(item.id) == period_id), None)
    if period is None:
        period = next((item for item in periods if item.is_current), None) or (periods[0] if periods else None)

    payload = {
        "has_access": True,
        "can_open": can_open_semester(request),
        "can_lock": can_lock_semester(request),
        "can_unlock": can_unlock_semester(request),
        "period_options": [{"value": str(item.id), "label": f"{item.year_display} · {item.name}"} for item in periods],
        "program_options": [
            {"value": str(item.id), "label": item.display_label}
            for item in Program.objects.filter(organization=organization, is_archived=False).order_by("name")[:500]
        ],
        "filters": {"period": str(period.id) if period else "", "chair": (request.GET.get("sm_chair") or "").strip()},
        "period": None,
        "rows": [],
        "steps": [],
        "blockers": programs_without_approved_plan(organization),
        "table_state": "empty",
    }
    if period is None:
        return payload

    stats = coverage(organization, period)
    chair = payload["filters"]["chair"]
    offerings = (
        CourseOffering.objects.filter(organization=organization, period=period)
        .select_related("subject", "group", "instructor", "course", "subject__chair_unit")
        .order_by("subject__code", "group__name")
    )
    if chair:
        offerings = offerings.filter(subject__chair_unit_id=chair)

    student_counts = dict(
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True, group__isnull=False)
        .values_list("group_id")
        .annotate(total=Count("id"))
    )

    rows = []
    for offering in offerings[:400]:
        rows.append(
            {
                "id": str(offering.id),
                "subject_code": offering.subject.code,
                "subject_name": offering.subject.name,
                "group_name": offering.group.name if offering.group_id else "—",
                "chair_name": offering.subject.chair_unit.name if offering.subject.chair_unit_id else "—",
                "students": student_counts.get(offering.group_id, 0),
                "hours": offering.lesson_hours,
                "instructor": (
                    (offering.instructor.get_full_name() or offering.instructor.username)
                    if offering.instructor_id
                    else ""
                ),
                "status_key": offering_status_key(offering),
                "is_active": offering.is_active,
            }
        )

    payload.update(
        {
            "period": {
                "id": str(period.id),
                "name": period.name,
                "year": period.year_display,
                "start_date": period.start_date,
                "end_date": period.end_date,
                "is_current": period.is_current,
                "opening_status": period.opening_status,
                "is_locked": period.locked_at is not None,
                "locked_at": period.locked_at,
                "lock_reason": period.lock_reason,
            },
            "stats": stats,
            "rows": rows,
            "steps": semester_steps(period, stats, payload["blockers"]),
            "table_state": "ready" if rows else "empty",
            "chair_options": [
                {"value": str(unit.id), "label": unit.name}
                for unit in _org_unit_model()
                .objects.filter(organization=organization, is_active=True, unit_type__in=("chair", "department"))
                .order_by("name")
            ],
            # Kilid QAPISI: üç şərt (handoff ekran 07). Düymə GİZLƏNMİR — disabled olur.
            "lock_gates": [
                {
                    "key": "approved_plan",
                    "label": pgettext(_CTX, "Açılışlar təsdiqlənmiş plandan gəlir"),
                    "ok": not payload["blockers"],
                },
                {
                    "key": "instructors",
                    "label": pgettext(_CTX, "Bütün açılışlara müəllim təyin olunub"),
                    "ok": stats["total"] > 0 and stats["without_instructor"] == 0,
                },
                {
                    "key": "journals",
                    "label": pgettext(_CTX, "Elektron jurnallar açılıb"),
                    "ok": stats["total"] > 0 and stats["without_journal"] == 0,
                },
            ],
        }
    )
    payload["can_lock_now"] = all(gate["ok"] for gate in payload["lock_gates"]) and not payload["period"]["is_locked"]
    return payload


def offering_counts_by_chair(organization, period) -> list:
    """Kafedra üzrə açılış/saat bölgüsü (ekran 07-nin «kafedralar» paneli)."""
    rows = (
        CourseOffering.objects.filter(organization=organization, period=period, is_active=True)
        .values("subject__chair_unit_id", "subject__chair_unit__name")
        .annotate(
            total=Count("id"),
            assigned=Count("id", filter=Q(instructor__isnull=False)),
            hours=Sum("lesson_hours"),
        )
        .order_by("-total")
    )
    return [
        {
            "chair_id": str(row["subject__chair_unit_id"]) if row["subject__chair_unit_id"] else "",
            "name": row["subject__chair_unit__name"] or "—",
            "total": row["total"],
            "assigned": row["assigned"],
            "hours": row["hours"] or 0,
            "pct": round(100 * row["assigned"] / row["total"], 1) if row["total"] else 0,
        }
        for row in rows
    ]


__all__ = [
    "PERM_LOCK",
    "PERM_OPEN",
    "PERM_UNLOCK",
    "PERM_VIEW",
    "approved_plan_for",
    "build_semester_opening",
    "can_lock_semester",
    "can_open_semester",
    "can_unlock_semester",
    "can_view_semester",
    "coverage",
    "generate_offerings",
    "groups_for_program",
    "offering_counts_by_chair",
    "offering_status_key",
    "semester_steps",
]
