from __future__ import annotations

import json
import logging
import re
import time

from django.conf import settings
from django.utils.translation import get_language, pgettext

from apps.exams.services.ai_summary import (
    _get_api_key,
    _get_rate_limit,
    check_user_ai_rate_limit,
    get_user_ai_quota_info,
)
from core.rate_limit import record_rate_limit_hit

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_CHAIN = ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite")
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2
_MAX_SOURCE_CHARS = 24000
_MAX_QUESTION_COUNT = 50


def _is_ai_enabled() -> bool:
    try:
        from apps.exams.domain.ai_config import get_ai_config

        return get_ai_config().enabled
    except Exception:
        return True


def _question_model_chain() -> tuple[str, ...]:
    configured = (getattr(settings, "AI_QUESTION_MODEL", "") or "").strip()
    if configured:
        fallbacks = [model for model in _DEFAULT_MODEL_CHAIN if model != configured]
        return (configured, *fallbacks)
    return _DEFAULT_MODEL_CHAIN


def _language_name(code: str) -> str:
    mapping = {
        "az": "Azerbaijani",
        "en": "English",
        "ru": "Russian",
        "tr": "Turkish",
    }
    return mapping.get(code, "Azerbaijani")


def _safe_question_count(raw_count) -> int:
    try:
        count = int(raw_count)
    except (TypeError, ValueError):
        return 5
    return min(max(count, 1), _MAX_QUESTION_COUNT)


def _compact_source_text(source_text: str) -> str:
    text = re.sub(r"\s+", " ", (source_text or "").strip())
    if len(text) <= _MAX_SOURCE_CHARS:
        return text
    return text[:_MAX_SOURCE_CHARS]


def _json_from_model_text(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty AI response")

    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(raw[start : end + 1])

    if isinstance(payload, list):
        return {"questions": payload}
    if not isinstance(payload, dict):
        raise ValueError("AI response is not a JSON object")
    return payload


def _call_gemini_text(*, prompt: str, model_chain: tuple[str, ...]) -> str:
    import google.generativeai as genai

    api_key = _get_api_key()
    genai.configure(api_key=api_key)

    last_exc = None
    generation_config = {
        "temperature": 0.35,
        "top_p": 0.9,
        "response_mime_type": "application/json",
    }

    for model_name in model_chain:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                model = genai.GenerativeModel(model_name)
                try:
                    response = model.generate_content(prompt, generation_config=generation_config)
                except TypeError:
                    response = model.generate_content(prompt)
                return (getattr(response, "text", "") or "").strip()
            except Exception as exc:
                last_exc = exc
                exc_name = type(exc).__name__
                if "ResourceExhausted" in exc_name or "429" in str(exc):
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_BASE_DELAY * (attempt + 1))
                        continue
                    logger.warning("Gemini rate limit on %s after %d retries", model_name, _MAX_RETRIES)
                    break
                logger.warning("Gemini question generation failed on %s: %s", model_name, exc_name)
                break

    raise RuntimeError(str(last_exc) if last_exc else "Gemini generation failed")


def _build_prompt(
    *,
    exam_title: str,
    exam_type: str,
    prompt_text: str,
    source_text: str,
    question_count: int,
    difficulty: str,
    block_name: str,
    lang_name: str,
) -> str:
    difficulty_label = {
        "easy": "easy",
        "medium": "medium",
        "hard": "hard",
        "mixed": "mixed difficulty",
    }.get(difficulty, "medium")

    source_block = source_text or "No lecture/source text was provided."
    teacher_prompt = prompt_text or "Create exam questions from the provided source text."
    target_context = f"Block/topic: {block_name}" if block_name else "No block/topic name was provided."

    if exam_type == "test":
        schema = """
Return ONLY valid JSON in this exact shape:
{
  "questions": [
    {
      "text": "Question text",
      "options": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
      "correct": ["A"],
      "answer_mode": "single"
    }
  ]
}
Rules:
- Create exactly the requested number of questions.
- Every question must have A, B, C, D and E options.
- Use one correct answer unless the teacher explicitly asks for multiple choice.
- Keep answers unambiguous and avoid duplicate option meanings.
- Do not number the question text and do not include markdown.
"""
    else:
        schema = """
Return ONLY valid JSON in this exact shape:
{
  "questions": [
    {"text": "Written exam question text"}
  ]
}
Rules:
- Create exactly the requested number of written questions.
- Each item must be a clear standalone question or task.
- Do not include answers, rubrics, numbering, markdown, or extra commentary.
"""

    return f"""You are an expert exam question writer for Learn Hub.
Language: Respond in {lang_name}.
Exam title: {exam_title}
Exam type: {exam_type}
Requested count: {question_count}
Difficulty: {difficulty_label}
{target_context}

Teacher instruction:
{teacher_prompt}

Lecture/source text:
{source_block}

{schema}
"""


def _clean_label(value: str) -> str:
    label = (value or "").strip().upper()
    return label[:1] if label[:1] in "ABCDE" else ""


