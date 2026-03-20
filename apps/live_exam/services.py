"""
Business logic layer for live_exam app.

This module contains service functions that encapsulate the core business
operations for live exam sessions.  Views should call these functions rather
than embedding complex orchestration logic directly.

Public API
----------
create_live_session   – create a new lobby-state session for an exam
start_game            – initialise question order and transition to STATE_QUESTION
advance_to_next       – move from reveal to the next question (or finish)
reveal_current        – transition to reveal state for the active question
finish_session        – mark a session as finished
toggle_session_lock   – toggle (or explicitly set) the session lock flag
remove_player         – remove a player from the lobby
"""

from __future__ import annotations

import random

from django.utils import timezone

from apps.live_exam.domain.session import (
    clear_question_phase_override,
    get_exam_question_ids,
    get_question_by_index,
    get_total_questions,
)
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.session_settings import get_session_settings
from apps.live_exam.transport import (
    broadcast,
    broadcast_host,
    broadcast_play,
    broadcast_players,
    build_finished_payload,
    build_lobby_state_payload,
    build_player_reveal_payload,
    build_question_payload,
    build_reveal_payload,
)


# ──────────────────────────────────────────────────────────────────────────────
# Session lifecycle
# ──────────────────────────────────────────────────────────────────────────────


def create_live_session(exam, host_user) -> LiveSession:
    """Create a new LiveSession in STATE_LOBBY for *exam* hosted by *host_user*."""
    return LiveSession.objects.create(exam=exam, host_user=host_user)


def start_game(session: LiveSession, *, question_count: int | None = None) -> dict:
    """
    Initialise question order and transition the session to STATE_QUESTION.

    Parameters
    ----------
    session:
        An already-created LiveSession in STATE_LOBBY.
    question_count:
        How many questions to include.  ``None`` means all questions.

    Returns
    -------
    dict with keys ``ok``, ``question_count``, ``total_in_exam``.

    Raises
    ------
    ValueError
        If there are no questions, or *question_count* is out of range.
    """
    all_ids = get_exam_question_ids(session)
    total_in_exam = len(all_ids)

    if total_in_exam <= 0:
        raise ValueError("no_questions_in_exam")

    if question_count is not None:
        if question_count <= 0:
            raise ValueError("question_count_minimum")
        if question_count > total_in_exam:
            raise ValueError("question_count_exceeds_total")

    settings = get_session_settings(session)
    randomize_questions = bool(settings.get("randomize_questions", True))

    selected_ids = list(all_ids)
    if randomize_questions:
        random.shuffle(selected_ids)

    if question_count is not None:
        selected_ids = selected_ids[:question_count]

    session.selected_question_ids = selected_ids
    session.question_limit = len(selected_ids)
    session.current_index = 0
    session.current_question_id = None
    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = None
    session.question_ends_at = None
    clear_question_phase_override(session)

    session.save(
        update_fields=[
            "selected_question_ids",
            "question_limit",
            "current_index",
            "current_question_id",
            "state",
            "question_started_at",
            "question_ends_at",
            "host_settings",
        ]
    )

    # Redirect lobby players to the player screen
    from django.urls import reverse

    broadcast(
        session.pin,
        {
            "type": "game_started",
            "redirect": reverse("liveExam:player_screen", kwargs={"pin": session.pin}),
        },
        "lobby",
    )

    # Publish the first question immediately
    eq = get_question_by_index(session, 0)
    if eq is None:
        raise ValueError("question_not_found")

    total = get_total_questions(session)
    payload, now, ends = build_question_payload(session, eq, idx=0, total=total)

    session.current_question_id = eq.id
    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["current_question_id", "question_started_at", "question_ends_at"])

    broadcast_play(session.pin, payload)

    return {
        "ok": True,
        "question_count": len(selected_ids),
        "total_in_exam": total_in_exam,
    }


def advance_to_next(session: LiveSession) -> dict:
    """
    Move the session from reveal state to the next question, or finish if done.

    Returns
    -------
    dict with keys ``ok``, ``finished`` (bool), and optionally ``index`` / ``total``.
    """
    if session.state == LiveSession.STATE_REVEAL:
        session.current_index = int(session.current_index or 0) + 1

    idx = int(session.current_index or 0)
    total = get_total_questions(session)

    eq = get_question_by_index(session, idx)
    if eq is None:
        session.state = LiveSession.STATE_FINISHED
        session.current_question_id = None
        session.save(update_fields=["state", "current_question_id"])

        broadcast_play(session.pin, build_finished_payload(session, limit=50))
        return {"ok": True, "finished": True}

    payload, now, ends = build_question_payload(session, eq, idx=idx, total=total)

    session.state = LiveSession.STATE_QUESTION
    session.current_question_id = eq.id
    session.question_started_at = now
    session.question_ends_at = ends
    clear_question_phase_override(session)

    session.save(
        update_fields=[
            "state",
            "current_index",
            "current_question_id",
            "question_started_at",
            "question_ends_at",
            "host_settings",
        ]
    )

    broadcast_play(session.pin, payload)
    return {"ok": True, "finished": False, "index": idx + 1, "total": total}


def reveal_current(session: LiveSession) -> dict:
    """
    Transition the active question to reveal state and broadcast payloads.

    Returns
    -------
    dict with keys ``ok`` and ``question_id``.
    """
    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if eq is None:
        raise ValueError("active_question_not_found")

    revealed_at = timezone.now()
    session.state = LiveSession.STATE_REVEAL
    session.question_ends_at = revealed_at
    clear_question_phase_override(session)
    session.save(update_fields=["state", "question_ends_at", "host_settings"])

    broadcast_host(session.pin, build_reveal_payload(session, eq.id, revealed_at=revealed_at))
    broadcast_players(session.pin, build_player_reveal_payload(session, eq.id, revealed_at=revealed_at))

    return {"ok": True, "question_id": eq.id}


def finish_session(session: LiveSession) -> None:
    """Mark the session as finished and broadcast the final leaderboard."""
    session.state = LiveSession.STATE_FINISHED
    session.current_question_id = None
    clear_question_phase_override(session)
    session.save(update_fields=["state", "current_question_id", "host_settings"])

    payload = build_finished_payload(session, finished_at=timezone.now(), limit=50)
    broadcast_play(session.pin, payload)


def toggle_session_lock(session: LiveSession, *, locked: bool | None = None) -> bool:
    """
    Toggle (or explicitly set) the session lock.

    Parameters
    ----------
    locked:
        ``True`` / ``False`` to set explicitly; ``None`` to toggle.

    Returns
    -------
    The new lock state (bool).
    """
    if locked is None:
        locked = not session.is_locked

    session.is_locked = locked
    session.save(update_fields=["is_locked"])

    broadcast(session.pin, build_lobby_state_payload(session), "lobby")
    return locked


def remove_player(session: LiveSession, player_id: int) -> bool:
    """
    Remove a player from the lobby by ID.

    Returns ``True`` if removed, ``False`` if not found.

    Raises
    ------
    ValueError
        If the session is not in STATE_LOBBY.
    """
    if session.state != LiveSession.STATE_LOBBY:
        raise ValueError("players_can_only_be_removed_in_lobby")

    player = LivePlayer.objects.filter(session=session, id=player_id).first()
    if player is None:
        return False

    player.delete()
    broadcast(session.pin, build_lobby_state_payload(session), "lobby")
    return True
