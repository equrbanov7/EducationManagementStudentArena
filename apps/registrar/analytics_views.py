"""Dekan/kafedra analitika görünüşü (U10) — /jurnal/analitika/.

RBAC: ``analytics.view_all`` / ``analytics.view_unit`` icazəsi olan rollar
(:func:`journal_scope.can_view_analytics`) paneli aça bilər; qalanlar 404 alır
(URL sızmasın). Kontekst profil kabinet bölməsi ilə paylaşılır
(:mod:`apps.registrar.page_contexts`).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.registrar import journal_scope, page_contexts


@login_required
def analytics_dashboard(request):
    """Faculty analytics: pass rate, avg GPA, attendance per program/group."""
    organization = getattr(request, "organization", None)
    if organization is None or not journal_scope.can_view_analytics(request.user, organization):
        raise Http404  # dean/chair/admin only — do not leak the URL

    context = page_contexts.analytics_context(request, organization)
    context["active_main_nav"] = "analytics"
    return render(request, "registrar/analytics.html", context)
