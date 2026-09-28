"""Strukturlaşdırılmış (JSON) AI cavabı — digər modullar üçün ümumi giriş nöqtəsi.

Sual yaratma (``ai_question_generation``) ilə EYNİ infrastruktur: model zənciri,
``GEMINI_API_KEY``, AI konfiqurasiyasının ``enabled`` bayrağı və istifadəçi başına
``ai_summary`` rate-limit kvotası. Çağıran yalnız prompt verir, normallaşdırılmış
``dict`` alır; Gemini SDK detalları exams daxilində qalır.
"""

from __future__ import annotations

import logging

from django.utils.translation import pgettext

from apps.exams.services.ai_question_generation import (
    _call_gemini_text,
    _is_ai_enabled,
    _json_from_model_text,
    _question_model_chain,
)
from apps.exams.services.ai_summary import (
    _get_api_key,
    _get_rate_limit,
    check_user_ai_rate_limit,
    get_user_ai_quota_info,
)
from core.rate_limit import record_rate_limit_hit

logger = logging.getLogger(__name__)

_CTX = "exams.service.ai_summary.error"
_REQUEST_TIMEOUT_SECONDS = 45


def generate_ai_json(*, prompt: str, user_id: int | None = None) -> dict:
    """Promptu modelə göndərib JSON obyektini qaytarır.

    Uğur: ``{"ok": True, "payload": dict, **kvota}``; xəta: ``{"ok": False, "code": str, "error": str}``
    (``code``: empty_prompt / disabled / key_missing / rate_limited / quota / generation_failed —
    çağıran öz kontekstinə uyğun mesaj seçə bilsin).
    Kvota yalnız UĞURLU cavabda sayılır (sual yaratma ilə eyni qayda).
    """
    if not (prompt or "").strip():
        return {"ok": False, "code": "empty_prompt", "error": pgettext(_CTX, "ai_empty_prompt")}
    if not _is_ai_enabled():
        return {"ok": False, "code": "disabled", "error": pgettext(_CTX, "ai_disabled")}
    if not _get_api_key():
        return {"ok": False, "code": "key_missing", "error": pgettext(_CTX, "gemini_api_key_missing")}
    if user_id is not None:
        limited = check_user_ai_rate_limit(user_id)
        if limited is not None:
            return {"code": "rate_limited", **limited}

    try:
        # Audit 2026-09-28 DB-05: sorğu axınında işləyir — hər model çağırışına zaman limiti
        # və yalnız ilk iki model (ən pis halda ~6 cəhd × 45 s əvəzinə 2 model).
        raw = _call_gemini_text(
            prompt=prompt, model_chain=_question_model_chain()[:2], request_timeout=_REQUEST_TIMEOUT_SECONDS
        )
        payload = _json_from_model_text(raw)
    except Exception as exc:
        logger.warning("AI JSON generation failed: %s", type(exc).__name__)
        if "ResourceExhausted" in type(exc).__name__ or "429" in str(exc):
            return {"ok": False, "code": "quota", "error": pgettext(_CTX, "gemini_quota_exhausted")}
        return {"ok": False, "code": "generation_failed", "error": pgettext(_CTX, "generation_failed")}

    if user_id is not None:
        record_rate_limit_hit("ai_summary", _get_rate_limit(), user_id)
    quota = get_user_ai_quota_info(user_id) if user_id else {}
    return {"ok": True, "payload": payload, **quota}
