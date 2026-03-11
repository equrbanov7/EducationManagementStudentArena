"""
Session and question domain helpers for live exams.
"""

from __future__ import annotations

from typing import Any

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.models import LiveSession


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
        return ExamQuestion.objects.filter(exam=session.exam, id=selected[index]).first()

    questions = ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id")
    try:
        return questions[index]
    except Exception:
        return None


def get_current_exam_question(session: LiveSession) -> ExamQuestion | None:
    return get_question_by_index(session, safe_int(session.current_index, 0))


def get_active_question(session: LiveSession) -> ExamQuestion | None:
    current_question_id = getattr(session, "current_question_id", None)
    if current_question_id:
        return ExamQuestion.objects.filter(id=current_question_id, exam_id=session.exam_id).first()
    return get_current_exam_question(session)


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
    correct_ids = list(
        ExamQuestionOption.objects.filter(question=exam_question, is_correct=True).values_list("id", flat=True)
    )
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
