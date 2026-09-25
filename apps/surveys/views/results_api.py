"""«Sorğu nəticələri» — filtr panelinin müəllim seçicisi üçün JSON ucu.

``GET /sorgu/neticeler/muellimler/?q=…&limit=…&offset=…&er_*`` →
``{"results": [{"id", "text"}], "has_more"}`` (``EMSSearchableSelect`` müqaviləsi).
Yalnız istifadəçinin ƏHATƏSİNDƏ, BAĞLI kampaniyalarda cavabı olan müəllimlər (davam edən
kampaniyada boş siyahı — M-1); fakültə/kafedra filtrinə tabedir; axtarış az/ing klaviaturaya
dözümlüdür. Cavab sayı qaytarılmır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .. import public
from .results_filters import resolve


def _int(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@never_cache
@login_required
@require_GET
def teacher_search(request):
    resolved = resolve(request)
    if resolved is None:
        return JsonResponse({"results": [], "has_more": False, "error": "forbidden"}, status=403)
    if resolved.live or not resolved.campaign_ids:
        # M-1: davam edən kampaniyada kimin cavab aldığı da (canlı iştirak) göstərilmir.
        return JsonResponse({"results": [], "has_more": False})
    data = public.teacher_choices(
        resolved.organization,
        resolved.scope,
        resolved.filters,
        resolved.campaign_ids,
        query=str(request.GET.get("q") or "")[:120],
        limit=_int(request.GET.get("limit"), 20),
        offset=_int(request.GET.get("offset"), 0),
    )
    return JsonResponse(
        {"results": [{"id": row["id"], "text": row["text"]} for row in data["results"]], "has_more": data["has_more"]}
    )
