"""
Scoring and answer persistence helpers for live exams.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.domain.session import build_question_phase_times, get_active_question, question_points
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.serializers import serialize_player_question_result
from core.rls import bypass_rls

# The client reports how fast it answered (`answer_ms`) for the speed bonus,
# but the value is attacker-controlled. The server clamps it against its own
# observed elapsed time, allowing only this much downward slack for network
# latency, so a tampered client cannot claim a 0 ms answer late in the window.
ANSWER_MS_LATENCY_ALLOWANCE_MS = 2500


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


def _round_awarded_points(value: float | Decimal) -> int:
    """
    Round points to the nearest integer using half-up semantics.

    `int(...)` truncates `0.5` down to `0`, which caused 1-point questions to
    award zero to correct answers answered later in the timer window.
    """
    return max(0, int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _kahoot_time_factor(*, answer_ms: int, total_ms: int) -> float:
    """
    Kahoot-style speed multiplier.

    A correct answer can earn between 100% and 50% of its base score depending
    on how quickly it was submitted during the active answer window.
    """
    if total_ms <= 0:
        return 1.0

    bounded_answer_ms = max(0, min(int(answer_ms or 0), int(total_ms)))
    progress = bounded_answer_ms / float(total_ms)
    return max(0.5, 1.0 - (progress * 0.5))


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

    bounded_answer_ms = int(answer_ms or 0)
    if total_ms > 0:
        bounded_answer_ms = max(0, min(bounded_answer_ms, total_ms))
    else:
        bounded_answer_ms = max(0, bounded_answer_ms)

    time_factor = _kahoot_time_factor(answer_ms=bounded_answer_ms, total_ms=total_ms)
    if fraction <= 0:
        awarded_points = 0
    else:
        awarded_points = _round_awarded_points(int(base_points) * fraction * time_factor)

    return {
        "is_correct": is_perfect,
        "fraction": round(float(fraction), 4),
        "time_factor": round(float(time_factor), 4),
        "picked_correct": picked_correct,
        "picked_wrong": picked_wrong,
        "correct_total": correct_total,
        "awarded_points": awarded_points,
        "base": int(base_points),
        "bonus": 0,
        "answer_ms": bounded_answer_ms,
    }


def get_answer_progress(*, pin: str, question_id: int) -> dict[str, int]:
    with bypass_rls():
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
        with bypass_rls():
            with transaction.atomic():
                # NOTE: the session row is intentionally NOT locked here. Locking it
                # serialized every answer submission in the session behind a single
                # row lock (a big bottleneck for large classes). Per-player integrity
                # is enforced by the player row lock + the unique
                # (session, player, question) constraint, and the question→reveal
                # transition uses an atomic conditional UPDATE below.
                session = LiveSession.objects.get(pin=pin)
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

                # Single query for all options: validates the submitted ids AND
                # derives the correct set without a second round-trip.
                option_rows = list(
                    ExamQuestionOption.objects.filter(question_id=question_id).values_list("id", "is_correct")
                )
                valid_option_ids = {row[0] for row in option_rows}
                correct_ids = [row[0] for row in option_rows if row[1]]
                if not correct_ids:
                    return False, pgettext("live_exam.consumer.error", "no_correct_options"), None, False

                # Reject ids that do not belong to this question: a legitimate
                # client can only submit options it was shown, so anything else
                # is a tampered payload (and would otherwise be persisted into
                # choice_ids and skew the answer distribution).
                if not option_ids or not set(int(value) for value in option_ids) <= valid_option_ids:
                    return False, pgettext("live_exam.consumer.error", "bad_payload"), None, False

                total_ms = int((session.question_ends_at - answer_starts_at).total_seconds() * 1000)

                # Anti-cheat: the speed bonus uses the client-reported answer
                # time, so enforce a server-side lower bound. A tampered client
                # claiming "0 ms" late in the window is raised to the
                # server-observed elapsed time minus a latency allowance.
                # (No upper clamp — overstating answer_ms only lowers the score.)
                server_elapsed_ms = max(0, int((received_at - answer_starts_at).total_seconds() * 1000))
                answer_ms = max(int(answer_ms or 0), server_elapsed_ms - ANSWER_MS_LATENCY_ALLOWANCE_MS)

                score = calculate_answer_score(
                    option_ids=option_ids,
                    correct_ids=correct_ids,
                    base_points=question_points(session, exam_question),
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
                if (
                    total_players > 0
                    and answered_count >= total_players
                    and session.state == LiveSession.STATE_QUESTION
                ):
                    # Atomic conditional UPDATE replaces the old session row lock:
                    # if two "last" answers race, exactly one wins the transition,
                    # so the reveal is broadcast exactly once.
                    updated = LiveSession.objects.filter(
                        pk=session.pk,
                        state=LiveSession.STATE_QUESTION,
                    ).update(state=LiveSession.STATE_REVEAL, question_ends_at=received_at)
                    if updated:
                        session.state = LiveSession.STATE_REVEAL
                        session.question_ends_at = received_at
                        reveal_question_id = question_id
    except LiveSession.DoesNotExist:
        return False, pgettext("live_exam.consumer.error", "session_not_found"), None, False
    except LivePlayer.DoesNotExist:
        return False, pgettext("live_exam.consumer.error", "player_not_found"), None, False

    with bypass_rls():
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
            # Counts were already computed inside the transaction — expose them so
            # callers don't have to re-query the same numbers for the progress
            # broadcast (saves 3 queries per answer).
            "progress": {
                "question_id": question_id,
                "answered_count": answered_count,
                "total_players": total_players,
            },
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
