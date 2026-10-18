"""Qrupun ÖZ qəbul ilinin (kohortunun) təsdiqlənmiş tədris planı — sahib qaydası 2026-10-19.

QAYDA
-----
Hər qrup üçün ``admission_year``-ı qrupun qəbul ilinə bərabər olan TƏSDİQLƏNMİŞ (aktiv) plan götürülür.
Qəbul ili: ``settings.admission_year`` (köçürülmüş «legacy» qrupda yox — orada idxal ilidir), yoxdursa addan
(``organizations.public.group_cohort_year`` → ``group_admission_year``). Eyni kohortun bir neçə təsdiqlənmiş
versiyası varsa — ən yüksək versiya.

Həmin kohort üçün plan yoxdursa (və ya qəbul ili bilinmirsə) ixtisasın ƏN SON təsdiqlənmiş planı tətbiq olunur
(``-admission_year, -version``) və semestr açılışında xəbərdarlıq verilir:
«Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan tətbiq olundu».

İSTEHLAKÇILAR: ``semester_open.generate_offerings`` (açılış), ``plan_hours.plan_hours_for_offering``
(sillabus saatı), ``workload.services.generation`` (dərs yükü tapşırığı — kohort semestr nömrəsindən: tədris
ilinin başlanğıcı − ``ceil(N/2)`` + 1). Fərdi tədris planı (``individual_plan``) tələbənin ÖZ
``StudentAcademicRecord.curriculum``-unu oxuyur — o artıq kohortludur, dəyişmir.

KÖHNƏ AÇILIŞLAR: əvvəlki qayda (bütün qruplara ən son plan) ilə yaradılmış açılışlar SİLİNMİR və yenidən
yaradılmır; :func:`period_cohort_warnings` onları «qrupun öz planında yoxdur» kimi sayır ki, Tədris şöbəsi
lazım olsa «Ləğv et» ilə özü qərar versin.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from django.utils.translation import pgettext

from .models import CourseOffering, Curriculum, CurriculumSubject, Program
from .models.curriculum_meta import PlanStatus

_CTX = "accounts.semester"

COHORT = "cohort"
FALLBACK_NO_PLAN = "no_cohort_plan"
FALLBACK_UNKNOWN_YEAR = "unknown_year"

#: Xəbərdarlıqda sadalanan nümunə sayı.
MAX_EXAMPLES = 5


def group_cohort_year(group):
    from apps.organizations.public import group_cohort_year as _impl

    return _impl(group) if group is not None else None


def approved_plans(organization, program_ids) -> dict:
    """``{program_id: [plan, …]}`` — təsdiqlənmiş aktiv planlar, ``-admission_year, -version`` sırası (1 sorğu)."""
    result: dict = defaultdict(list)
    for plan in Curriculum.objects.filter(
        organization=organization, program_id__in=list(program_ids), status=PlanStatus.APPROVED, is_active=True
    ).order_by("program_id", "-admission_year", "-version"):
        result[plan.program_id].append(plan)
    return dict(result)


class PlanIndex:
    """Bir ixtisasın təsdiqlənmiş planları: kohort → plan (ən yüksək versiya) + ən son plan."""

    def __init__(self, plans):
        plans = list(plans or ())
        self.newest = plans[0] if plans else None
        self.by_year: dict = {}
        for plan in plans:  # sıra -admission_year, -version → ilk rast gələn ən yüksək versiyadır
            self.by_year.setdefault(int(plan.admission_year), plan)

    def __bool__(self):
        return self.newest is not None

    def for_year(self, year):
        """``(plan, status)`` — kohort planı, yoxdursa ən son plan + səbəb."""
        if self.newest is None:
            return None, FALLBACK_NO_PLAN
        if not year:
            return self.newest, FALLBACK_UNKNOWN_YEAR
        plan = self.by_year.get(int(year))
        if plan is not None:
            return plan, COHORT
        return self.newest, FALLBACK_NO_PLAN

    def for_group(self, group):
        year = group_cohort_year(group)
        plan, status = self.for_year(year)
        return plan, status, year


def plan_index_for(organization, program) -> PlanIndex:
    return PlanIndex(approved_plans(organization, [program.pk]).get(program.pk, ()))


def fallback_item(program, group, year, plan, status) -> dict:
    return {
        "program": program.display_label,
        "group": group.name,
        "group_id": str(group.pk),
        "admission_year": year or 0,
        "plan_year": int(plan.admission_year) if plan is not None else 0,
        "reason": status,
    }


def semester_label(program, year, semester) -> str:
    """Dərs yükü xəbərdarlığının sətri — qrup əvəzinə «ixtisas · qəbul ili · semestr»."""
    return pgettext(_CTX, "%(program)s · %(year)s qəbulu · semestr %(n)d") % {
        "program": program.display_label,
        "year": year or "—",
        "n": int(semester),
    }


def _names(items) -> str:
    groups = sorted({item["group"] for item in items})
    text = ", ".join(groups[:MAX_EXAMPLES])
    if len(groups) > MAX_EXAMPLES:
        text += " " + pgettext(_CTX, "və daha %(n)d") % {"n": len(groups) - MAX_EXAMPLES}
    return text


def fallback_messages(items) -> list:
    """Kohort planı tapılmayan qruplar üçün xəbərdarlıq mətnləri (qrup adları ilə)."""
    messages = []
    no_plan = [item for item in items if item["reason"] == FALLBACK_NO_PLAN]
    unknown = [item for item in items if item["reason"] == FALLBACK_UNKNOWN_YEAR]
    if no_plan:
        messages.append(
            pgettext(_CTX, "Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan tətbiq olundu: %(groups)s.")
            % {"groups": _names(no_plan)}
        )
    if unknown:
        messages.append(
            pgettext(_CTX, "Qrupun qəbul ili bilinmir (ad və ayarda yoxdur) — ən son plan tətbiq olundu: %(groups)s.")
            % {"groups": _names(unknown)}
        )
    return messages


# ── Dövr üzrə xəbərdarlıqlar (semestr açılışı ekranı) ────────────────────────


def _start_year(academic_year) -> int:
    match = re.search(r"(\d{4})", str(academic_year or ""))
    return int(match.group(1)) if match else 0


def period_semester_parity(period):
    """Dövrün fəsli → semestr pariteti: payız (avqust–dekabr) 1 (tək), yaz (yanvar–may) 0 (cüt), yay — ``None``."""
    start = getattr(period, "start_date", None)
    if start is None:
        return None
    if start.month >= 8:
        return 1
    if start.month <= 5:
        return 0
    return None


def semester_number_for(group, period):
    """Qrupun bu dövrdə oxuduğu plan semestri (kurs × fəsil); bilinmirsə ``None``."""
    from . import services

    parity = period_semester_parity(period)
    course = services.group_course_year(group, period.academic_year)
    if parity is None or not course:
        return None
    return course * 2 - 1 if parity == 1 else course * 2


def cohort_for_semester(academic_year, semester_number):
    """Dərs yükü qaydası: semestr ``N``-i oxuyan kohort = tədris ilinin başlanğıcı − ``ceil(N/2)`` + 1."""
    start = _start_year(academic_year)
    if not start or not semester_number:
        return None
    return start - max(math.ceil(int(semester_number) / 2), 1) + 1


def period_cohort_warnings(organization, period, *, scope_q=None) -> dict:
    """``{"fallbacks": [...], "mismatch_count": N, "mismatch_examples": [...], "messages": [...]}``.

    Dövrün AKTİV açılışlarının qrupları üzərindən: (1) kohort planı olmayan qruplar (ən son plan tətbiq olunub);
    (2) fənni qrupun öz kohort planının həmin semestrində olmayan açılışlar (köhnə qaydadan qalıb — silinmir).
    Sorğu: açılışlar 1 + ixtisaslar 1 + planlar 1 + plan sətirləri 1.
    """
    offerings = CourseOffering.objects.filter(
        organization=organization, period=period, is_active=True, group__isnull=False
    )
    if scope_q is not None:
        offerings = offerings.filter(scope_q)
    rows = list(offerings.select_related("group", "subject"))
    empty = {"fallbacks": [], "mismatch_count": 0, "mismatch_examples": [], "messages": []}
    if not rows:
        return empty
    programs = [
        program
        for program in Program.objects.filter(organization=organization, specialty_unit__isnull=False).select_related(
            "specialty_unit"
        )
        if program.specialty_unit.path
    ]
    programs.sort(key=lambda item: -len(item.specialty_unit.path))

    def program_of(group):
        path = group.path or ""
        return next((item for item in programs if path.startswith(f"{item.specialty_unit.path}/")), None)

    group_program = {}
    for row in rows:
        if row.group_id not in group_program:
            group_program[row.group_id] = program_of(row.group)
    plans = approved_plans(organization, {program.pk for program in group_program.values() if program})
    indexes = {program_id: PlanIndex(items) for program_id, items in plans.items()}

    resolved = {}  # group_id → (plan, semester)
    fallbacks = {}
    for row in rows:
        group = row.group
        if group.pk in resolved:
            continue
        program = group_program.get(group.pk)
        index = indexes.get(program.pk) if program else None
        if not index:
            resolved[group.pk] = (None, None)
            continue
        plan, status, year = index.for_group(group)
        resolved[group.pk] = (plan, semester_number_for(group, period))
        if status != COHORT:
            fallbacks[group.pk] = fallback_item(program, group, year, plan, status)

    plan_ids = {plan.pk for plan, _semester in resolved.values() if plan is not None}
    plan_subjects = defaultdict(set)
    for curriculum_id, semester, subject_id in CurriculumSubject.objects.filter(
        curriculum_id__in=list(plan_ids)
    ).values_list("curriculum_id", "semester_number", "subject_id"):
        plan_subjects[(curriculum_id, semester)].add(subject_id)

    mismatches = []
    for row in rows:
        plan, semester = resolved.get(row.group_id, (None, None))
        if plan is None or semester is None:
            continue
        if row.subject_id not in plan_subjects.get((plan.pk, semester), set()):
            mismatches.append(f"{row.subject.name} · {row.group.name}")
    mismatches.sort()

    messages = []
    fallback_rows = sorted(fallbacks.values(), key=lambda item: (item["program"], item["group"]))
    messages.extend(fallback_messages(fallback_rows))
    if mismatches:
        messages.append(
            pgettext(
                _CTX,
                "%(n)d açılışın fənni qrupun öz qəbul ili planının bu semestrində yoxdur (əvvəlki qayda ilə ən son "
                "plandan yaradılıb). Açılışlar avtomatik silinmir — lazımsızdırsa «Ləğv et» ilə ləğv edin.",
            )
            % {"n": len(mismatches)}
        )
    return {
        "fallbacks": fallback_rows,
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:MAX_EXAMPLES],
        "messages": messages,
    }


__all__ = [
    "COHORT",
    "FALLBACK_NO_PLAN",
    "FALLBACK_UNKNOWN_YEAR",
    "PlanIndex",
    "approved_plans",
    "cohort_for_semester",
    "fallback_item",
    "fallback_messages",
    "group_cohort_year",
    "period_cohort_warnings",
    "plan_index_for",
    "semester_label",
    "semester_number_for",
]
