"""
AI-powered grading for written exam answers using Google Gemini.

Follows the same caching + rate-limiting pattern as ai_summary.py:
  1. Cache by SHA-256 hash of (question, answer, max_points, language)
  2. Per-user rate limiting (only on cache miss)
  3. Quota info in every response
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language, pgettext

from core.rate_limit import record_rate_limit_hit

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_CHAIN = ("gemini-2.5-flash-lite", "gemini-2.5-flash")
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2
_CACHE_TTL = 60 * 60 * 24  # 24 hours


def _get_grading_model_chain() -> tuple[str, ...]:
    try:
        from apps.exams.domain.ai_config import get_ai_config

        cfg = get_ai_config()
        if cfg:
            primary = cfg.grading_model
            fallbacks = [m for m in ("gemini-2.5-flash-lite", "gemini-2.5-flash") if m != primary]
            return (primary, *fallbacks)
    except Exception:
        pass
    return _DEFAULT_MODEL_CHAIN


def _is_ai_enabled() -> bool:
    try:
        from apps.exams.domain.ai_config import get_ai_config

        cfg = get_ai_config()
        return cfg.enabled if cfg else True
    except Exception:
        return True


def _get_api_key() -> str | None:
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


def _grade_cache_key(question_text: str, student_answer: str, max_points: int, lang: str) -> str:
    payload = json.dumps(
        {
            "question": question_text,
            "answer": student_answer,
            "max_points": max_points,
            "lang": lang,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"ai_grade:{digest}"


def _get_quota_info(user_id: int | None) -> dict:
    if user_id is None:
        return {}
    from apps.exams.services.ai_summary import get_user_ai_quota_info

    return get_user_ai_quota_info(user_id)


def _check_rate_limit(user_id: int) -> dict | None:
    from apps.exams.services.ai_summary import check_user_ai_rate_limit

    return check_user_ai_rate_limit(user_id)


def _record_hit(user_id: int) -> None:
    from apps.exams.services.ai_summary import _get_rate_limit

    record_rate_limit_hit("ai_summary", _get_rate_limit(), user_id)


def _parse_ai_grade(text: str, max_points: int) -> tuple[int, str]:
    """Extract score and explanation from AI response text.

    Expected format from the prompt:
        SCORE: <number>
        EXPLANATION: <text>

    Falls back to returning 0 and the full text if parsing fails.
    """
    score = 0
    explanation = text.strip()

    score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if score_match:
        score = min(int(float(score_match.group(1))), max_points)
        score = max(0, score)

    expl_match = re.search(r"EXPLANATION:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if expl_match:
        explanation = expl_match.group(1).strip()

    return score, explanation


def _build_grading_prompt(
    *,
    question_text: str,
    student_answer: str,
    max_points: int,
    correct_answer: str,
    lang_name: str,
) -> str:
    correct_section = ""
    if correct_answer:
        correct_section = f"""
**Reference/Correct Answer:**
{correct_answer}
"""

    return f"""You are an expert exam grader. Grade the following student answer.

**Question:**
{question_text}
{correct_section}
**Student's Answer:**
{student_answer}

**Maximum Points:** {max_points}

**Language:** Respond ONLY in {lang_name}.

**Instructions:**
- Evaluate the student's answer for correctness, completeness, and clarity.
- Assign a score from 0 to {max_points}.
- Provide a brief explanation of your grading decision.
- Be fair but thorough. Partial credit is acceptable for partially correct answers.
- If the answer is empty or completely irrelevant, give 0 points.

**You MUST respond in EXACTLY this format:**

SCORE: <number between 0 and {max_points}>
EXPLANATION: <your grading explanation in {lang_name}>"""


def grade_written_answer(
    *,
    question_text: str,
    student_answer: str,
    max_points: int,
    correct_answer: str = "",
    language_code: str | None = None,
    user_id: int | None = None,
) -> dict:
    """Grade a written answer using AI.

    Returns
    -------
    dict
        ``{"ok": True, "score": int, "explanation": str, "cached": bool, ...}``
        on success, or ``{"ok": False, "error": str}`` on failure.
    """
    if not _is_ai_enabled():
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "ai_disabled")}

    api_key = _get_api_key()
    if not api_key:
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "gemini_api_key_missing")}

    if not student_answer or not student_answer.strip():
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "empty_answer")}

    lang = language_code or get_language() or "en"
    lang_name = _language_name(lang)

    # ── Cache check ────────────────────────────────────────────────
    cache_key = _grade_cache_key(question_text, student_answer, max_points, lang)
    cached = cache.get(cache_key)
    if cached is not None:
        quota = _get_quota_info(user_id)
        return {"ok": True, "cached": True, **cached, **quota}

    # ── Per-user rate limit (only on cache miss) ───────────────────
    if user_id is not None:
        rate_limit_error = _check_rate_limit(user_id)
        if rate_limit_error is not None:
            return rate_limit_error

    # ── Call Gemini ────────────────────────────────────────────────
    prompt = _build_grading_prompt(
        question_text=question_text,
        student_answer=student_answer,
        max_points=max_points,
        correct_answer=correct_answer,
        lang_name=lang_name,
    )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        last_exc = None
        for model_name in _get_grading_model_chain():
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    text = (response.text or "").strip()

                    score, explanation = _parse_ai_grade(text, max_points)

                    result = {"score": score, "explanation": explanation}
                    cache.set(cache_key, result, _CACHE_TTL)

                    if user_id is not None:
                        _record_hit(user_id)

                    quota = _get_quota_info(user_id)
                    return {"ok": True, "cached": False, **result, **quota}
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

        exc_str = str(last_exc) if last_exc else ""
        if last_exc and ("ResourceExhausted" in type(last_exc).__name__ or "429" in exc_str):
            return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "gemini_quota_exhausted")}

        logger.exception("AI grading failed", exc_info=last_exc)
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "grading_failed")}
    except Exception:
        logger.exception("AI grading failed")
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "grading_failed")}
