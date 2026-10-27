"""«Fənnimə aid apellyasiyalar» kabinet bölməsinin konteksti (``?section=teaching-appeals``, sahib 2026-10-27).

Bölmə şablonu datanı ``{% teaching_appeals_panel %}`` tag-ı ilə render vaxtı alır (accounts Python importu etmir).
Əhatə hər render-də YENİDƏN hesablanır (``services.teaching_scope``): müəllim — öz fənn × tələbə cütləri,
superadmin / RİM rəhbəri — bütün təşkilat. View-as altında ``request.user`` baxılan istifadəçidir → onun əhatəsi.

Sorğu büdcəsi: əhatə (2–3) + qrup xəritəsi (1) + KPI (2) + seçim siyahıları (1) + səhifə (1 + prefetch 4) —
sətir sayından asılı deyil.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from core.tenancy import get_request_organization

from ...constants import APPEAL_STATUS_CHOICES
from ...services.teaching_scope import scoped_appeals
from .teaching_rows import (
    CATEGORIES,
    CTX,
    FILTER_KEYS,
    PREFIX,
    SECTION,
    STATUS_ACCEPTED_ANY,
    apply_filters,
    build_row,
    kpi_tiles,
    read_filters,
    student_group_map,
    with_row_data,
)

PAGE_SIZE = 20


def _open_id(request) -> int:
    try:
        return max(int(request.GET.get(PREFIX + "open") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _category_label(value) -> str:
    """İmtahan modelinin öz etiketi (sətirdəki nişanla eyni dil; exams import edilmir — model adla alınır)."""
    from django.apps import apps as django_apps

    field = django_apps.get_model("exams", "Exam")._meta.get_field("exam_type_extended")
    return str(dict(field.choices).get(value, value))


def _filter_fields(filters, *, subjects, groups) -> list:
    everything = {"value": "", "label": pgettext(CTX, "Hamısı")}
    status_options = [everything] + [{"value": value, "label": str(label)} for value, label in APPEAL_STATUS_CHOICES]
    status_options.append({"value": STATUS_ACCEPTED_ANY, "label": pgettext(CTX, "Qəbul edildi (tam və ya qismən)")})
    return [
        {
            "name": PREFIX + "q",
            "label": pgettext(CTX, "Tələbə və ya imtahan"),
            "kind": "search",
            "value": filters["q"],
            "placeholder": pgettext(CTX, "Ad, soyad, ata adı, istifadəçi adı…"),
            "wide": True,
        },
        {
            "name": PREFIX + "status",
            "label": pgettext(CTX, "Status"),
            "kind": "select",
            "options": status_options,
            "value": filters["status"],
        },
        {
            "name": PREFIX + "subject",
            "label": pgettext(CTX, "Fənn"),
            "kind": "select",
            "options": [everything] + [{"value": str(pk), "label": name} for pk, name in subjects],
            "value": filters["subject"],
            "searchable": True,
        },
        {
            "name": PREFIX + "group",
            "label": pgettext(CTX, "Qrup"),
            "kind": "select",
            "options": [everything] + [{"value": name, "label": name} for name in groups],
            "value": filters["group"],
            "searchable": True,
        },
        {
            "name": PREFIX + "category",
            "label": pgettext(CTX, "Kateqoriya"),
            "kind": "select",
            "options": [everything] + [{"value": value, "label": _category_label(value)} for value in CATEGORIES],
            "value": filters["category"],
        },
        {"name": PREFIX + "from", "label": pgettext(CTX, "Tarixdən"), "kind": "date", "value": filters["from"]},
        {"name": PREFIX + "to", "label": pgettext(CTX, "Tarixədək"), "kind": "date", "value": filters["to"]},
    ]


def filter_query(filters) -> dict:
    return {PREFIX + key: filters[key] for key in FILTER_KEYS if filters.get(key)}


def build_teaching_panel(request) -> dict:
    """Bölmənin bütün ekranı: KPI, süzgəclər, səhifələnmiş sətirlər, ixrac linki, çekməcə URL-i."""
    organization = get_request_organization(request)
    user = getattr(request, "user", None)
    if organization is None or not getattr(user, "is_authenticated", False):
        return {"state": "no_org"}
    scoped, org_wide = scoped_appeals(user, organization)
    filters = read_filters(request)
    group_map = student_group_map(scoped)
    base = apply_filters(scoped, filters, group_map=group_map, with_status=False)
    rows_qs = apply_filters(base, {**filters, "group": ""}, with_status=True).order_by("-created_at", "-id")
    page = Paginator(with_row_data(rows_qs), PAGE_SIZE).get_page(request.GET.get(PREFIX + "page") or 1)
    rows = [build_row(appeal, group_map) for appeal in page.object_list]
    subjects = sorted(
        {
            (pk, name)
            for pk, name in scoped.order_by().values_list("exam__subject_id", "exam__subject__name").distinct()
            if pk and name
        },
        key=lambda pair: pair[1].lower(),
    )
    groups = sorted(set(group_map.values()), key=str.lower)
    query = filter_query(filters)
    is_filtered = bool(query)
    count = page.paginator.count
    return {
        "state": "ready",
        "org_wide": org_wide,
        "rows": rows,
        "page_obj": page,
        "pagination_query": urlencode({"section": SECTION, **query}),
        "kpi_tiles": kpi_tiles(base, filters["status"]),
        "filter_fields": _filter_fields(filters, subjects=subjects, groups=groups),
        "count_label": pgettext(CTX, "Nəticə: %(n)s müraciət") % {"n": count},
        "export_url": reverse("appeals:teaching_appeals_export") + ("?" + urlencode(query) if query else ""),
        "detail_base_url": reverse("appeals:teaching_appeals"),
        "open_id": _open_id(request),
        "is_filtered": is_filtered,
        "has_any": scoped.exists() if not count else True,
    }


__all__ = ["PAGE_SIZE", "build_teaching_panel", "filter_query"]
