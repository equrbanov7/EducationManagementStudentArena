"""Kataloq analitikasının OXU endpoint-ləri (JSON).

İki endpoint, QƏSDƏN ayrı — `_appeal_stats` naxşı ilə eyni:

* ``people_analytics``    — göstəricilər + qrafik seriyaları; hər filtr
  dəyişikliyində çağırılır (cədvəl endpoint-indən AYRIDIR ki, səhifə keçidi
  aqreqat sorğularını təkrarlamasın).
* ``people_analytics_ai`` — AI xülasəsi; YALNIZ istifadəçi düyməni sıxanda.
  Keş data-hash-ə görədir, ona görə eyni filtr üçün təkrar API çağırışı olmur.

Hər ikisi fail-closed: əhatəsi olmayan istifadəçi ``has_access: false`` və BOŞ
statistika alır (rəqəm sızmır).

JSON MÜQAVİLƏSİ (JS buna söykənir — açar adları dəyişməz)
─────────────────────────────────────────────────────────
``GET analytics_url?<eyni filtrlər>`` →

    has_access, kind, total, can_view_demographics,
    status[]   {key, label, count}
    gender[]   {key, label, count}        — demoqrafiya icazəsi yoxdursa BOŞ
    age        {buckets[{key,label,count}], known, unknown, coverage_percent}
    breakdowns[] {key, title, chart, total, rows[{label, count, percent}]}
    workload[] {key, label, value}        — yalnız müəllim kataloqunda
    filters    {…tətbiq olunmuş normallaşdırılmış filtrlər…}

``GET analytics_ai_url?<eyni filtrlər>`` → ``{ok, summary, cached, limit,
remaining, window}`` və ya ``{ok: false, error}``.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.services import people
from apps.accounts.services.people.analytics import empty_analytics
from apps.accounts.services.people.constants import (
    DEFAULT_PAGE_SIZE,
    STUDENT_SORT_OPTIONS,
    TEACHER_SORT_OPTIONS,
)

logger = logging.getLogger(__name__)

_KINDS = ("teachers", "students")


def _filters_for(request, kind):
    sort_options = TEACHER_SORT_OPTIONS if kind == "teachers" else STUDENT_SORT_OPTIONS
    return people.parse_filters(request.GET, sort_options=sort_options, default_page_size=DEFAULT_PAGE_SIZE)


def _build(request, kind):
    """Aktor + cari filtrlərlə analitika zərfi (heç vaxt exception atmır)."""
    actor = people.resolve_actor(request)
    filters = _filters_for(request, kind)
    if kind == "teachers":
        return filters, people.build_teacher_analytics(actor=actor, filters=filters, request=request)
    return filters, people.build_student_analytics(actor=actor, filters=filters, request=request)


@never_cache
@login_required
@require_GET
def people_analytics(request, kind: str):
    """Filtrlənmiş kataloq üzrə göstəricilər + qrafik seriyaları."""
    if kind not in _KINDS:
        return JsonResponse({**empty_analytics(kind), "error": "unknown_catalog"}, status=404)
    _filters, payload = _build(request, kind)
    return JsonResponse(payload)


@never_cache
@login_required
@require_GET
def people_analytics_ai(request, kind: str):
    """AI xülasəsi — PII-siz aqreqat yük, data-hash keş, istifadəçi-başına limit.

    Xəta halında bölmə səssizcə gizlənməlidir, ona görə cavab HƏMİŞƏ 200-dir və
    uğursuzluq ``{"ok": false, …}`` ilə bildirilir; JS bloku gizlədir.
    """
    if kind not in _KINDS:
        return JsonResponse({"ok": False, "error": "unknown_catalog"}, status=404)

    filters, analytics = _build(request, kind)
    if not analytics.get("has_access"):
        return JsonResponse({"ok": False, "error": "no_access"})

    try:
        result = people.generate_analytics_summary(
            analytics=analytics,
            filters=filters,
            language_code=get_language(),
            user_id=request.user.id,
        )
    except Exception:  # noqa: BLE001 — AI kanalı səhifəni SINDIRMAMALIDIR
        logger.exception("İnsanlar kataloqu AI xülasəsi alınmadı")
        return JsonResponse({"ok": False, "error": "generation_failed"})
    return JsonResponse(result)


__all__ = ["people_analytics", "people_analytics_ai"]
