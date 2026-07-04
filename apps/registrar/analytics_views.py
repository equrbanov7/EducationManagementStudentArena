"""Dekan/kafedra analitika görünüşü (U10) — /jurnal/analitika/.

RBAC mirrors the grade-approval chain: deans, kafedra müdirləri and org admins
(:func:`approval.can_chair_approve`) may open the dashboard; everyone else gets
a 404 (no existence leak). Data building is delegated to
:mod:`apps.registrar.analytics` (read-only, fixed query count).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.registrar import analytics, approval


def _periods_for(organization):
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"))


def _pick_period(periods, requested_id):
    if requested_id:
        for period in periods:
            if str(period.id) == requested_id:
                return period
    for period in periods:
        if period.is_current:
            return period
    return periods[0] if periods else None


@login_required
def analytics_dashboard(request):
    """Faculty analytics: pass rate, avg GPA, attendance per program/group."""
    organization = getattr(request, "organization", None)
    if organization is None or not approval.can_chair_approve(request.user, organization):
        raise Http404  # dean/chair/admin only — do not leak the URL

    periods = _periods_for(organization)
    period = _pick_period(periods, (request.GET.get("period") or "").strip())
    data = (
        analytics.build_period_analytics(organization=organization, period=period)
        if period is not None
        else {"has_data": False, "period": None, "totals": None, "programs": [], "groups": [], "at_risk": []}
    )
    return render(
        request,
        "registrar/analytics.html",
        {
            "periods": periods,
            "analytics": data,
            "active_main_nav": "analytics",
        },
    )
