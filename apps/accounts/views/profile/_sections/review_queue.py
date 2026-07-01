"""Profil "pending-review" və "review-results" bölmələri üçün context-fragment-lər.

Hər funksiya yalnız müvafiq bölmə aktiv olduqda (caller guard-ı) çağırılır və
həmin bölmənin ``context`` açarlarını qaytarır. Davranış köhnə inline bloklarla
eynidir.
"""

from django.core.paginator import Paginator

from apps.accounts.views._dashboard_helpers import _collect_evaluated_review_items, _collect_pending_review_items


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
    (
        evaluated_review_items,
        evaluated_review_search_query,
        evaluated_review_filter_type,
        evaluated_review_filter_group,
        evaluated_review_available_groups,
        evaluated_review_submitted_order,
    ) = _collect_evaluated_review_items(request)
    evaluated_review_page_obj = Paginator(evaluated_review_items, 15).get_page(request.GET.get("er_page", 1))
    er_extra = ["section=review-results"]
    if evaluated_review_search_query:
        er_extra.append(f"evaluated_search={evaluated_review_search_query}")
    if evaluated_review_filter_type != "all":
        er_extra.append(f"evaluated_type={evaluated_review_filter_type}")
    if evaluated_review_filter_group:
        er_extra.append(f"evaluated_group={evaluated_review_filter_group}")
    if evaluated_review_submitted_order != "newest":
        er_extra.append(f"evaluated_submitted_order={evaluated_review_submitted_order}")
    return {
        "evaluated_review_items": evaluated_review_items,
        "evaluated_review_search_query": evaluated_review_search_query,
        "evaluated_review_filter_type": evaluated_review_filter_type,
        "evaluated_review_filter_group": evaluated_review_filter_group,
        "evaluated_review_available_groups": evaluated_review_available_groups,
        "evaluated_review_submitted_order": evaluated_review_submitted_order,
        "evaluated_review_page_obj": evaluated_review_page_obj,
        "evaluated_review_pagination_query": "&".join(er_extra),
    }
