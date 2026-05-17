from __future__ import annotations

import json
import logging

from django.db import transaction
from django.utils import timezone

from apps.exams.models import ExamQuestion
from apps.exams.services.ai_question_generation import (
    _call_gemini_text,
    _get_api_key,
    _is_ai_enabled,
    _json_from_model_text,
    _question_model_chain,
)

logger = logging.getLogger(__name__)

_DIFFICULTIES = {"easy", "medium", "hard"}
_BATCH_SIZE = 40
_BALANCE_STATUS_KEY = "ai_difficulty_balance"


def _normalise_difficulty(value) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "easy": "easy",
        "asan": "easy",
        "sadə": "easy",
        "sade": "easy",
        "medium": "medium",
        "orta": "medium",
        "normal": "medium",
        "hard": "hard",
        "çətin": "hard",
        "cetin": "hard",
        "difficult": "hard",
    }
    return aliases.get(raw, "")


def _question_payload(question: ExamQuestion) -> dict:
    options = [option.text for option in question.options.all()]
    payload = {
        "id": question.id,
        "text": question.text,
        "answer_mode": question.answer_mode,
        "points": question.points,
    }
    if options:
        payload["options"] = options
    if question.correct_answer:
        payload["correct_answer"] = question.correct_answer
    if question.block_id:
        payload["block"] = getattr(question.block, "name", "")
    return payload


def _build_difficulty_prompt(exam, questions: list[ExamQuestion]) -> str:
    items = json.dumps([_question_payload(question) for question in questions], ensure_ascii=False)
    return f"""You are calibrating exam question difficulty.
Exam title: {exam.title}
Classify each question as exactly one of: easy, medium, hard.

Use these guidelines:
- easy: direct recall, one-step recognition, or very simple application.
- medium: normal exam-level understanding, two-step reasoning, or moderate application.
- hard: multi-step reasoning, ambiguity resolution, synthesis, proof, or advanced application.

Return ONLY valid JSON in this exact shape:
{{
  "questions": [
    {{"id": 123, "difficulty": "easy"}}
  ]
}}

Questions:
{items}
"""


def _parse_difficulty_payload(payload: dict) -> dict[int, str]:
    parsed: dict[int, str] = {}

    questions = payload.get("questions") or payload.get("items") or payload.get("results")
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id") or item.get("question_id")
            try:
                question_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            difficulty = _normalise_difficulty(item.get("difficulty") or item.get("level") or item.get("weight"))
            if difficulty in _DIFFICULTIES:
                parsed[question_id] = difficulty
        return parsed

    for raw_id, raw_difficulty in payload.items():
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        difficulty = _normalise_difficulty(raw_difficulty)
        if difficulty in _DIFFICULTIES:
            parsed[question_id] = difficulty
    return parsed


def classify_question_difficulties_with_ai(exam, questions: list[ExamQuestion]) -> dict[int, str]:
    if not questions:
        return {}

    prompt = _build_difficulty_prompt(exam, questions)
    raw_response = _call_gemini_text(prompt=prompt, model_chain=_question_model_chain())
    payload = _json_from_model_text(raw_response)
    return _parse_difficulty_payload(payload)


def ensure_ai_question_difficulties(exam, *, force: bool = False) -> int:
    """
    Best-effort AI difficulty calibration.

    Student exam start must never fail because AI is unavailable, so this
    service quietly falls back to existing question.difficulty values.
    """
    if not getattr(exam, "ai_difficulty_balance_enabled", False):
        return 0
    if not _is_ai_enabled() or not _get_api_key():
        return 0

    queryset = exam.questions.filter(is_active=True).prefetch_related("options").select_related("block")
    if not force:
        queryset = queryset.exclude(difficulty_source="ai")

    questions = list(queryset.order_by("id"))
    if not questions:
        return 0

    updated_total = 0
    now = timezone.now()
    for start in range(0, len(questions), _BATCH_SIZE):
        batch = questions[start : start + _BATCH_SIZE]
        try:
            difficulties = classify_question_difficulties_with_ai(exam, batch)
        except Exception:
            logger.exception("AI difficulty calibration failed for exam %s", getattr(exam, "pk", None))
            continue

        changed = []
        for question in batch:
            difficulty = difficulties.get(question.id)
            if difficulty not in _DIFFICULTIES:
                continue
            question.difficulty = difficulty
            question.difficulty_source = "ai"
            question.difficulty_checked_at = now
            changed.append(question)

        if changed:
            ExamQuestion.objects.bulk_update(
                changed,
                ["difficulty", "difficulty_source", "difficulty_checked_at"],
            )
            updated_total += len(changed)

    return updated_total


def _set_ai_balance_status(exam_pk: int, *, status: str, updated_count: int | None = None, error: str = "") -> None:
    from apps.exams.models import Exam

    with transaction.atomic():
        exam = Exam.objects.select_for_update().only("id", "settings").get(pk=exam_pk)
        settings = dict(exam.settings or {})
        payload = {
            "status": status,
            "updated_at": timezone.now().isoformat(),
        }
        if updated_count is not None:
            payload["updated_count"] = updated_count
        if error:
            payload["error"] = error
        settings[_BALANCE_STATUS_KEY] = payload
        exam.settings = settings
        exam.save(update_fields=["settings"])


def warm_ai_question_difficulties_for_exam(*, exam_pk: int, force: bool = False) -> int:
    from apps.exams.models import Exam

    exam = Exam.objects.filter(pk=exam_pk).first()
    if exam is None or not getattr(exam, "ai_difficulty_balance_enabled", False):
        return 0

    if not _is_ai_enabled():
        _set_ai_balance_status(exam_pk, status="skipped", error="ai_disabled")
        return 0
    if not _get_api_key():
        _set_ai_balance_status(exam_pk, status="skipped", error="gemini_api_key_missing")
        return 0

    _set_ai_balance_status(exam_pk, status="pending")
    try:
        updated_count = ensure_ai_question_difficulties(exam, force=force)
    except Exception as exc:
        logger.exception("AI difficulty warmup failed for exam %s", exam_pk)
        _set_ai_balance_status(exam_pk, status="failed", error=type(exc).__name__)
        return 0

    _set_ai_balance_status(exam_pk, status="ready", updated_count=updated_count)
    return updated_count


def schedule_ai_question_difficulty_warmup(exam, *, force: bool = False) -> bool:
    if not getattr(exam, "is_active", False):
        return False
    if not getattr(exam, "ai_difficulty_balance_enabled", False):
        return False

    from core.tasks import defer

    defer(warm_ai_question_difficulties_for_exam, exam_pk=exam.pk, force=force)
    return True
