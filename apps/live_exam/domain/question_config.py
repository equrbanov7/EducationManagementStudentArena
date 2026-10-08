"""
Bir sualın canlı oyun konfiqurasiyası (cavab növü, multi, bal rejimi, qəbul cavablar).

Konfiqurasiya sual NƏŞR olunanda ``host_settings["_question_config"]``-da
DONDURULUR (Audit 2026-09-28 LX-BE): müəllim oyun gedərkən yazılı cavab / multi
bal ayarlarını dəyişsə belə aktiv sualın qaydası dəyişmir — raund daxilində bütün
oyunçular eyni qayda ilə qiymətləndirilir. Dondurulmuş snapshot yoxdursa (köhnə
sessiya, testlər) canlı ayarlardan hesablanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.live_exam.domain.session import configured_time_limit, safe_int, selection_limits
from apps.live_exam.session_settings import (
    MULTI_SCORING_KEYS,
    MULTI_SCORING_PARTIAL,
    normalize_session_settings,
)
from apps.live_exam.typed_answers import TEXT_MAX_LENGTH, dedupe_accepted, typed_eligibility

ANSWER_INPUT_CHOICE = "choice"
ANSWER_INPUT_TEXT = "text"
QUESTION_CONFIG_KEY = "_question_config"


@dataclass(frozen=True)
class QuestionConfig:
    question_id: int
    answer_input: str
    is_multi: bool
    max_select: int
    correct_ids: tuple[int, ...]
    accepted: tuple[str, ...]
    typo_tolerance: bool
    multi_scoring: str

    @property
    def is_text(self) -> bool:
        return self.answer_input == ANSWER_INPUT_TEXT

    @property
    def is_neutral(self) -> bool:
        """Düzgün variantı olmayan choice sualı — heç kim düz ola bilməz (seriyaya təsirsiz)."""
        return not self.is_text and not self.correct_ids

    def to_payload_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {"answer_input": self.answer_input}
        if self.is_text:
            fields["text_max_length"] = TEXT_MAX_LENGTH
        return fields


def _frozen_snapshot(session, question_id: int) -> dict[str, Any] | None:
    raw = getattr(session, "host_settings", None) or {}
    snapshot = raw.get(QUESTION_CONFIG_KEY) if isinstance(raw, dict) else None
    if not isinstance(snapshot, dict) or safe_int(snapshot.get("question_id"), 0) != int(question_id):
        return None
    return snapshot


def _live_rules(session, exam_question) -> dict[str, Any]:
    settings = normalize_session_settings(getattr(session, "host_settings", None) or {})
    typed_entry = (settings.get("typed_questions") or {}).get(str(exam_question.id))
    answer_input = ANSWER_INPUT_CHOICE
    accepted: list[str] = []
    if typed_entry is not None:
        eligible, defaults = typed_eligibility(exam_question)
        if eligible:
            answer_input = ANSWER_INPUT_TEXT
            accepted = dedupe_accepted(typed_entry.get("accepted") or []) or defaults
    return {
        "answer_input": answer_input,
        "accepted": accepted,
        "typo_tolerance": bool(settings.get("typed_typo_tolerance", True)),
        "multi_scoring": settings.get("multi_scoring") or MULTI_SCORING_PARTIAL,
    }


def resolve_question_config(session, exam_question) -> QuestionConfig:
    """Sualın effektiv qaydası (dondurulmuş snapshot → canlı ayarlar)."""
    rules = _frozen_snapshot(session, exam_question.id) or _live_rules(session, exam_question)
    correct_ids = tuple(option.id for option in exam_question.options.all() if option.is_correct)
    answer_input = rules.get("answer_input")
    if answer_input != ANSWER_INPUT_TEXT:
        answer_input = ANSWER_INPUT_CHOICE
    multi_scoring = rules.get("multi_scoring")
    if multi_scoring not in MULTI_SCORING_KEYS:
        multi_scoring = MULTI_SCORING_PARTIAL
    if answer_input == ANSWER_INPUT_TEXT:
        is_multi, max_select = False, 1
    else:
        is_multi, max_select = selection_limits(exam_question, len(correct_ids))
    return QuestionConfig(
        question_id=int(exam_question.id),
        answer_input=answer_input,
        is_multi=is_multi,
        max_select=max_select,
        correct_ids=correct_ids,
        accepted=tuple(str(value) for value in (rules.get("accepted") or []) if str(value).strip()),
        typo_tolerance=bool(rules.get("typo_tolerance", True)),
        multi_scoring=multi_scoring,
    )


def freeze_question_config(session, exam_question) -> None:
    """Nəşr anında aktiv sualın qaydasını ``host_settings``-ə yazır (save çağıran edir)."""
    rules = _live_rules(session, exam_question)
    # 2026-10-08 (L2): sualın vaxtı da dondurulur — aparıcı vaxtı sual gedərkən dəyişsə
    # cari raundun pəncərəsi/«time_limit»-i dəyişmir, yeni dəyər növbəti sualdan keçərlidir.
    rules["time_limit"] = configured_time_limit(session, exam_question)
    raw = dict(getattr(session, "host_settings", None) or {})
    raw[QUESTION_CONFIG_KEY] = {"question_id": int(exam_question.id), **rules}
    session.host_settings = raw
