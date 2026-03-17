"""
Session and question domain helpers for live exams.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils.dateparse import parse_datetime

from apps.exams.models import ExamQuestion
from apps.live_exam.constants import (
    PLAYER_GET_READY_SECONDS,
    PLAYER_LEADERBOARD_SECONDS,
    PLAYER_QUESTION_INTRO_SECONDS,
    PLAYER_RESULT_SECONDS,
)
from apps.live_exam.models import LiveSession

QUESTION_PHASE_OVERRIDE_KEY = "_question_phase_override"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def get_selected_question_ids(session: LiveSession) -> list[int]:
    ids = getattr(session, "selected_question_ids", None) or []
    selected: list[int] = []
    for value in ids:
        try:
            selected.append(int(value))
        except Exception:
            continue
    return selected


def get_exam_question_ids(session: LiveSession) -> list[int]:
    return list(ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id").values_list("id", flat=True))


def get_total_questions(session: LiveSession) -> int:
    selected = get_selected_question_ids(session)
    if selected:
        return len(selected)
    return ExamQuestion.objects.filter(exam=session.exam).count()


def get_question_by_index(session: LiveSession, index: int) -> ExamQuestion | None:
    index = safe_int(index, 0)
    if index < 0:
        return None

    selected = get_selected_question_ids(session)
    if selected:
        if index >= len(selected):
            return None
        return ExamQuestion.objects.filter(exam=session.exam, id=selected[index]).prefetch_related("options").first()

    questions = ExamQuestion.objects.filter(exam=session.exam).prefetch_related("options").order_by("order", "id")
    try:
        return questions[index]
    except Exception:
        return None


def get_current_exam_question(session: LiveSession) -> ExamQuestion | None:
    return get_question_by_index(session, safe_int(session.current_index, 0))


def get_active_question(session: LiveSession) -> ExamQuestion | None:
    current_question_id = getattr(session, "current_question_id", None)
    if current_question_id:
        return (
            ExamQuestion.objects.filter(id=current_question_id, exam_id=session.exam_id)
            .prefetch_related("options")
            .first()
        )
    return get_current_exam_question(session)


def get_question_phase_override(session: LiveSession, *, question_id: int | None = None) -> dict[str, Any] | None:
    raw = getattr(session, "host_settings", None) or {}
    if not isinstance(raw, dict):
        return None

    override = raw.get(QUESTION_PHASE_OVERRIDE_KEY)
    if not isinstance(override, dict):
        return None

    active_question_id = safe_int(question_id if question_id is not None else getattr(session, "current_question_id", 0), 0)
    override_question_id = safe_int(override.get("question_id"), 0)
    if active_question_id <= 0 or override_question_id != active_question_id:
        return None

    answer_starts_at = parse_datetime(str(override.get("answer_starts_at") or "")) if override.get("answer_starts_at") else None
    ends_at = parse_datetime(str(override.get("ends_at") or "")) if override.get("ends_at") else None
    ready_ends_at = parse_datetime(str(override.get("ready_ends_at") or "")) if override.get("ready_ends_at") else None
    if answer_starts_at is None or ends_at is None:
        return None

    return {
        "question_id": override_question_id,
        "ready_ends_at": ready_ends_at or answer_starts_at,
        "answer_starts_at": answer_starts_at,
        "ends_at": ends_at,
    }


def set_question_phase_override(
    session: LiveSession,
    *,
    question_id: int,
    ready_ends_at,
    answer_starts_at,
    ends_at,
) -> None:
    raw = dict(getattr(session, "host_settings", None) or {})
    raw[QUESTION_PHASE_OVERRIDE_KEY] = {
        "question_id": safe_int(question_id, 0),
        "ready_ends_at": ready_ends_at.isoformat() if ready_ends_at else None,
        "answer_starts_at": answer_starts_at.isoformat() if answer_starts_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
    }
    session.host_settings = raw


def clear_question_phase_override(session: LiveSession) -> bool:
    raw = getattr(session, "host_settings", None) or {}
    if not isinstance(raw, dict) or QUESTION_PHASE_OVERRIDE_KEY not in raw:
        return False

    updated = dict(raw)
    updated.pop(QUESTION_PHASE_OVERRIDE_KEY, None)
    session.host_settings = updated
    return True


def question_time_limit(session: LiveSession, exam_question: ExamQuestion) -> int:
    if hasattr(exam_question, "effective_time_limit"):
        value = safe_int(getattr(exam_question, "effective_time_limit", 0), 0)
        if value > 0:
            return value

    value = safe_int(getattr(exam_question, "time_limit_seconds", 0), 0)
    if value > 0:
        return value

    value = safe_int(getattr(session.exam, "default_question_time_seconds", 0), 0)
    if value > 0:
        return value

    return 15


def question_intro_seconds(session: LiveSession, exam_question: ExamQuestion | None = None) -> float:
    return float(PLAYER_QUESTION_INTRO_SECONDS)


def question_get_ready_seconds(session: LiveSession, *, idx: int) -> float:
    return float(PLAYER_GET_READY_SECONDS if safe_int(idx, 0) == 0 else 0)


def result_phase_seconds(session: LiveSession | None = None) -> float:
    return float(PLAYER_RESULT_SECONDS)


def leaderboard_phase_seconds(session: LiveSession | None = None) -> float:
    return float(PLAYER_LEADERBOARD_SECONDS)


def build_question_phase_times(
    session: LiveSession,
    exam_question: ExamQuestion,
    *,
    started_at,
    idx: int,
):
    ready_ends_at = started_at + timedelta(seconds=question_get_ready_seconds(session, idx=idx))
    answer_starts_at = ready_ends_at + timedelta(seconds=question_intro_seconds(session, exam_question))
    ends_at = answer_starts_at + timedelta(seconds=question_time_limit(session, exam_question))

    override = get_question_phase_override(session, question_id=getattr(exam_question, "id", None))
    if override:
        ready_ends_at = override["ready_ends_at"]
        answer_starts_at = override["answer_starts_at"]
        ends_at = override["ends_at"]

    return ready_ends_at, answer_starts_at, ends_at


def build_reveal_phase_times(session: LiveSession, *, revealed_at):
    result_ends_at = revealed_at + timedelta(seconds=result_phase_seconds(session))
    leaderboard_ends_at = result_ends_at + timedelta(seconds=leaderboard_phase_seconds(session))
    return result_ends_at, leaderboard_ends_at


def question_points(session: LiveSession, exam_question: ExamQuestion) -> int:
    value = safe_int(getattr(exam_question, "points", 0), 0)
    if value > 0:
        return value

    value = safe_int(getattr(session.exam, "default_question_points", 0), 0)
    if value > 0:
        return value

    return 1


def get_question_text(exam_question: ExamQuestion) -> str:
    for attr in ("text", "question_text", "title", "body"):
        value = getattr(exam_question, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_option_text(option: Any) -> str:
    for attr in ("text", "title", "content", "answer", "option_text", "body"):
        value = getattr(option, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_option_label(option: Any) -> str:
    value = getattr(option, "label", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def detect_multi(exam_question: ExamQuestion) -> tuple[bool, int, list[int]]:
    # Use the options relation manager so callers that call prefetch_related("options")
    # avoid an extra round-trip to the database.
    correct_ids = [opt.id for opt in exam_question.options.all() if opt.is_correct]
    correct_count = len(correct_ids)

    flags = [
        bool(getattr(exam_question, "is_multiple", False)),
        bool(getattr(exam_question, "multi_choice", False)),
        bool(getattr(exam_question, "allow_multiple", False)),
    ]
    is_multi = any(flags) or (correct_count > 1)

    if is_multi:
        max_select = safe_int(getattr(exam_question, "max_select", 0), 0)
        if max_select <= 1:
            max_select = max(2, correct_count)
    else:
        max_select = 1

    return is_multi, max_select, correct_ids
