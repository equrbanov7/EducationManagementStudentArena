"""Profil "pending-review" və "review-results" bölmələri üçün context-fragment-lər.

Hər funksiya yalnız müvafiq bölmə aktiv olduqda (caller guard-ı) çağırılır və
həmin bölmənin ``context`` açarlarını qaytarır. Davranış köhnə inline bloklarla
eynidir.
"""

from urllib.parse import quote, urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views._dashboard_helpers import (
    _collect_evaluated_review_items,
    _collect_pending_review_items,
    fill_evaluated_checkers,
    fill_evaluated_test_scores,
)


def build_pending_review_context(request) -> dict:
    (
        pending_review_items,
        pending_review_search_query,
        pending_review_filter_type,
        pending_review_filter_status,
        pending_review_submitted_order,
        pending_review_filter_group,
        pending_review_available_groups,
    ) = _collect_pending_review_items(request)
    pending_review_page_obj = Paginator(pending_review_items, 15).get_page(request.GET.get("pr_page", 1))
    pr_extra = ["section=pending-review"]
    if pending_review_search_query:
        pr_extra.append(f"search={pending_review_search_query}")
    if pending_review_filter_type != "all":
        pr_extra.append(f"type={pending_review_filter_type}")
    if pending_review_filter_status != "all":
        pr_extra.append(f"status={pending_review_filter_status}")
    if pending_review_submitted_order != "oldest":
        pr_extra.append(f"submitted_order={pending_review_submitted_order}")
    if pending_review_filter_group:
        pr_extra.append(f"pr_group={pending_review_filter_group}")
    return {
        "pending_review_items": pending_review_items,
        "pending_review_search_query": pending_review_search_query,
        "pending_review_filter_type": pending_review_filter_type,
        "pending_review_filter_status": pending_review_filter_status,
        "pending_review_submitted_order": pending_review_submitted_order,
        "pending_review_filter_group": pending_review_filter_group,
        "pending_review_available_groups": pending_review_available_groups,
        "pending_review_page_obj": pending_review_page_obj,
        "pending_review_pagination_query": "&".join(pr_extra),
    }


def build_review_results_context(request) -> dict:
    from apps.appeals.public import appeal_status_by_attempt

    from .review_results_ui import build_filter_fields, build_kpi_tiles, decorate_rows, empty_state

    (
        evaluated_review_items,
        evaluated_review_search_query,
        evaluated_review_filter_type,
        evaluated_review_filter_group,
        evaluated_review_available_groups,
        evaluated_review_submitted_order,
        evaluated_review_period,
        extras,
    ) = _collect_evaluated_review_items(request)
    evaluated_review_page_obj = Paginator(evaluated_review_items, 15).get_page(request.GET.get("er_page", 1))
    # Test balı yalnız görünən 15 sətir üçün (əvvəl bütün tarixçə üçün hesablanırdı).
    fill_evaluated_test_scores(evaluated_review_page_obj.object_list)
    # «Yoxlayan» — insan yoxdursa «Avtomatik (sistem)» (2026-10-27); yenə yalnız görünən sətirlər.
    fill_evaluated_checkers(evaluated_review_page_obj.object_list)
    # Apellyasiya statusu — bütün süzülmüş imtahan cəhdləri üçün TƏK sorğu (KPI + sətir nişanı).
    appeal_map = appeal_status_by_attempt(item.get("attempt_id") for item in evaluated_review_items)
    decorate_rows(evaluated_review_page_obj.object_list, appeal_map)
    # Tətbiq olunmuş süzgəclər — səhifələmə linki VƏ Excel ixracı eyni dəstdən (ixrac = ekrandakı siyahı).
    applied = {
        "evaluated_search": evaluated_review_search_query,
        "evaluated_type": evaluated_review_filter_type if evaluated_review_filter_type != "all" else "",
        "evaluated_group": evaluated_review_filter_group,
        "evaluated_subject": extras["subject"],
        "evaluated_period": evaluated_review_period,
        "evaluated_from": extras["date_from"],
        "evaluated_to": extras["date_to"],
        "evaluated_submitted_order": (
            evaluated_review_submitted_order if evaluated_review_submitted_order != "newest" else ""
        ),
    }
    applied = {key: value for key, value in applied.items() if value}
    er_extra = ["section=review-results"] + [f"{key}={quote(value)}" for key, value in applied.items()]
    export_url = reverse("accounts:review_results_export")
    if applied:
        export_url = f"{export_url}?{urlencode(applied)}"
    is_filtered = bool(set(applied) - {"evaluated_submitted_order"})
    return {
        "evaluated_review_items": evaluated_review_items,
        "evaluated_review_search_query": evaluated_review_search_query,
        "evaluated_review_filter_type": evaluated_review_filter_type,
        "evaluated_review_filter_group": evaluated_review_filter_group,
        "evaluated_review_available_groups": evaluated_review_available_groups,
        "evaluated_review_submitted_order": evaluated_review_submitted_order,
        "evaluated_review_period": evaluated_review_period,
        "evaluated_review_page_obj": evaluated_review_page_obj,
        "evaluated_review_pagination_query": "&".join(er_extra),
        "evaluated_review_kpi_tiles": build_kpi_tiles(evaluated_review_items, appeal_map),
        "evaluated_review_filter_fields": build_filter_fields(
            search=evaluated_review_search_query,
            filter_type=evaluated_review_filter_type,
            group=evaluated_review_filter_group,
            groups=evaluated_review_available_groups,
            period=evaluated_review_period,
            order=evaluated_review_submitted_order,
            subject=extras["subject"],
            subjects=extras["subjects"],
            date_from=extras["date_from"],
            date_to=extras["date_to"],
        ),
        "evaluated_review_export_url": export_url,
        "evaluated_review_count_label": pgettext("accounts.review_results", "Nəticə: %(n)s")
        % {"n": len(evaluated_review_items)},
        "evaluated_review_empty": empty_state(filtered=is_filtered),
    }
