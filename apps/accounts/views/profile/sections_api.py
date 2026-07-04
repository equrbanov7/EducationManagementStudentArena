"""
Profile section API (P3.1 + P3.2) — progressive enhancement endpoints.

Two endpoints:

* ``profile_section_fragment`` — returns HTML for the active section partial
  so the frontend can swap only the main content area without a full page
  reload. Reuses ``user_profile`` for context-building so permission, tenant,
  RLS and section-gating behaviour stays identical to ``/accounts/profile/``.

* ``profile_badges_api`` — returns sidebar badge counts as JSON via the
  cheap counters from ``_dashboard_helpers.cheap_counts``.

Server-side ``/accounts/profile/?section=...`` continues to work untouched;
the AJAX endpoints are pure progressive enhancement.

Security guarantees:
- ``@login_required`` on every endpoint
- only sections in ``AJAX_SAFE_SECTIONS`` are exposed via AJAX (forms/admin
  sections remain full-page only)
- access check uses the same ``_role_capabilities(...).allowed_sections``
  contract as ``user_profile``
- CSRF for these GET endpoints is irrelevant (read-only); POST forms inside
  rendered partials continue to use Django's CSRF middleware as before
- tenant/RLS scoping comes "for free" because we delegate to ``user_profile``
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse

# from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.models import UserProfile
from apps.notifications.public import build_profile_notification_state, get_unread_count
from core.cache import get_or_set_cached_profile_badge_counts

from .._dashboard_helpers.cheap_counts import compute_profile_badge_counts
from .._helpers import _get_active_organization, _role_capabilities

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Section mapping
# --------------------------------------------------------------------------- #

# Bütün mövcud profile section-ları → partial template adı.
SECTION_PARTIALS: dict[str, str] = {
    "profile-info": "accounts/profile/sections/_profile_info.html",
    "notifications": "accounts/profile/sections/_notifications.html",
    "publish-notification": "accounts/profile/sections/_publish_notification.html",
    "create-post": "accounts/profile/sections/_create_post.html",
    "posts": "accounts/profile/sections/_posts.html",
    "my-exams": "accounts/profile/sections/_my_exams.html",
    "my-courses": "accounts/profile/sections/_my_courses.html",
    "courses": "accounts/profile/sections/_courses.html",
    "assigned-exams": "accounts/profile/sections/_assigned_exams.html",
    "assigned-courses": "accounts/profile/sections/_assigned_courses.html",
    "my-results": "accounts/profile/sections/_my_results.html",
    "my-subjects": "accounts/profile/sections/_my_subjects.html",
    "pending-answers": "accounts/profile/sections/_pending_answers.html",
    "groups": "accounts/profile/sections/_groups.html",
    "pending-post-approvals": "accounts/profile/sections/_pending_post_approvals.html",
    "pending-review": "accounts/profile/sections/_pending_review.html",
    "review-results": "accounts/profile/sections/_review_results.html",
    "role-assignment": "accounts/profile/sections/_role_assignment.html",
    "student-organization-request": "accounts/profile/sections/_student_org_request.html",
    "student-organization-management": "accounts/profile/sections/_student_org_management.html",
    "permission-editor": "accounts/profile/sections/_permission_editor.html",
    "manage-roles": "accounts/profile/sections/_manage_roles.html",
    "category-management": "accounts/profile/sections/_category_management.html",
    "create-category": "accounts/profile/sections/_create_category.html",
    "superadmin-org-features": "accounts/profile/sections/superadmin/_superadmin_org_features.html",
    "superadmin-organizations": "accounts/profile/sections/superadmin/_superadmin_organizations.html",
    "superadmin-users": "accounts/profile/sections/superadmin/_superadmin_user_management.html",
    "superadmin-ai": "accounts/profile/sections/superadmin/_superadmin_ai_settings.html",
    "superadmin-contact-messages": "accounts/profile/sections/superadmin/_superadmin_contact_messages.html",
    "statistics": "accounts/profile/sections/_statistics.html",
    "edit-profile": "accounts/profile/sections/_edit_profile.html",
    "change-password": "accounts/profile/sections/_change_password.html",
    "question-bank": "accounts/profile/sections/_question_bank.html",
    "my-appeals": "accounts/profile/sections/_my_appeals.html",
    "manage-appeals": "accounts/profile/sections/_manage_appeals.html",
    "org-structure": "accounts/profile/sections/_org_structure.html",
    "org-faculties": "accounts/profile/sections/_org_faculties.html",
    "org-kafedras": "accounts/profile/sections/_org_kafedras.html",
    "org-members": "accounts/profile/sections/_org_members.html",
    "org-roles": "accounts/profile/sections/_org_roles.html",
    "audit-log": "accounts/profile/sections/_audit_log.html",
}

# AJAX-safe sections (P3.4) — read-mostly bölmələr. Form-heavy admin
# bölmələri normal full-page naviqasiyada qalır.
AJAX_SAFE_SECTIONS: frozenset[str] = frozenset(
    {
        "profile-info",
        "notifications",
        "posts",
        "my-exams",
        "my-courses",
        "courses",
        "assigned-exams",
        "assigned-courses",
        "my-results",
        "my-subjects",
        "pending-answers",
        "groups",
        "pending-review",
        "review-results",
        "statistics",
        "pending-post-approvals",
        "question-bank",
        "my-appeals",
        "manage-appeals",
        "org-structure",
        "org-faculties",
        "org-kafedras",
        "org-members",
        "org-roles",
        "audit-log",
    }
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ensure_section_allowed(request: HttpRequest, section: str):
    """
    Return ``(profile, capabilities)`` if user may access ``section`` via AJAX,
    otherwise return ``None``.

    Permission contract is identical to ``user_profile``:
    - section must be in ``SECTION_PARTIALS``
    - section must be in ``AJAX_SAFE_SECTIONS`` (form/admin sections excluded)
    - section must be in the user's ``allowed_sections``
    """
    if section not in SECTION_PARTIALS:
        return None
    if section not in AJAX_SAFE_SECTIONS:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    if section not in capabilities["allowed_sections"]:
        return None
    return profile, capabilities


# --------------------------------------------------------------------------- #
# P3.1 — Section HTML fragment endpoint
# --------------------------------------------------------------------------- #


@never_cache
@login_required
@require_GET
def profile_section_fragment(request: HttpRequest, section: str) -> HttpResponse:
    """
    Render and return only the active section's HTML partial.

    Reuses ``user_profile``'s full context builder so all permission, tenant,
    RLS, search, filter and pagination behaviour is identical to
    ``/accounts/profile/?section=<name>``.

    P3-extra — `@never_cache` qoyulub. Bu response istifadəçi/sessiya/təşkilat-a
    bağlı olduğu üçün brauzer və ya proxy onu kəş etməməlidir.
    """
    access = _ensure_section_allowed(request, section)
    if access is None:
        return JsonResponse(
            {"ok": False, "error": "forbidden_or_unknown_section"},
            status=403,
        )

    # Delegate context-building to user_profile via the existing
    # `_render_profile_section` helper. We set `direct_profile_section` so the
    # full-page template renders only the active section in case the caller
    # falls back to the full-page response (defensive).
    request.direct_profile_section = section
    mutable_get = request.GET.copy()
    mutable_get["section"] = section
    request.GET = mutable_get

    # KRİTİK: fragment KANONİK profil URL-i kimi render olunmalıdır.
    # Şablonlarda çoxlu form `next`/canonical üçün `request.get_full_path`-i
    # istifadə edir. Bu endpoint (`/accounts/profile/api/sections/...`) ilə
    # render olunanda həmin `next` API URL-inə işarələyir; full form submit
    # (moderate/delete/dil dəyişmə) `url_has_allowed_host_and_scheme`-dən keçib
    # istifadəçini xam JSON səhifəsinə aparır. `request.path`-i kanonik profil
    # URL-inə çeviririk ki, `get_full_path()` `/accounts/profile/?section=...`
    # qaytarsın. `resolver_match` (nav-active) dəyişmir, çünki o ayrıca atributdur.
    from django.urls import reverse

    _canonical_profile_path = reverse("accounts:profile")
    request.path = _canonical_profile_path
    request.path_info = _canonical_profile_path
    request.META["QUERY_STRING"] = mutable_get.urlencode()

    # Import lazily to avoid circular import (sections_api -> main -> sections_api).
    from .main import user_profile

    # We want user_profile to run its context builder, then we render only
    # the partial. Easiest way: monkey-render. user_profile returns a
    # TemplateResponse-like HttpResponse from `render(...)` (already rendered).
    # We instead intercept by capturing the context — but `render(...)` does
    # not expose the context. So we re-implement just the part we need:
    #
    # Call user_profile and let it produce the full HttpResponse, then
    # we re-render the partial with the request context that includes the
    # same template variables. Simplest robust approach: re-execute the
    # context builder via the same code path by calling user_profile and
    # discarding its rendered HTML, while reusing the request state it
    # mutates. However that costs the full render time.
    #
    # The cleanest, lowest-risk approach for P3.1: render the partial through
    # `render_to_string` after running user_profile's context builder by
    # invoking it once with a sentinel. To keep the change minimal we add a
    # public hook in `main`: `build_profile_context(request)` (see comment in
    # main.py). For backward safety, until that hook exists we fall back to
    # calling user_profile and returning its full HTML — the JS will swap
    # only the relevant DOM node.
    response = user_profile(request)

    # If user_profile produced an HttpResponseRedirect (POST-redirect-get flow
    # is impossible here because we require GET, but defensive).
    if getattr(response, "status_code", 200) >= 300 and getattr(response, "status_code", 200) < 400:
        return JsonResponse(
            {"ok": False, "error": "redirect_required", "location": response.get("Location", "")},
            status=409,
        )

    # The full-page response already contains only the active section partial
    # because P1's profile.html switch statement renders just one panel.
    # The frontend's job is to extract `[data-profile-section-panel="<section>"]`
    # from the response body. For a cleaner API we wrap it in JSON.
    try:
        html_bytes = response.content
        html = html_bytes.decode(response.charset or "utf-8")
    except Exception:  # noqa: BLE001 — defensive
        html = ""

    return JsonResponse(
        {
            "ok": True,
            "section": section,
            "html": html,
            # Frontend hint: which DOM selector to extract from `html`.
            "extract_selector": '[data-profile-section-panel="{}"]'.format(section),
        }
    )


# --------------------------------------------------------------------------- #
# P3.2 — Sidebar badge endpoint
# --------------------------------------------------------------------------- #


@never_cache
@login_required
@require_GET
def profile_badges_api(request: HttpRequest) -> JsonResponse:
    """
    Lightweight JSON endpoint returning sidebar badge counts the user is
    allowed to see. The student/reviewer counts come from the SAME cached bundle
    (``get_or_set_cached_profile_badge_counts`` → ``compute_profile_badge_counts``)
    that ``user_profile`` uses, so page, section fragments and this API stay
    consistent and the heavy COUNT/aggregate queries run at most once per
    (user, org) per TTL window.

    P3-extra — `@never_cache` (HTTP) qalır; badge dəyərləri Redis-də ~45s
    eventual-consistent saxlanılır (öz datası, kiçik staleness məqbul).
    """
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)

    payload: dict[str, int] = {}

    # In-app + org notifications (cheap counts).
    notification_state = build_profile_notification_state(user=request.user, profile=profile)
    in_app_unread = get_unread_count(user=request.user)
    payload["notifications_unread_count"] = notification_state.get("unread_count", 0) + in_app_unread

    # P3 — Student + reviewer badge sayğacları user_profile ilə EYNİ cached
    # dəstdən gəlir (köhnə inline ~90-sətirlik dublikat aqreqasiya silindi: DRY +
    # drift riski aradan qalxdı). Eyni (user, aktiv org) açarı paylaşıldığına görə
    # tam profil səhifəsi, section fragment-ləri və bu API həmişə eyni rəqəmləri
    # qaytarır (uyğunsuz "flicker" olmur). Qeyd: badge-lər ~45s eventual-consistent
    # olur; ani yenilənmə lazım olduqda submit/qiymətləndirmə kodu
    # core.cache.invalidate_profile_badge_counts_cache çağırmalıdır.
    active_org = _get_active_organization(request)

    def _compute_shared_badges() -> dict[str, int]:
        from apps.courses.models import Course
        from apps.exams.models import Exam

        from .._helpers import _tenant_scoped_courses, _tenant_scoped_exams

        return compute_profile_badge_counts(
            request,
            request.user,
            capabilities=capabilities,
            my_exams_qs=_tenant_scoped_exams(request, Exam.objects.filter(author=request.user)),
            teacher_courses=_tenant_scoped_courses(request, Course.objects.filter(owner=request.user)),
        )

    shared_badges = get_or_set_cached_profile_badge_counts(
        user_id=request.user.pk,
        org_id=active_org.pk if active_org is not None else None,
        compute=_compute_shared_badges,
    )
    if capabilities.get("can_view_student_assignments"):
        payload["assigned_tasks_count"] = shared_badges.get("assigned_tasks", 0)
        payload["my_results_count"] = shared_badges.get("my_results", 0)
        payload["pending_answers_count"] = shared_badges.get("pending_answers", 0)
    if capabilities.get("can_review_submissions"):
        payload["pending_review_count"] = shared_badges.get("pending_review", 0)
        payload["evaluated_review_count"] = shared_badges.get("evaluated_review", 0)

    # Post-approval badge (teachers/admins with that allowed section)
    if "pending-post-approvals" in capabilities.get("allowed_sections", set()):
        from apps.accounts import profile_hooks

        payload["pending_post_approval_count"] = profile_hooks.pending_posts_count(request.user)

    # Superadmin badges
    if capabilities.get("is_superadmin"):
        from apps.organizations.models import Organization

        payload["superadmin_pending_org_count"] = Organization.objects.filter(status="pending").count()
        if "superadmin-contact-messages" in capabilities.get("allowed_sections", set()):
            from apps.contact.models import ContactMessage
            from apps.trial_exams.models import TrialExamRequest

            payload["contact_unhandled_count"] = min(
                ContactMessage.objects.filter(is_handled=False).count()
                + TrialExamRequest.objects.filter(is_handled=False).count(),
                99,
            )

    return JsonResponse({"ok": True, "badges": payload})


__all__ = [
    "SECTION_PARTIALS",
    "AJAX_SAFE_SECTIONS",
    "profile_section_fragment",
    "profile_badges_api",
]
