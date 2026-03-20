"""
Scoring and answer persistence helpers for live exams.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.domain.session import build_question_phase_times, get_active_question
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.serializers import serialize_player_question_result


def score_multi_fraction(chosen_ids: list[int], correct_ids: list[int], *, mode: str = "strict") -> float:
    chosen = set(int(value) for value in (chosen_ids or []))
    correct = set(int(value) for value in (correct_ids or []))
    if not correct:
        return 0.0

    picked_correct = len(chosen & correct)
    picked_wrong = len(chosen - correct)
    correct_total = len(correct)

    if mode == "strict":
        if picked_wrong > 0:
            return 0.0
        return 1.0 if picked_correct == correct_total else 0.0

    return max(0.0, (picked_correct - picked_wrong) / float(correct_total))


def calculate_answer_score(
    *,
    option_ids: list[int],
    correct_ids: list[int],
    base_points: int,
    answer_ms: int,
    total_ms: int,
) -> dict[str, Any]:
    selected_set = set(int(value) for value in option_ids)
    correct_set = set(int(value) for value in correct_ids)

    picked_correct = len(selected_set & correct_set)
    picked_wrong = len(selected_set - correct_set)
    correct_total = len(correct_set)
    fraction = min(1.0, max(0.0, score_multi_fraction(option_ids, correct_ids, mode="partial")))
    is_perfect = selected_set == correct_set

    bonus = 0
    bounded_answer_ms = int(answer_ms or 0)
    if total_ms > 0:
        bounded_answer_ms = max(0, min(bounded_answer_ms, total_ms))
        remaining = total_ms - bounded_answer_ms
        bonus = int((remaining / total_ms) * 500)

    awarded_points = int((int(base_points) + bonus) * fraction)

    return {
        "is_correct": is_perfect,
        "fraction": round(float(fraction), 4),
        "picked_correct": picked_correct,
        "picked_wrong": picked_wrong,
        "correct_total": correct_total,
        "awarded_points": awarded_points,
        "base": int(base_points),
        "bonus": bonus,
        "answer_ms": bounded_answer_ms,
    }


def get_answer_progress(*, pin: str, question_id: int) -> dict[str, int]:
    session = LiveSession.objects.get(pin=pin)
    total_players = LivePlayer.objects.filter(session=session).count()
    answered_count = (
        LiveAnswer.objects.filter(session=session, question_id=question_id).values("player_id").distinct().count()
    )

    return {
        "question_id": question_id,
        "answered_count": answered_count,
        "total_players": total_players,
    }


def _save_answer_and_score_impl(
    *,
    pin: str,
    player_id: int,
    client_id: str,
    question_id: int,
    option_ids: list[int],
    answer_ms: int,
    received_at=None,
) -> tuple[bool, str | dict[str, Any], LiveAnswer | None, bool]:
    received_at = received_at or timezone.now()

    try:
        with transaction.atomic():
            session = LiveSession.objects.select_for_update().get(pin=pin)
            player = LivePlayer.objects.select_for_update().get(
                id=player_id,
                session=session,
                client_id=client_id,
            )

            exam_question = ExamQuestion.objects.filter(id=question_id, exam_id=session.exam_id).first()
            if exam_question is None:
                return False, pgettext("live_exam.consumer.error", "question_not_found"), None, False

            active_question = get_active_question(session)
            if active_question is None:
                return False, pgettext("live_exam.consumer.error", "active_question_not_found"), None, False

            if int(question_id) != int(active_question.id):
                return False, pgettext("live_exam.consumer.error", "question_not_active"), None, False

            existing_answer_obj = LiveAnswer.objects.filter(
                session=session,
                player=player,
                question_id=question_id,
            ).first()
            if existing_answer_obj is not None:
                existing_answer = serialize_player_question_result(session, question_id, player.id) or {}
                return (
                    True,
                    {
                        "answer": {
                            "message": pgettext("live_exam.consumer.error", "already_answered"),
                            "score": player.score,
                            **existing_answer,
                        },
                        "question_id": question_id,
                        "reveal_question_id": None,
                    },
                    existing_answer_obj,
                    False,
                )

            if (
                session.state != LiveSession.STATE_QUESTION
                or session.question_started_at is None
                or session.question_ends_at is None
            ):
                return False, pgettext("live_exam.consumer.error", "question_not_accepting_answers"), None, False

            question_idx = int(session.current_index or 0)
            _, answer_starts_at, _ = build_question_phase_times(
                session,
                exam_question,
                started_at=session.question_started_at,
                idx=question_idx,
            )

            if not (answer_starts_at <= received_at <= session.question_ends_at):
                return False, pgettext("live_exam.consumer.error", "submission_outside_active_window"), None, False

            correct_ids = list(
                ExamQuestionOption.objects.filter(question_id=question_id, is_correct=True).values_list("id", flat=True)
            )
            if not correct_ids:
                return False, pgettext("live_exam.consumer.error", "no_correct_options"), None, False

            total_ms = int((session.question_ends_at - answer_starts_at).total_seconds() * 1000)
            score = calculate_answer_score(
                option_ids=option_ids,
                correct_ids=correct_ids,
                base_points=int(getattr(exam_question, "points", 1000) or 1000),
                answer_ms=answer_ms,
                total_ms=total_ms,
            )

            answer = LiveAnswer.objects.create(
                session=session,
                player=player,
                question_id=question_id,
                choice_id=(option_ids[0] if option_ids else None),
                choice_ids=option_ids,
                is_correct=score["is_correct"],
                answer_ms=score["answer_ms"],
                awarded_points=score["awarded_points"],
            )

            player.score = int(player.score or 0) + int(score["awarded_points"])
            player.last_seen = received_at
            player.save(update_fields=["score", "last_seen"])

            total_players = LivePlayer.objects.filter(session=session).count()
            answered_count = (
                LiveAnswer.objects.filter(session=session, question_id=question_id)
                .values("player_id")
                .distinct()
                .count()
            )

            reveal_question_id = None
            if total_players > 0 and answered_count >= total_players and session.state == LiveSession.STATE_QUESTION:
                session.state = LiveSession.STATE_REVEAL
                session.question_ends_at = received_at
                session.save(update_fields=["state", "question_ends_at"])
                reveal_question_id = question_id
    except LiveSession.DoesNotExist:
        return False, pgettext("live_exam.consumer.error", "session_not_found"), None, False
    except LivePlayer.DoesNotExist:
        return False, pgettext("live_exam.consumer.error", "player_not_found"), None, False

    personal_result = serialize_player_question_result(session, question_id, player.id) or {}

    return (
        True,
        {
            "answer": {
                "is_correct": score["is_correct"],
                "fraction": score["fraction"],
                "picked_correct": score["picked_correct"],
                "picked_wrong": score["picked_wrong"],
                "correct_total": score["correct_total"],
                "awarded_points": score["awarded_points"],
                "base": score["base"],
                "bonus": score["bonus"],
                "score": player.score,
                **personal_result,
            },
            "question_id": question_id,
            "reveal_question_id": reveal_question_id,
        },
        answer,
        True,
    )


def _legacy_answer_ms(session: LiveSession, question: ExamQuestion, submitted_at) -> int:
    if session.question_started_at is None:
        return 0

    question_idx = int(session.current_index or 0)
    _, answer_starts_at, _ = build_question_phase_times(
        session,
        question,
        started_at=session.question_started_at,
        idx=question_idx,
    )
    return max(0, int((submitted_at - answer_starts_at).total_seconds() * 1000))


def save_answer_and_score(
    *,
    pin: str | None = None,
    player_id: int | None = None,
    client_id: str | None = None,
    question_id: int | None = None,
    option_ids: list[int] | None = None,
    answer_ms: int | None = None,
    session: LiveSession | None = None,
    player: LivePlayer | None = None,
    question: ExamQuestion | None = None,
    submitted_at=None,
):
    if session is not None or player is not None or question is not None:
        if session is None or player is None or question is None:
            raise TypeError("Legacy save_answer_and_score calls require session=, player=, and question=.")

        effective_submitted_at = submitted_at or timezone.now()
        ok, _result, answer, created = _save_answer_and_score_impl(
            pin=session.pin,
            player_id=player.id,
            client_id=str(player.client_id or ""),
            question_id=question.id,
            option_ids=list(option_ids or []),
            answer_ms=_legacy_answer_ms(session, question, effective_submitted_at),
            received_at=effective_submitted_at,
        )
        if not ok:
            return None
        return answer, created

    if pin is None or player_id is None or question_id is None:
        raise TypeError("pin=, player_id=, and question_id= are required.")

    ok, result, _answer, _created = _save_answer_and_score_impl(
        pin=pin,
        player_id=player_id,
        client_id=str(client_id or ""),
        question_id=question_id,
        option_ids=list(option_ids or []),
        answer_ms=int(answer_ms or 0),
    )
    return ok, result
