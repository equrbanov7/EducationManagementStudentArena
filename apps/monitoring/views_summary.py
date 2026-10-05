"""«Ümumi vəziyyət» xülasəsi və «AI ilə təhlil et» API-ları (sahib 2026-10-01).

* ``GET  summary/``     — bir baxışda server: status banneri, trafik, xidmətlər,
  resurslar, backup, imtahan fəaliyyəti, aktiv istifadəçilər, təhlükəsizlik,
  insidentlər. Superadmin + ``system.monitoring.view`` (RİM rəhbəri).
* ``POST ai-analysis/`` — təmizlənmiş xülasəni Gemini-yə göndərib Azərbaycan
  dilində hesabat alır. İstifadəçi başına ``MONITORING_AI_RATE_LIMIT``
  (defolt 10/saat), hər cəhd audit jurnalına yazılır, view-as altında bağlıdır.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from core.constants import AuditAction
from core.rate_limit import parse_rate, record_rate_limit_hit

from .ai_snapshot import build_ai_snapshot
from .permissions import monitoring_view_required
from .summary import build_summary

logger = logging.getLogger(__name__)

AI_RATE_SCOPE = "monitoring_ai"
_AI = "monitoring.ai"


def _ai_rate() -> str:
    return getattr(settings, "MONITORING_AI_RATE_LIMIT", "10/1h")


def _no_store(payload: dict, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _ai_quota(user_id) -> dict:
    """Qalan AI təhlili sayı (rate-limit keşindən; yazmır)."""
    parsed = parse_rate(_ai_rate())
    if parsed is None:
        return {"limit": 0, "remaining": 0}
    from core.rate_limit import _cache_keys, _rate_limit_cache

    count_key, _expires_key = _cache_keys(AI_RATE_SCOPE, (user_id,))
    used = int(_rate_limit_cache().get(count_key) or 0)
    return {"limit": parsed.limit, "remaining": max(0, parsed.limit - used)}


def _ai_state(user_id) -> dict:
    from apps.ai_assistant.public import monitoring_ai_status

    return {**monitoring_ai_status(), **_ai_quota(user_id)}


@require_GET
@monitoring_view_required
def summary_api(request):
    scope = request.monitoring_scope
    data = dict(build_summary(scope))
    data["scope"] = {"platform": scope.platform, "can_manage": scope.can_manage}
    data["ai"] = _ai_state(request.user.pk)
    return _no_store({"status": "ok", "data": data})


def _audit(request, *, outcome: str, details: dict) -> None:
    try:
        from core.audit import log_action

        log_action(
            # Xülasə sistemdən KƏNARA (Gemini) göndərilir → EXPORT; limitə düşən cəhd → DENY.
            AuditAction.DENY if outcome == "rate_limited" else AuditAction.EXPORT,
            user=request.user,
            organization=getattr(request, "organization", None),
            request=request,
            resource_type="monitoring.ai_analysis",
            resource_repr="Sistem monitorinqi — AI təhlili",
            reason=f"outcome={outcome}",
            new_values=details,
        )
    except Exception:  # pragma: no cover - audit heç vaxt cavabı sındırmasın
        logger.exception("Monitorinq AI audit yazısı alınmadı")


def _error_message(code: str) -> str:
    messages = {
        "disabled": pgettext(_AI, "AI köməkçi hazırda söndürülüb."),
        "not_configured": pgettext(_AI, "AI xidməti hələ qoşulmayıb (açar təyin edilməyib)."),
        "global_limit": pgettext(_AI, "AI xidməti bu gün üçün ümumi limitə çatıb. Sabah yenidən cəhd edin."),
        "rate_limited": pgettext(_AI, "Saatlıq AI təhlili limitinə çatdınız. Bir az sonra yenidən cəhd edin."),
        "view_as": pgettext(_AI, "Başqa istifadəçi kimi baxış rejimində AI təhlili əlçatan deyil."),
        "timeout": pgettext(_AI, "AI xidməti vaxtında cavab vermədi. Yenidən cəhd edin."),
        "busy": pgettext(_AI, "AI xidməti hazırda məşğuldur. Bir az sonra yenidən cəhd edin."),
    }
    return messages.get(code, pgettext(_AI, "AI təhlili alınmadı. Yenidən cəhd edin."))


def _severity_label(severity: str) -> str:
    return {
        "normal": pgettext(_AI, "Normal"),
        "low": pgettext(_AI, "Aşağı"),
        "medium": pgettext(_AI, "Orta"),
        "high": pgettext(_AI, "Yüksək"),
        "critical": pgettext(_AI, "Kritik"),
    }.get(severity, "")


@require_POST
@csrf_protect
@monitoring_view_required
def ai_analysis_api(request):
    user = request.user
    if getattr(request, "is_view_as", False):
        return _no_store({"error": "view_as", "message": _error_message("view_as")}, status=403)

    from apps.ai_assistant.public import analyze_monitoring_snapshot, monitoring_ai_status

    status = monitoring_ai_status()
    if not status["enabled"] or not status["configured"]:
        code = "disabled" if not status["enabled"] else "not_configured"
        return _no_store({"error": code, "message": _error_message(code), **_ai_quota(user.pk)}, status=503)

    rate = _ai_rate()
    # Təhlükəsizlik auditi 2026-10-05: yoxla-və-say ATOMİKDİR (cache.incr) və snapshot/
    # Gemini-dən ƏVVƏLdir. Əvvəl «is_rate_limited → build_summary → record» idi: bu
    # pəncərədə gələn paralel kliklər hamısı yoxlamadan keçib Gemini-yə gedirdi.
    limited, retry_after = record_rate_limit_hit(AI_RATE_SCOPE, rate, user.pk)
    if limited:
        _audit(request, outcome="rate_limited", details={"retry_after": retry_after})
        response = _no_store(
            {"error": "rate_limited", "message": _error_message("rate_limited"), **_ai_quota(user.pk)}, status=429
        )
        if retry_after:
            response["Retry-After"] = str(retry_after)
        return response

    snapshot = build_ai_snapshot(build_summary(request.monitoring_scope))
    result = analyze_monitoring_snapshot(snapshot)
    details = {
        "ok": bool(result.get("ok")),
        "error": result.get("error", ""),
        "severity": result.get("severity", ""),
        "snapshot_chars": len(json.dumps(snapshot, ensure_ascii=False, default=str)),
        "prompt_tokens": result.get("prompt_tokens", 0),
        "response_tokens": result.get("response_tokens", 0),
        "platform_scope": request.monitoring_scope.platform,
    }
    _audit(request, outcome="ok" if result.get("ok") else "error", details=details)
    if not result.get("ok"):
        code = result.get("error", "unavailable")
        return _no_store({"error": code, "message": _error_message(code), **_ai_quota(user.pk)}, status=502)

    return _no_store(
        {
            "status": "ok",
            "data": {
                "answer": result["answer"],
                "severity": result.get("severity", ""),
                "severity_label": _severity_label(result.get("severity", "")),
                "generated_at": timezone.now().isoformat(),
                **_ai_quota(user.pk),
            },
        }
    )


__all__ = ["AI_RATE_SCOPE", "ai_analysis_api", "summary_api"]