def _normalise_test_questions(payload: dict, question_count: int) -> list[dict]:
    questions = payload.get("questions") or []
    if not isinstance(questions, list):
        return []

    normalised = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        options_payload = item.get("options") or {}
        if not text or not isinstance(options_payload, dict):
            continue

        options = {}
        for label in "ABCDE":
            value = str(options_payload.get(label) or options_payload.get(label.lower()) or "").strip()
            if value:
                options[label] = value

        if any(label not in options for label in "ABCD"):
            continue

        correct_payload = item.get("correct") or item.get("answers") or []
        if isinstance(correct_payload, str):
            correct_labels = re.split(r"\s*[,;/]\s*", correct_payload)
        else:
            correct_labels = list(correct_payload) if isinstance(correct_payload, list) else []
        correct = []
        for label in correct_labels:
            clean = _clean_label(str(label))
            if clean and clean in options and clean not in correct:
                correct.append(clean)
        if not correct:
            correct = ["A"]

        normalised.append(
            {
                "text": text,
                "options": options,
                "correct": correct,
                "answer_mode": "multiple" if len(correct) > 1 else "single",
            }
        )
        if len(normalised) >= question_count:
            break

    return normalised


def _normalise_written_questions(payload: dict, question_count: int) -> list[str]:
    questions = payload.get("questions") or []
    if not isinstance(questions, list):
        return []

    normalised = []
    for item in questions:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("question") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            normalised.append(text)
        if len(normalised) >= question_count:
            break
    return normalised


def _render_test_questions(questions: list[dict]) -> str:
    blocks = []
    for index, question in enumerate(questions, start=1):
        lines = [f"{index}. {question['text']}"]
        for label in "ABCDE":
            if label in question["options"]:
                lines.append(f"{label}) {question['options'][label]}")
        lines.append(f"Cavab: {', '.join(question['correct'])}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_written_questions(questions: list[str]) -> str:
    return "\n".join(f"{index}. {text}" for index, text in enumerate(questions, start=1))


def generate_question_bank_text(
    *,
    exam_title: str,
    exam_type: str,
    prompt_text: str = "",
    source_text: str = "",
    question_count=5,
    difficulty: str = "medium",
    block_name: str = "",
    language_code: str | None = None,
    user_id: int | None = None,
) -> dict:
    if exam_type not in {"test", "written"}:
        return {
            "ok": False,
            "error": pgettext(
                "exams.service.ai_questions.error",
                "Bu imtahan tipi üçün AI sual yaratma dəstəklənmir.",
            ),
        }

    prompt_text = (prompt_text or "").strip()
    source_text = _compact_source_text(source_text)
    if not prompt_text and not source_text:
        return {
            "ok": False,
            "error": pgettext(
                "exams.service.ai_questions.error",
                "Prompt yazın və ya mənbə faylı əlavə edin.",
            ),
        }

    if not _is_ai_enabled():
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "ai_disabled")}

    if not _get_api_key():
        return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "gemini_api_key_missing")}

    if user_id is not None:
        rate_limit_error = check_user_ai_rate_limit(user_id)
        if rate_limit_error is not None:
            return rate_limit_error

    count = _safe_question_count(question_count)
    lang = language_code or get_language() or "az"
    lang_name = _language_name(lang)
    prompt = _build_prompt(
        exam_title=exam_title,
        exam_type=exam_type,
        prompt_text=prompt_text,
        source_text=source_text,
        question_count=count,
        difficulty=(difficulty or "medium").strip().lower(),
        block_name=(block_name or "").strip(),
        lang_name=lang_name,
    )

    try:
        raw_response = _call_gemini_text(prompt=prompt, model_chain=_question_model_chain())
        payload = _json_from_model_text(raw_response)
        if exam_type == "test":
            questions = _normalise_test_questions(payload, count)
            rendered = _render_test_questions(questions)
        else:
            questions = _normalise_written_questions(payload, count)
            rendered = _render_written_questions(questions)

        if not rendered:
            return {
                "ok": False,
                "error": pgettext(
                    "exams.service.ai_questions.error",
                    "AI cavabı gözlənilən sual formatında olmadı.",
                ),
            }

        if user_id is not None:
            record_rate_limit_hit("ai_summary", _get_rate_limit(), user_id)

        quota = get_user_ai_quota_info(user_id) if user_id else {}
        return {
            "ok": True,
            "text": rendered,
            "question_count": len(questions),
            "exam_type": exam_type,
            "model": _question_model_chain()[0],
            **quota,
        }
    except Exception as exc:
        logger.exception("AI question generation failed")
        if "ResourceExhausted" in type(exc).__name__ or "429" in str(exc):
            return {"ok": False, "error": pgettext("exams.service.ai_summary.error", "gemini_quota_exhausted")}
        return {
            "ok": False,
            "error": pgettext(
                "exams.service.ai_questions.error",
                "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın.",
            ),
        }
