"""Profil "pending-review" və "review-results" bölmələri üçün context-fragment-lər.

Hər funksiya yalnız müvafiq bölmə aktiv olduqda (caller guard-ı) çağırılır və
həmin bölmənin ``context`` açarlarını qaytarır. Davranış köhnə inline bloklarla
eynidir.
"""

from urllib.parse import quote

from django.core.paginator import Paginator
from django.utils.translation import pgettext

from apps.accounts.views._dashboard_helpers import (
    _collect_evaluated_review_items,
    _collect_pending_review_items,
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
    ) = _collect_evaluated_review_items(request)
    evaluated_review_page_obj = Paginator(evaluated_review_items, 15).get_page(request.GET.get("er_page", 1))
    # Test balı yalnız görünən 15 sətir üçün (əvvəl bütün tarixçə üçün hesablanırdı).
    fill_evaluated_test_scores(evaluated_review_page_obj.object_list)
    # Apellyasiya statusu — bütün süzülmüş imtahan cəhdləri üçün TƏK sorğu (KPI + sətir nişanı).
    appeal_map = appeal_status_by_attempt(item.get("attempt_id") for item in evaluated_review_items)
    decorate_rows(evaluated_review_page_obj.object_list, appeal_map)
    er_extra = ["section=review-results"]
    if evaluated_review_search_query:
        er_extra.append(f"evaluated_search={quote(evaluated_review_search_query)}")
    if evaluated_review_filter_type != "all":
        er_extra.append(f"evaluated_type={evaluated_review_filter_type}")
    if evaluated_review_filter_group:
        er_extra.append(f"evaluated_group={quote(evaluated_review_filter_group)}")
    if evaluated_review_period:
        er_extra.append(f"evaluated_period={evaluated_review_period}")
    if evaluated_review_submitted_order != "newest":
        er_extra.append(f"evaluated_submitted_order={evaluated_review_submitted_order}")
    is_filtered = bool(
        evaluated_review_search_query
        or evaluated_review_filter_type != "all"
        or evaluated_review_filter_group
        or evaluated_review_period
    )
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
        ),
        "evaluated_review_count_label": pgettext("accounts.review_results", "Nəticə: %(n)s")
        % {"n": len(evaluated_review_items)},
        "evaluated_review_empty": empty_state(filtered=is_filtered),
    }
