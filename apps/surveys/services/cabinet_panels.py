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
from django.utils.translation import pgettext

from .. import registrar_bridge as bridge
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
    from .analytics_guard import count_bucket, round5
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
        part = participation(organization, scope, ResultFilters(), [row["id"]]) if index < RATE_CAMPAIGNS else None
        # Audit 2026-09-28 SV-4: dəqiq say/faiz yoxdur — nəticə panelindəki kimi səbət və 5%-lik faiz.
        row["participation"] = (
            {"expected": count_bucket(part.get("expected")), "rate": round5(part.get("rate"))} if part else None
        )
        row["responses_label"] = count_bucket(row["responses"] + row.get("pending", 0))
        row["receipts_label"] = count_bucket(row["receipts"])
        row["is_closed"] = row["status"] == CampaignStatus.CLOSED
        row["is_draft"] = row["status"] == CampaignStatus.DRAFT
    _attach_question_sets(organization, rows)
    today = timezone.localdate()
    _attach_journal_counts(organization, rows)
    config = survey_config(organization)
    return {
        "has_access": True,
        "rows": rows,
        "periods": _period_choices(organization, {row["period_id"] for row in rows}, today),
        "config": config,
        "today": today,
        "post_url": reverse("surveys:manage"),
        "next_url": reverse("accounts:profile") + "?section=evaluation-campaigns",
        "k_floor": MIN_GROUP_SIZE_FLOOR,
        "k_ceil": MIN_GROUP_SIZE_CEIL,
        "builder_url": reverse("accounts:profile") + "?section=surveys-builder&status=all",
    }


def _attach_journal_counts(organization, rows) -> None:
    """Sahib 2026-10-04: kartda «bağlı jurnal N / M» və açıq-amma-hədəfsiz xəbərdarlığı (2 sorğu).

    Hədəflər YALNIZ bağlı jurnallardan yaranır — bağlı jurnalı olmayan dövrün kampaniyası «Açıq»
    görünsə də heç bir tələbəyə çıxmır; RİM bunu kartın özündə görməlidir.
    """
    counts = bridge.closed_offering_counts(organization, [row["period_id"] for row in rows])
    for row in rows:
        item = counts.get(row["period_id"]) or {"closed": 0, "total": 0}
        row["journals_closed"], row["journals_total"] = item["closed"], item["total"]
        row["no_targets"] = row["effective_status"] == CampaignStatus.OPEN and not item["closed"]


def _period_choices(organization, used, today) -> list:
    """Yeni kampaniya seçimi: keçmiş/cari dövrlər ƏVVƏL (ən yenisi seçili), gələcək dövrlər SONDA.

    Sahib 2026-10-04: siyahı ``-start_date`` ilə gəlirdi — ilk sətir gələcək «Yaz 2026/2027» idi və
    «Kampaniyanı aç» seçim dəyişdirilmədən basılanda hədəfsiz kampaniya açılırdı. Hər seçimdə
    «bağlı jurnal N / M» yazılır ki, boş dövr bir baxışda bilinsin.
    """
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    candidates = [
        period
        for period in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")[:12]
        if period.pk not in used
    ]
    candidates.sort(key=lambda period: (period.start_date > today, -period.start_date.toordinal()))
    counts = bridge.closed_offering_counts(organization, [period.pk for period in candidates])
    suffix = pgettext("surveys.cabinet", "bağlı jurnal %(closed)s / %(total)s")
    return [
        {
            "id": period.pk,
            "label": f"{period.name} · {period.academic_year} — "
            + suffix % (counts.get(period.pk) or {"closed": 0, "total": 0}),
            "selected": index == 0,
        }
        for index, period in enumerate(candidates)
    ]


def _attach_question_sets(organization, rows) -> None:
    """Sorğu qurucusu (2026-09-30): hər kampaniyanın sual dəsti (ad + qurucuda redaktə linki), 2 sorğu."""
    from ..models import Survey, SurveyCampaign

    templates = dict(
        SurveyCampaign.objects.filter(organization=organization, pk__in=[row["id"] for row in rows]).values_list(
            "pk", "template_id"
        )
    )
    wrappers = {
        template_id: (pk, title)
        for pk, template_id, title in Survey.objects.filter(template_id__in=set(templates.values())).values_list(
            "pk", "template_id", "title"
        )
    }
    base = reverse("accounts:profile") + "?section=surveys-builder&tab=questions&survey="
    for row in rows:
        wrapper = wrappers.get(templates.get(row["id"]))
        row["question_set"] = {"title": wrapper[1], "url": f"{base}{wrapper[0]}"} if wrapper else None


def results_panel(context) -> dict:
    """«Sorğu nəticələri» — tam analitika paneli (filtrlər, KPI, qrafiklər, müəllim
    reytinqi, ümumi təkliflər); konteksti ``views.results_panel`` qurur (F2).

    Gecikmiş import: görünüş qatı ``public`` fasadından istifadə edir, bu modul isə
    fasadın özünə daxildir — modul yüklənəndə dövr yaranmasın.
    """
    from ..views.results_panel import panel_context

    return panel_context(context)
