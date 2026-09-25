"""Kabinet bölmələrinin kontekst qurucuları — ``survey_cabinet`` template tag-ları çağırır.

Niyə template tag? Kabinet konteksti ``accounts`` app-ının stage qurucularındadır;
``surveys`` isə ``accounts``-u import edə bilməz (``accounts → surveys`` kənarı
var — dövr yaranardı). Bölmə partial-ı ``{% load survey_cabinet %}`` ilə paneli
burada qurur: YALNIZ bölmə render olunanda işləyir (digər bölmələrə sorğu yoxdur)
və icazəni FAIL-CLOSED yenidən yoxlayır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from ..constants import MIN_GROUP_SIZE_CEIL, MIN_GROUP_SIZE_FLOOR, CampaignStatus
from .access import can_manage_campaigns, results_scope
from .config import survey_config
from .gate_snapshot import active_entries, snapshot_is_stale, sync_gate_snapshot

#: İştirak faizi hesablanan son kampaniya sayı (hər biri ~6 aqreqat sorğu).
RATE_CAMPAIGNS = 6


def _request_org(context):
    request = context.get("request")
    return request, getattr(request, "organization", None)


def student_panel(context) -> dict:
    """Tələbənin «Anonim sorğu» bölməsi — middleware vəziyyətindən, SIFIR sorğu."""
    request, organization = _request_org(context)
    user = getattr(request, "user", None)
    state = getattr(user, "_survey_gate_state", None)
    entries = active_entries(organization, timezone.localdate()) if organization is not None else []
    closes = [entry["closes_on"] for entry in entries if entry["closes_on"]]
    return {
        "available": state is not None and state.total > 0,
        "pending": state.pending if state is not None else 0,
        "total": state.total if state is not None else 0,
        "done": (state.total - state.pending) if state is not None else 0,
        "closes_on": min(closes) if closes else None,
        "survey_url": reverse("surveys:home"),
    }


def campaigns_panel(context) -> dict:
    """«Sorğu kampaniyaları» — dövrlər üzrə kampaniyalar, iştirak, idarə formaları."""
    from ..public import campaigns_for
    from .filters import ResultFilters
    from .participation import participation

    request, organization = _request_org(context)
    user = getattr(request, "user", None)
    if organization is None or not can_manage_campaigns(user, organization, request=request):
        return {"has_access": False}
    if not getattr(request, "is_view_as", False) and snapshot_is_stale(organization):
        sync_gate_snapshot(organization)  # self-healing (bax gate_snapshot sənədi); view-as-da yazı yoxdur
    scope = results_scope(user, organization, request=request)
    rows = campaigns_for(organization)
    for index, row in enumerate(rows):
        row["participation"] = (
            participation(organization, scope, ResultFilters(), [row["id"]]) if index < RATE_CAMPAIGNS else None
        )
        row["is_closed"] = row["status"] == CampaignStatus.CLOSED
        row["is_draft"] = row["status"] == CampaignStatus.DRAFT
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    used = {row["period_id"] for row in rows}
    periods = [
        {"id": period.pk, "label": f"{period.name} · {period.academic_year}"}
        for period in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")[:12]
        if period.pk not in used
    ]
    config = survey_config(organization)
    return {
        "has_access": True,
        "rows": rows,
        "periods": periods,
        "config": config,
        "today": timezone.localdate(),
        "post_url": reverse("surveys:manage"),
        "next_url": reverse("accounts:profile") + "?section=evaluation-campaigns",
        "k_floor": MIN_GROUP_SIZE_FLOOR,
        "k_ceil": MIN_GROUP_SIZE_CEIL,
    }


def results_panel(context) -> dict:
    """«Sorğu nəticələri» — tam analitika paneli (filtrlər, KPI, qrafiklər, müəllim
    reytinqi, ümumi təkliflər); konteksti ``views.results_panel`` qurur (F2).

    Gecikmiş import: görünüş qatı ``public`` fasadından istifadə edir, bu modul isə
    fasadın özünə daxildir — modul yüklənəndə dövr yaranmasın.
    """
    from ..views.results_panel import panel_context

    return panel_context(context)
