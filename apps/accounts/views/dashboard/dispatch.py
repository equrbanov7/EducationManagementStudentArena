"""
Dashboard / cabinet role dispatcher.

Single-login → unified role-aware cabinet routing (e-university best practice,
à la UNEC kabinet): one login screen, one canonical cabinet entry
(``/kabinet/``) that forwards every user to the same profile cabinet shell. The
profile page renders role-specific sections for students, teaching staff and
management roles, so users do not see two competing cabinet designs.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse

UNIFIED_CABINET_URL_NAME = "accounts:profile"


def resolve_cabinet_url(user, capabilities=None):
    """Return the cabinet URL that matches *user*'s role.

    All roles share the single unified cabinet (profile). ``user`` and
    ``capabilities`` are accepted for backward-compatible call sites.
    """
    return reverse(UNIFIED_CABINET_URL_NAME)


@login_required
def cabinet_entry(request):
    """Canonical single cabinet entry (``/kabinet/``) — routes by role.

    Bookmarkable, role-agnostic URL used by the top-nav "Kabinet" link and as
    the post-login landing: everyone lands on the unified profile cabinet.
    """
    return redirect(resolve_cabinet_url(request.user))


@login_required
def student_cabinet_entry(request):
    """Explicit student-cabinet URL.

    Students use this bookmarkable URL; after authentication it lands on the
    unified role-aware profile cabinet where student sections live.
    """
    return redirect("accounts:profile")


@login_required
def staff_cabinet_entry(request):
    """Explicit teaching-staff / management cabinet URL."""
    return redirect(resolve_cabinet_url(request.user))


@login_required
def dashboard(request):
    """Legacy dashboard dispatcher (kept for existing links)."""
    return redirect(resolve_cabinet_url(request.user))
