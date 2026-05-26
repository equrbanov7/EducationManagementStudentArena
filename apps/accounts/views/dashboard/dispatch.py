"""
Dashboard role dispatcher.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .._helpers import _role_capabilities


@login_required
def dashboard(request):
    """Redirect users to the dashboard variant that matches their role."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if capabilities["can_review_submissions"]:
        return redirect("accounts:teacher_dashboard")
    return redirect("accounts:student_dashboard")
