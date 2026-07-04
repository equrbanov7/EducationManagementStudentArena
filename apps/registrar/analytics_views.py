"""Dekan/kafedra analitika görünüşü (U10) — /jurnal/analitika/.

RBAC mirrors the grade-approval chain: deans, kafedra müdirləri and org admins
(:func:`approval.can_chair_approve`) may open the dashboard; everyone else gets
a 404 (no existence leak). Context building is shared with the profile cabinet
section (:mod:`apps.registrar.page_contexts`).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.registrar import approval, page_contexts


@login_required
def analytics_dashboard(request):
    """Faculty analytics: pass rate, avg GPA, attendance per program/group."""
    organization = getattr(request, "organization", None)
    if organization is None or not approval.can_chair_approve(request.user, organization):
        raise Http404  # dean/chair/admin only — do not leak the URL

    context = page_contexts.analytics_context(request, organization)
    context["active_main_nav"] = "analytics"
    return render(request, "registrar/analytics.html", context)
