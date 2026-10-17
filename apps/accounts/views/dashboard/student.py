"""
Student-facing dashboard and assigned-items / results views.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import pgettext_lazy

from core.search_text import tolerant_q
from core.tenancy import restore_request_organization_from_profile

from .._dashboard_helpers import _collect_my_results, academic_filter_options, fill_my_results_scores
from .._helpers import (
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _query_string,
    _render_profile_section,
    _role_capabilities,
)

User = get_user_model()


@login_required
def student_dashboard(request):
    """Köhnə tələbə paneli URL-i — kanonik kabinet ``accounts:profile``-dir.

    URL auditi A6 (2026-10-10): köhnə ``student_dashboard.html`` səhifəsi silindi;
    ``teacher_dashboard`` kimi yalnız yönləndirmədir (login «next» auditoriya
    xəritəsi URL adını işlətməyə davam edir).
    """
    return redirect("accounts:profile")


@login_required
def assigned_exams(request):
    """Assigned exams list for the current user."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    exams = _assigned_exams_queryset(request, request.user, active_only=True).order_by("-start_datetime", "-created_at")

    search = request.GET.get("search", "")
    search_q = tolerant_q(search, ("title", "description"))
    if search_q is not None:
        exams = exams.filter(search_q)

    exam_items = []
    for exam in exams:
        can_start_without_code, _ = exam.can_user_start(request.user, code=None)
        exam_items.append(
            {
                "exam": exam,
                "requires_code": bool(exam.access_code and not can_start_without_code),
            }
        )

    context = {
        "exam_items": exam_items,
        "search_query": search,
    }
    return render(request, "accounts/assigned_exams.html", context)


@login_required
def assigned_courses(request):
    """Assigned courses list for the current user."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    courses = _assigned_courses_queryset(request, request.user).order_by("-created_at")

    search = request.GET.get("search", "")
    search_q = tolerant_q(search, ("title", "description"))
    if search_q is not None:
        courses = courses.filter(search_q)

    context = {
        "courses": courses,
        "search_query": search,
    }
    return render(request, "accounts/assigned_courses.html", context)


@login_required
def my_results(request):
    """Unified submission/result list for students and member-level users."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    from django.core.paginator import Paginator

    search_query = (request.GET.get("q") or "").strip()
    # İl/semestr süzgəci — yalnız akademik (jurnal) fənn nəticələrinə aiddir.
    year = (request.GET.get("year") or "").strip()
    season = (request.GET.get("season") or "").strip()
    items, counts, active_filter = _collect_my_results(
        request, filter_type=request.GET.get("type"), search=search_query, year=year, season=season
    )
    # Süzgəc açılışları yalnız onları GÖSTƏRƏN tablarda oxunur — başqa tabda ağır
    # akademik qurucunu boş yerə işə salmasın.
    year_options, season_options = (
        academic_filter_options(request) if active_filter in {"all", "academic"} else ([], [])
    )

    paginator = Paginator(items, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    fill_my_results_scores(page_obj.object_list)

    context = {
        "items": page_obj,
        "page_obj": page_obj,
        "counts": counts,
        "active_filter": active_filter,
        "search_query": search_query,
        "selected_year": year,
        "selected_season": season,
        "year_options": year_options,
        "season_options": season_options,
        "pagination_query": _query_string(type=active_filter, q=search_query, year=year, season=season),
    }
    return render(request, "accounts/my_results.html", context)


@login_required
def pending_answers(request):
    """Pending (not yet finalized) answer list for students."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    return _render_profile_section(request, "pending-answers")
