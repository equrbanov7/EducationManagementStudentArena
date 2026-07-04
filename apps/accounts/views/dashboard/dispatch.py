"""
Dashboard / cabinet role dispatcher.

Single-login → role-aware cabinet routing (e-university best practice, à la
UNEC kabinet): one login screen, one canonical cabinet entry (``/kabinet/``)
that forwards each user to the surface that fits their role — teaching staff to
the teacher cabinet, everyone else (students + management roles) to the unified
role-aware profile cabinet, which renders role-specific sections.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse

from .._helpers import _role_capabilities

# Teaching-staff roles land on the teacher cabinet; every other role shares the
# unified profile cabinet. ``is_teacher`` already covers teacher +
# assistant/lab-assistant (via role aliases), so it is the single predicate.
TEACHER_CABINET_URL_NAME = "accounts:teacher_dashboard"
UNIFIED_CABINET_URL_NAME = "accounts:profile"


def resolve_cabinet_url(user, capabilities=None):
    """Return the cabinet URL that matches *user*'s role.

    Teaching staff → teacher cabinet; students and all other roles → the single
    unified cabinet (profile). Pass pre-computed *capabilities* to avoid a
    second RBAC resolution when the caller already has them.
    """
    if capabilities is None:
        capabilities = _role_capabilities(user, getattr(user, "profile", None))
    if capabilities.get("is_teacher"):
        return reverse(TEACHER_CABINET_URL_NAME)
    return reverse(UNIFIED_CABINET_URL_NAME)


@login_required
def cabinet_entry(request):
    """Canonical single cabinet entry (``/kabinet/``) — routes by role.

    Bookmarkable, role-agnostic URL used by the top-nav "Kabinet" link and as
    the post-login landing: teaching staff are forwarded to the teacher cabinet,
    everyone else to the unified profile cabinet.
    """
    return redirect(resolve_cabinet_url(request.user))


@login_required
def dashboard(request):
    """Legacy dashboard dispatcher (kept for existing links).

    Mirrors the cabinet router but targets the older standalone dashboards.
    """
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if capabilities["can_review_submissions"]:
        return redirect("accounts:teacher_dashboard")
    return redirect("accounts:student_dashboard")
