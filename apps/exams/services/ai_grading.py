"""
AI-powered grading for written exam answers using Google Gemini.

Follows the same caching + rate-limiting pattern as ai_summary.py:
  1. Cache by SHA-256 hash of (question, answer, max_points, language)
  2. Per-user rate limiting (only on cache miss)
  3. Quota info in every response
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import re
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language, pgettext

import requests

from core.rate_limit import record_rate_limit_hit

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_CHAIN = ("gemini-2.5-flash-lite", "gemini-2.5-flash")
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2
_CACHE_TTL = 60 * 60 * 24  # 24 hours
_REQUEST_TIMEOUT_SECONDS = 60
_GRADE_PROMPT_VERSION = 2


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
    return _grade_cache_key_with_attachments(
        question_text=question_text,
        student_answer=student_answer,
        max_points=max_points,
        lang=lang,
        attachment_hashes=(),
    )


def _grade_cache_key_with_attachments(
    *,
    question_text: str,
    student_answer: str,
    max_points: int,
    lang: str,
    attachment_hashes: Iterable[str],
) -> str:
    payload = json.dumps(
        {
            "version": _GRADE_PROMPT_VERSION,
            "question": question_text,
            "answer": student_answer,
            "max_points": max_points,
            "lang": lang,
            "attachments": list(attachment_hashes),
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


def _round_score(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_score_number(raw_value: str) -> Decimal | None:
    try:
        return Decimal((raw_value or "").strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _parse_ai_grade(text: str, max_points: int) -> tuple[int, str]:
    """Extract score and explanation from AI response text.

    Expected format from the prompt:
        SCORE: <number>
        EXPLANATION: <text>

    Falls back to returning 0 and the full text if parsing fails.
    """
    max_points = max(1, int(max_points or 1))
    score = 0
    explanation = text.strip()

    score_match = re.search(
        r"(?:SCORE|BAL|Q[İI]YM[ƏE]T|XAL|PUAN|POINTS?|ОЦЕНКА|БАЛЛ)\s*[:\-]\s*"
        r"(\d+(?:[\.,]\d+)?)"
        r"(?:\s*/\s*(\d+(?:[\.,]\d+)?))?"
        r"(\s*%)?",
        text,
        re.IGNORECASE,
    )
    if score_match:
        raw_score = _parse_score_number(score_match.group(1))
        raw_denominator = _parse_score_number(score_match.group(2) or "")
        if raw_score is not None:
            if score_match.group(3):
                scaled_score = raw_score * Decimal(max_points) / Decimal("100")
            elif raw_denominator and raw_denominator > 0:
                scaled_score = raw_score * Decimal(max_points) / raw_denominator
            else:
                scaled_score = raw_score
            score = min(_round_score(scaled_score), max_points)
            score = max(0, score)

    expl_match = re.search(
        r"(?:EXPLANATION|IZAH|İZAH|A[ÇC]IQLAMA|R[ƏE]Y|FEEDBACK|COMMENT|Ş[ƏE]RH)\s*[:\-]\s*(.+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if expl_match:
        explanation = expl_match.group(1).strip()
    elif score_match:
        explanation = (text[: score_match.start()] + text[score_match.end() :]).strip()

    return score, explanation


def _normalized_text(student_answer: str) -> str:
    return (student_answer or "").strip()


def _materialize_answer_files(answer_files) -> list:
    if not answer_files:
        return []
    if hasattr(answer_files, "all"):
        return list(answer_files.all())
    return list(answer_files)


def _detect_mime_type(file_obj, fallback_name: str = "") -> str:
    mime_type = (
        (getattr(file_obj, "content_type", "") or getattr(getattr(file_obj, "file", None), "content_type", "") or "")
        .strip()
        .lower()
    )
    if mime_type:
        return mime_type

    guessed, _ = mimetypes.guess_type(getattr(file_obj, "name", "") or fallback_name)
    return (guessed or "").strip().lower()


def _is_image_mime_type(mime_type: str) -> bool:
    return bool(mime_type and mime_type.startswith("image/"))


def _read_file_bytes(file_obj) -> bytes:
    if not file_obj:
        return b""

    try:
        file_obj.open("rb")
    except Exception:
        pass

    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        data = file_obj.read()
    finally:
        try:
            file_obj.close()
        except Exception:
            pass

    return data or b""


def _collect_image_inputs(*, answer_files=None, paint_image=None) -> list[dict]:
    image_inputs: list[dict] = []

    for answer_file in _materialize_answer_files(answer_files):
        file_field = getattr(answer_file, "file", None)
        if not file_field:
            continue

        mime_type = _detect_mime_type(file_field)
        if not _is_image_mime_type(mime_type):
            continue

        binary = _read_file_bytes(file_field)
        if not binary:
            continue

        image_inputs.append(
            {
                "mime_type": mime_type,
                "data_b64": base64.b64encode(binary).decode("ascii"),
                "attachment_hash": hashlib.sha256(mime_type.encode("utf-8") + b":" + binary).hexdigest(),
            }
        )

    if paint_image:
        mime_type = _detect_mime_type(paint_image, fallback_name="paint.png") or "image/png"
        if _is_image_mime_type(mime_type):
            binary = _read_file_bytes(paint_image)
            if binary:
                image_inputs.append(
                    {
                        "mime_type": mime_type,
                        "data_b64": base64.b64encode(binary).decode("ascii"),
                        "attachment_hash": hashlib.sha256(mime_type.encode("utf-8") + b":" + binary).hexdigest(),
                    }
                )

    return image_inputs


def has_written_answer_content(*, student_answer: str = "", answer_files=None, paint_image=None) -> bool:
    return bool(_normalized_text(student_answer)) or bool(_materialize_answer_files(answer_files)) or bool(paint_image)


def has_ai_gradeable_answer_content(*, student_answer: str = "", answer_files=None, paint_image=None) -> bool:
    if _normalized_text(student_answer):
        return True
    return bool(_collect_image_inputs(answer_files=answer_files, paint_image=paint_image))


def _build_grading_prompt(
    *,
    question_text: str,
    student_answer: str,
    max_points: int,
    correct_answer: str,
    lang_name: str,
    includes_image_inputs: bool,
) -> str:
    correct_section = ""
    if correct_answer:
        correct_section = f"""
