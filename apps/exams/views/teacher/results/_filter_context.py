"""results paketi — süzgəc panelinin şablon konteksti (URL vəziyyəti, seçimlər, xülasə).

2026-10-25: süzgəc vəziyyəti TAM URL-dədir — sıralama başlıqları, səhifələmə və Excel
ixracı eyni parametrləri daşıyır (`filter_query_items`), ona görə ixrac ekranda
görünən süzgəc + sıralama ilə birəbir eynidir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ._filters import day_options, filter_query_items, filters_active, room_options

PER_PAGE_CHOICES = (12, 25, 50, 100)
DEFAULT_PER_PAGE = PER_PAGE_CHOICES[0]


def results_per_page(raw) -> int:
    try:
        value = int(str(raw or "").strip())
    except ValueError:
        return DEFAULT_PER_PAGE
    return value if value in PER_PAGE_CHOICES else DEFAULT_PER_PAGE


def _navigation_items(request, per_page) -> list[tuple[str, str]]:
    items = [
        ("attempt", (request.GET.get("attempt") or "").strip()),
        ("from_section", (request.GET.get("from_section") or "").strip()),
        ("return_to", (request.GET.get("return_to") or "").strip()),
        ("per_page", "" if per_page == DEFAULT_PER_PAGE else str(per_page)),
    ]
    return [(key, value) for key, value in items if value]


def results_filter_context(exam, state, *, request, per_page) -> dict:
    """Şablon üçün süzgəc konteksti (2–3 yüngül aqreqat sorğu: gün, zal, ümumi say)."""
    navigation = _navigation_items(request, per_page)
    active = filters_active(state)
    return {
        "search_query": state["search_query"],
        "status_filter": state["status_filter"],
        "checked_filter": state["checked_filter"],
        "appeal_filter": state["appeal_filter"],
        "room_filter": state["room_filter"],
        "day_filter": state["day_raw"],
        "date_from": state["date_from_raw"],
        "date_to": state["date_to_raw"],
        "score_min": state["score_min"],
        "score_max": state["score_max"],
        "sort_by": state["sort_by"],
        "sort_dir": state["sort_dir"],
        # Köhnə açar (tək dəyər / vergüllə) — testlər və şablon şərtləri üçün.
        "group_filter": state["group_id"] or "",
        "group_filter_values": state["group_values"],
        "filters_active": active,
        "sort_base_query": urlencode(filter_query_items(state, include_sort=False) + navigation),
        "pagination_query": urlencode(filter_query_items(state) + navigation),
        "export_query": urlencode(filter_query_items(state)),
        "day_options": day_options(exam),
        "room_options": room_options(exam),
        "overall_total": exam.attempts.exclude(is_trial=True).count() if active else None,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        "is_test_exam": exam.exam_type == "test",
    }


__all__ = ["DEFAULT_PER_PAGE", "PER_PAGE_CHOICES", "results_filter_context", "results_per_page"]
