"""
AI-powered exam statistics summary generation using Google Gemini.

Reads the API key from the GEMINI_API_KEY environment variable.
Falls back gracefully when the key is not configured.

Caching strategy:
    A SHA-256 hash of the stats dict is used as a cache key.  When the
    same data is requested again the cached response is returned without
    consuming an API call.  The cache is invalidated automatically when
    the underlying data changes (new attempts, updated scores, etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language, pgettext

from core.rate_limit import is_rate_limited, parse_rate, record_rate_limit_hit

logger = logging.getLogger(__name__)

# Default fallback values (used when DB is unreachable)
_DEFAULT_MODEL_CHAIN = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
_DEFAULT_RATE_LIMIT = "100/1h"

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2  # seconds

# Cache TTL for AI summaries — 24 hours (data-hash based, so stale data
# is never served; the TTL is just an upper bound).
_CACHE_TTL = 60 * 60 * 24


def _get_ai_config():
    """Load the AIConfiguration singleton (cached for 60s)."""
    try:
        from apps.exams.domain.ai_config import get_ai_config

        return get_ai_config()
    except Exception:
        return None


def _get_rate_limit() -> str:
    cfg = _get_ai_config()
    if cfg:
        return cfg.rate_limit
    return getattr(settings, "AI_RATE_LIMIT", _DEFAULT_RATE_LIMIT)


def _get_summary_model_chain() -> tuple[str, ...]:
    cfg = _get_ai_config()
    if cfg:
        primary = cfg.summary_model
        fallbacks = [m for m in ("gemini-2.5-flash", "gemini-2.5-flash-lite") if m != primary]
        return (primary, *fallbacks)
    return _DEFAULT_MODEL_CHAIN


def _is_ai_enabled() -> bool:
    cfg = _get_ai_config()
    return cfg.enabled if cfg else True


def _get_api_key() -> str | None:
    """Return the Gemini API key from settings, or *None* if unconfigured."""
    key = getattr(settings, "GEMINI_API_KEY", "") or ""
    return key.strip() or None


def _language_name(code: str) -> str:
    mapping = {
        "az": "Azerbaijani",
        "en": "English",
        "ru": "Russian",
        "tr": "Turkish",
    }
    return mapping.get(code, "English")


def _stats_cache_key(exam_title: str, exam_type: str, stats: dict, lang: str) -> str:
    """Deterministic cache key based on the content hash of the input data."""
    payload = json.dumps(
        {"title": exam_title, "type": exam_type, "stats": stats, "lang": lang},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ai_summary:{digest}"


def check_user_ai_rate_limit(user_id: int) -> dict | None:
    """Check per-user AI rate limit.  Returns an error dict if limited, else None."""
    rate = _get_rate_limit()
    limited, retry_after = is_rate_limited("ai_summary", rate, user_id)
    if limited:
        return {
            "ok": False,
            "error": pgettext("exams.service.ai_summary.error", "ai_rate_limit_exceeded"),
            "retry_after": retry_after,
        }
    return None


def get_user_ai_quota_info(user_id: int) -> dict:
    """Return remaining AI quota info for the current user."""
    rate = _get_rate_limit()
    parsed = parse_rate(rate)
    if parsed is None:
        return {"limit": 0, "remaining": 0, "window": ""}

    from core.rate_limit import _cache_keys, _rate_limit_cache

    rl_cache = _rate_limit_cache()
    count_key, _ = _cache_keys("ai_summary", (user_id,))
    current = int(rl_cache.get(count_key) or 0)
    remaining = max(0, parsed.limit - current)

    window_seconds = parsed.window_seconds
    if window_seconds >= 3600:
        window_label = f"{window_seconds // 3600}h"
    elif window_seconds >= 60:
        window_label = f"{window_seconds // 60}m"
    else:
        window_label = f"{window_seconds}s"

    return {
        "limit": parsed.limit,
        "remaining": remaining,
        "window": window_label,
    }


def generate_exam_statistics_summary(
    *,
    exam_title: str,
    exam_type: str,
    stats: dict,
    language_code: str | None = None,
    user_id: int | None = None,
) -> dict:
    """Generate an AI-powered summary of exam statistics.

    Parameters
    ----------
    exam_title : str
        Human-readable exam title.
    exam_type : str
        "test", "written", or a live-exam identifier.
    stats : dict
        Pre-computed statistics dictionary containing keys such as
        ``total_attempts``, ``avg_score``, ``pass_rate``, ``group_stats``,
        ``question_stats``, etc.
    language_code : str | None
        ISO language code (az/en/ru/tr).  Defaults to the current request
        language.
    user_id : int | None
        The requesting user's ID — used for per-user rate limiting.

    Returns
    -------
    dict
        ``{"ok": True, "summary": "<markdown text>", "cached": bool}``
        on success, or ``{"ok": False, "error": "<reason>"}`` on failure.
    """
    if not _is_ai_enabled():
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "ai_disabled")}

    api_key = _get_api_key()
    if not api_key:
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "gemini_api_key_missing")}

    lang = language_code or get_language() or "en"
    lang_name = _language_name(lang)

    # ── Cache check — skip API call if data is unchanged ─────────────
    cache_key = _stats_cache_key(exam_title, exam_type, stats, lang)
    cached = cache.get(cache_key)
    if cached is not None:
        quota = get_user_ai_quota_info(user_id) if user_id else {}
        return {"ok": True, "summary": cached, "cached": True, **quota}

    # ── Per-user rate limit (only charged on cache miss = real API call)
    if user_id is not None:
        rate_limit_error = check_user_ai_rate_limit(user_id)
        if rate_limit_error is not None:
            return rate_limit_error

    # ── Call Gemini API ──────────────────────────────────────────────
    prompt = _build_prompt(
        exam_title=exam_title,
        exam_type=exam_type,
        stats=stats,
        lang_name=lang_name,
    )

    model_chain = _get_summary_model_chain()

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        last_exc = None
        for model_name in model_chain:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    text = (response.text or "").strip()

                    # Cache the successful response
                    cache.set(cache_key, text, _CACHE_TTL)

                    # Record rate limit hit (only on real API call)
                    if user_id is not None:
                        record_rate_limit_hit("ai_summary", _get_rate_limit(), user_id)

                    quota = get_user_ai_quota_info(user_id) if user_id else {}
                    return {"ok": True, "summary": text, "cached": False, **quota}
                except Exception as exc:
                    last_exc = exc
                    exc_name = type(exc).__name__
                    if "ResourceExhausted" in exc_name or "429" in str(exc):
                        if attempt < _MAX_RETRIES:
                            time.sleep(_RETRY_BASE_DELAY * (attempt + 1))
                            continue
                        logger.warning("Gemini rate limit on %s after %d retries", model_name, _MAX_RETRIES)
                        break
                    logger.warning("Gemini error on %s: %s", model_name, exc_name)
                    break

        # All models failed
        exc_str = str(last_exc) if last_exc else ""
        if "ResourceExhausted" in type(last_exc).__name__ or "429" in exc_str:
            logger.error("Gemini quota exhausted across all models")
            return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "gemini_quota_exhausted")}

        logger.exception("Gemini AI summary generation failed", exc_info=last_exc)
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "generation_failed")}
    except Exception:
        logger.exception("Gemini AI summary generation failed")
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "generation_failed")}


def _build_prompt(
    *,
    exam_title: str,
    exam_type: str,
    stats: dict,
    lang_name: str,
) -> str:
    stats_json = json.dumps(stats, ensure_ascii=False, default=str)
    return f"""You are an expert education analytics assistant. Analyze the following exam statistics and provide a professional summary.

**Exam:** {exam_title}
**Type:** {exam_type}
**Language:** Respond ONLY in {lang_name}.

**Statistics data (JSON):**
```json
{stats_json}
```

Please provide:
1. **Performance Summary** — A concise overview of overall performance.
2. **Critical Analysis** — Key strengths and weaknesses observed.
3. **Notable Patterns** — Any anomalies, trends, or outliers.
4. **Group Comparison** (if group data is present) — Compare groups by average score, pass rate, and participation.
5. **Topic/Question Analysis** (if question data is present) — Which topics/questions students struggled with most and which they excelled at.
6. **Recommendations** — Actionable suggestions for teachers to improve outcomes.
7. **Students at Risk** — Identify struggling students or groups that need extra attention.

Format the response in clean Markdown with headers. Be concise but thorough. Do not include the raw data in your response. Focus on insights and actionable information."""
