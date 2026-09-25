"""Nəticə filtrlərinin seçimləri — KASKADLI və ƏHATƏLİ (yalnız istifadəçinin görə
bildiyi cavablarda mövcud olan dəyərlər, sayları ilə).

Kaskad: fakültə → kafedra → (müəllim) → fənn → qrup; ixtisas və kurs kafedraya
tabedir. Seçilmiş dəyər valideyn filtrinə uyğun gəlmirsə (məs. kafedra başqa
fakültədədir) o, ``effective`` filtrlərdən ATILIR — UI-da görünən seçim ilə
serverin tətbiq etdiyi filtr həmişə eyni qalır.

Müəllim seçimi server tərəfli axtarışdır (:func:`teacher_choices`): dözümlü
az/ing klaviatura regex-i (``core.search_text``, ``person_q`` ilə eyni qayda),
səhifələnmiş, fakültə/kafedra filtrinə tabe. Hər funksiya 1 sorğudur.
"""

from __future__ import annotations

from dataclasses import replace

from django.db.models import Count

from core.search_text import tolerant_q

from . import filters as flt


def campaign_choices(organization) -> list:
    """Dövr seçicisi üçün YÜNGÜL kampaniya siyahısı (1 sorğu, yeni dövr birinci):
    ``[{"id", "period_id", "period_name", "academic_year", "start_date",
    "effective_status", "min_group_size"}]`` — ``campaigns_for``-dan fərqli olaraq
    cavab/qəbz saylarını hesablamır."""
    from django.utils import timezone

    from ..models import SurveyCampaign

    if organization is None:
        return []
    today = timezone.localdate()
    return [
        {
            "id": campaign.pk,
            "period_id": campaign.period_id,
            "period_name": campaign.period.name,
            "academic_year": campaign.period.academic_year,
            "start_date": campaign.period.start_date,
            "effective_status": campaign.effective_status(today),
            "min_group_size": campaign.min_group_size,
        }
        for campaign in SurveyCampaign.objects.filter(organization=organization)
        .select_related("period")
        .order_by("-period__start_date", "-created_at")
    ]


def _options(queryset, key, label) -> list:
    return [
        {"id": row[key], "label": row[label] or "", "n": row["n"]}
        for row in queryset.exclude(**{f"{key}__isnull": True})
        .values(key, label)
        .annotate(n=Count("id"))
        .order_by(label, key)
    ]


def _keep(value, options):
    if value is None:
        return None
    return value if any(str(option["id"]) == str(value) for option in options) else None


def filter_choices(organization, scope, filters, campaign_ids) -> dict:
    """``{"faculties", "departments", "subjects", "groups", "programs", "course_years",
    "effective"}`` — hər siyahı ``[{"id", "label", "n"}]``; ``effective`` — valideyn
    kaskadına uyğunlaşdırılmış ``ResultFilters`` (uyğunsuz seçimlər atılıb)."""
    filters = filters or flt.ResultFilters()
    campaign_ids = list(campaign_ids or [])
    empty = {key: [] for key in ("faculties", "departments", "subjects", "groups", "programs", "course_years")}
    if not campaign_ids or not scope.has_structure_access:
        return {**empty, "effective": filters}

    def base(**parents):
        return flt.responses(organization, scope, flt.ResultFilters(**parents), campaign_ids)

    faculties = _options(base(), "faculty_id", "faculty__name")
    faculty_id = _keep(filters.faculty_id, faculties)
    departments = _options(base(faculty_id=faculty_id), "teacher_department_id", "teacher_department__name")
    department_id = _keep(filters.department_id, departments)
    parents = {"faculty_id": faculty_id, "department_id": department_id, "teacher_id": filters.teacher_id}
    subjects = _options(base(**parents), "subject_id", "subject__name")
    subject_id = _keep(filters.subject_id, subjects)
    groups = _options(base(**parents, subject_id=subject_id), "group_id", "group__name")
    unit_parents = {"faculty_id": faculty_id, "department_id": department_id}
    programs = _options(base(**unit_parents), "program_id", "program__name")
    course_years = [
        {"id": year, "label": str(year), "n": count}
        for year, count in base(**unit_parents)
        .exclude(course_year__isnull=True)
        .values("course_year")
        .annotate(n=Count("id"))
        .order_by("course_year")
        .values_list("course_year", "n")
    ]
    effective = replace(
        filters,
        faculty_id=faculty_id,
        department_id=department_id,
        subject_id=subject_id,
        group_id=_keep(filters.group_id, groups),
        program_id=_keep(filters.program_id, programs),
        course_year=_keep(filters.course_year, course_years),
    )
    return {
        "faculties": faculties,
        "departments": departments,
        "subjects": subjects,
        "groups": groups,
        "programs": programs,
        "course_years": course_years,
        "effective": effective,
    }


def _teacher_base(organization, scope, filters, campaign_ids):
    unit_filters = flt.ResultFilters(faculty_id=filters.faculty_id, department_id=filters.department_id)
    return flt.responses(organization, scope, unit_filters, campaign_ids).exclude(teacher__isnull=True)


def _display_name(first, last, username) -> str:
    return f"{first or ''} {last or ''}".strip() or (username or "")


def teacher_choices(organization, scope, filters, campaign_ids, *, query="", limit=20, offset=0) -> dict:
    """``{"results": [{"id", "text", "n"}], "has_more"}`` — ``EMSSearchableSelect`` müqaviləsi.

    Yalnız əhatədəki (cavabı olan) müəllimlər; boş sorğu → ada görə siyahı.
    """
    filters = filters or flt.ResultFilters()
    campaign_ids = list(campaign_ids or [])
    if not campaign_ids or not scope.has_structure_access:
        return {"results": [], "has_more": False}
    limit = max(1, min(int(limit or 20), 50))
    offset = max(0, int(offset or 0))
    base = _teacher_base(organization, scope, filters, campaign_ids)
    name_q = tolerant_q(query, ("teacher__first_name", "teacher__last_name", "teacher__username"))
    if name_q is not None:
        base = base.filter(name_q)
    rows = list(
        base.values("teacher_id", "teacher__first_name", "teacher__last_name", "teacher__username")
        .annotate(n=Count("id"))
        .order_by("teacher__first_name", "teacher__last_name", "teacher_id")[offset : offset + limit + 1]
    )
    return {
        "results": [
            {
                "id": row["teacher_id"],
                "text": _display_name(row["teacher__first_name"], row["teacher__last_name"], row["teacher__username"]),
                "n": row["n"],
            }
            for row in rows[:limit]
        ],
        "has_more": len(rows) > limit,
    }


def teacher_label(organization, scope, filters, campaign_ids, teacher_id) -> str:
    """Seçilmiş müəllimin adı — YALNIZ əhatədə cavabı varsa (əks halda boş sətir)."""
    campaign_ids = list(campaign_ids or [])
    if teacher_id is None or not campaign_ids or not scope.has_structure_access:
        return ""
    row = (
        _teacher_base(organization, scope, filters or flt.ResultFilters(), campaign_ids)
        .filter(teacher_id=teacher_id)
        .values_list("teacher__first_name", "teacher__last_name", "teacher__username")
        .first()
    )
    return _display_name(*row) if row else ""