**Reference/Correct Answer:**
{correct_answer}
"""

    image_section = ""
    if includes_image_inputs:
        image_section = """
**Attached Visual Answer Material:**
- The student's answer may include uploaded images or drawn work.
- Read handwriting, formulas, diagrams, screenshots, and annotations in the images before grading.
"""

    return f"""You are an expert exam grader. Grade the following student answer.

**Question:**
{question_text}
{correct_section}
**Student's Answer:**
{student_answer}
{image_section}

**Maximum Points:** {max_points}

**Language:** Respond ONLY in {lang_name}.

**Instructions:**
- Evaluate the student's answer for correctness, completeness, relevance, and clarity.
- Assign an INTEGER score from 0 to {max_points}. Use the full {max_points}-point scale, not a binary correct/incorrect score.
- Calibrate the score like a fair human teacher: excellent answers should be near {max_points}, mostly correct answers around 70-90%, partially correct answers around 40-70%, minimal but relevant answers around 10-40%, and empty or completely irrelevant answers 0.
- If there is no reference answer, grade against a reasonable expert answer to the question and give credit for valid reasoning, terminology, examples, and partial understanding.
- Do not give 1 point just because the answer is imperfect when the maximum score is higher; scale partial credit proportionally.
- Provide brief, constructive teacher-style feedback that explains what is good and what is missing.

**You MUST respond in EXACTLY this format:**

SCORE: <integer between 0 and {max_points}>
EXPLANATION: <your grading explanation in {lang_name}>"""


def _gemini_generate_content(*, model_name: str, api_key: str, prompt: str, image_inputs: list[dict]) -> str:
    parts = [{"text": prompt}]
    for image in image_inputs:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image["mime_type"],
                    "data": image["data_b64"],
                }
            }
        )

    response = requests.post(
        (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(model_name, safe='')}:"
            "generateContent"
            f"?key={api_key}"
        ),
        json={"contents": [{"parts": parts}]},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        error_message = (
            payload.get("error", {}).get("message") or response.text or f"Gemini HTTP {response.status_code}"
        )
        raise requests.HTTPError(error_message, response=response)

    payload = response.json()
    texts = []
    for candidate in payload.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text = (part.get("text") or "").strip()
            if text:
                texts.append(text)

    return "\n".join(texts).strip()


def grade_written_answer(
    *,
    question_text: str,
    student_answer: str,
    max_points: int,
    correct_answer: str = "",
    language_code: str | None = None,
    user_id: int | None = None,
    answer_files=None,
    paint_image=None,
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

    normalized_answer = _normalized_text(student_answer)
    image_inputs = _collect_image_inputs(answer_files=answer_files, paint_image=paint_image)
    if not normalized_answer and not image_inputs:
        return {"ok": False, "error": pgettext("exams.service.ai_grading.error", "empty_answer")}

    lang = language_code or get_language() or "en"
    lang_name = _language_name(lang)

    # ── Cache check ────────────────────────────────────────────────
    cache_key = _grade_cache_key_with_attachments(
        question_text=question_text,
        student_answer=normalized_answer,
        max_points=max_points,
        lang=lang,
        attachment_hashes=(item["attachment_hash"] for item in image_inputs),
    )
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
        student_answer=normalized_answer,
        max_points=max_points,
        correct_answer=correct_answer,
        lang_name=lang_name,
        includes_image_inputs=bool(image_inputs),
    )

    try:
        last_exc = None
        for model_name in _get_grading_model_chain():
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    text = _gemini_generate_content(
                        model_name=model_name,
                        api_key=api_key,
                        prompt=prompt,
                        image_inputs=image_inputs,
                    )

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
                    response = getattr(exc, "response", None)
                    response_status = getattr(response, "status_code", None)
                    if response_status == 429 or "ResourceExhausted" in exc_name or "429" in str(exc):
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
