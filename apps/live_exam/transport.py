"""
Transport helpers for live exam HTTP and websocket payloads.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import async_to_sync
from channels.exceptions import InvalidChannelLayerError
from channels.layers import get_channel_layer

from apps.live_exam.constants import PLAYER_LEADERBOARD_SECONDS, PLAYER_RESULT_SECONDS, PLAYER_REVEAL_TRANSITION_SECONDS
from apps.live_exam.domain.session import build_question_phase_times, build_reveal_phase_times
from apps.live_exam.serializers import (
    serialize_answer_distribution,
    serialize_player_identity,
    serialize_players,
    serialize_question,
    serialize_question_results,
    serialize_top,
    serialize_top_before_question,
)
from apps.live_exam.session_settings import get_session_settings, session_join_path


def get_public_base_url(request) -> str:
    configured = (getattr(settings, "LIVE_EXAM_PUBLIC_HOST", None) or getattr(settings, "LAN_HOST", None) or "").strip()

    if configured:
        configured = configured.rstrip("/")
        if configured.startswith(("http://", "https://")):
            return configured
        scheme = "https" if request.is_secure() else "http"
        return f"{scheme}://{configured}"

    return request.build_absolute_uri("/").rstrip("/")


def build_join_url(request, session) -> str:
    base_url = f"{get_public_base_url(request)}{session_join_path(session)}"
    if get_session_settings(session).get("two_step_join", True):
        return f"{base_url}?{urlencode({'pin': session.pin})}"
    return base_url


def broadcast(pin: str, payload: dict[str, Any], group_suffix: str) -> None:
    """Broadcast a payload to a specific channel-layer group.

    group_suffix can be:
      - "lobby"           → live_<pin>_lobby  (lobby_event)
      - "play_host"       → live_<pin>_play_host  (play_event, host only)
      - "play_players"    → live_<pin>_play_players  (play_event, players only)
    """
    try:
        layer = get_channel_layer()
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return
    if layer is None:
        return

    event_type = "lobby_event" if group_suffix == "lobby" else "play_event"
    try:
        async_to_sync(layer.group_send)(
            f"live_{pin}_{group_suffix}",
            {"type": event_type, "data": payload},
        )
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return


def broadcast_host(pin: str, payload: dict[str, Any]) -> None:
    """Broadcast a payload to the host-only play group."""
    broadcast(pin, payload, "play_host")


def broadcast_players(pin: str, payload: dict[str, Any]) -> None:
    """Broadcast a payload to the players-only play group."""
    broadcast(pin, payload, "play_players")


def broadcast_play(pin: str, payload: dict[str, Any]) -> None:
    """Broadcast a payload to both host and player play groups."""
    broadcast_host(pin, payload)
    broadcast_players(pin, payload)


def parse_answer_submission(data: dict[str, Any]) -> tuple[bool, Any]:
    try:
        question_id = int(data.get("question_id"))
        answer_ms = int(data.get("answer_ms") or 0)

        if isinstance(data.get("option_ids"), list):
            option_ids = [int(value) for value in data.get("option_ids") if str(value).isdigit()]
        else:
            option_ids = [int(data.get("option_id"))]

        option_ids = list(dict.fromkeys(option_ids))
        if not option_ids:
            return False, pgettext("live_exam.consumer.error", "no_options_selected")

        return True, (question_id, option_ids, answer_ms)
    except Exception:
        return False, pgettext("live_exam.consumer.error", "bad_payload")


def build_lobby_state_payload(session, *, limit: int = 200) -> dict[str, Any]:
    players = serialize_players(session, limit=limit)
    return {
        "type": "lobby_state",
        "count": len(players),
        "players": players,
        "is_locked": bool(session.is_locked),
        "settings": get_session_settings(session),
    }


def build_reaction_event_payload(*, player, reaction_key: str, emoji: str, created_at=None) -> dict[str, Any]:
    payload = {
        "type": "reaction_event",
        "reaction_key": reaction_key,
        "emoji": emoji,
        "player": serialize_player_identity(player),
    }
    if created_at is not None:
        payload["created_at"] = created_at.isoformat()
    return payload


def build_answer_progress_payload(*, question_id: int, answered_count: int, total_players: int) -> dict[str, Any]:
    return {
        "type": "answer_progress",
        "question_id": question_id,
        "answered_count": answered_count,
        "total_players": total_players,
    }


def build_question_payload(session, exam_question, *, idx: int, total: int):
    started_at = timezone.now()
    ready_ends_at, answer_starts_at, ends_at = build_question_phase_times(
        session,
        exam_question,
        started_at=started_at,
        idx=idx,
    )
    payload = {
        "type": "question_published",
        "question": serialize_question(
            session,
            exam_question,
            idx=idx,
            total=total,
            started_at=started_at,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        ),
        "previous_top": serialize_top(session, limit=10),
    }
    return payload, started_at, ends_at


def build_question_phase_payload(
    session,
    exam_question,
    *,
    idx: int,
    total: int,
    started_at,
    ready_ends_at,
    answer_starts_at,
    ends_at,
):
    return {
        "type": "question_published",
        "question": serialize_question(
            session,
            exam_question,
            idx=idx,
            total=total,
            started_at=started_at,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        ),
        "previous_top": serialize_top_before_question(session, exam_question.id, limit=10),
    }


def build_reveal_payload(
    session,
    question_id: int,
    *,
    revealed_at=None,
    exam_question=None,
) -> dict[str, Any]:
    from apps.exams.models import ExamQuestion
    from apps.live_exam.domain.session import detect_multi

    if exam_question is None:
        exam_question = (
            ExamQuestion.objects.filter(exam=session.exam, id=question_id).prefetch_related("options").first()
        )
    if not exam_question:
        return {"type": "error", "message": pgettext("live_exam.view.message", "question_not_found")}

    revealed_at = revealed_at or session.question_ends_at or timezone.now()
    leaderboard_starts_at, next_question_at = build_reveal_phase_times(session, revealed_at=revealed_at)
    _, _, correct_ids = detect_multi(exam_question)
    payload = {
        "type": "reveal",
        "question_id": question_id,
        "correct_option_ids": correct_ids,
        "distribution": serialize_answer_distribution(session, question_id),
        "results": serialize_question_results(session, question_id, limit=50),
        "top": serialize_top(session, limit=10),
        "previous_top": serialize_top_before_question(session, question_id, limit=10),
        "revealed_at": revealed_at.isoformat(),
        "result_duration_ms": int(PLAYER_RESULT_SECONDS * 1000),
        "leaderboard_duration_ms": int(PLAYER_LEADERBOARD_SECONDS * 1000),
        "transition_duration_ms": int(PLAYER_REVEAL_TRANSITION_SECONDS * 1000),
        "leaderboard_starts_at": leaderboard_starts_at.isoformat(),
        "next_question_at": next_question_at.isoformat(),
    }
    return payload


def build_player_reveal_payload(
    session,
    question_id: int,
    *,
    revealed_at=None,
    exam_question=None,
) -> dict[str, Any]:
    """Reveal payload for players.

    Includes correct_option_ids (appropriate at reveal stage), distribution, and leaderboard
    data, but omits per-player answer details (``results``) which are host-only analytics.
    """
    from apps.exams.models import ExamQuestion
    from apps.live_exam.domain.session import detect_multi

    if exam_question is None:
        exam_question = (
            ExamQuestion.objects.filter(exam=session.exam, id=question_id).prefetch_related("options").first()
        )
    if not exam_question:
        return {"type": "error", "message": pgettext("live_exam.view.message", "question_not_found")}

    revealed_at = revealed_at or session.question_ends_at or timezone.now()
    leaderboard_starts_at, next_question_at = build_reveal_phase_times(session, revealed_at=revealed_at)
    _, _, correct_ids = detect_multi(exam_question)
    return {
        "type": "reveal",
        "question_id": question_id,
        "correct_option_ids": correct_ids,
        "distribution": serialize_answer_distribution(session, question_id),
        "top": serialize_top(session, limit=10),
        "previous_top": serialize_top_before_question(session, question_id, limit=10),
        "revealed_at": revealed_at.isoformat(),
        "result_duration_ms": int(PLAYER_RESULT_SECONDS * 1000),
        "leaderboard_duration_ms": int(PLAYER_LEADERBOARD_SECONDS * 1000),
        "transition_duration_ms": int(PLAYER_REVEAL_TRANSITION_SECONDS * 1000),
        "leaderboard_starts_at": leaderboard_starts_at.isoformat(),
        "next_question_at": next_question_at.isoformat(),
    }


def build_finished_payload(session, *, finished_at=None, limit: int = 50) -> dict[str, Any]:
    payload = {
        "type": "finished",
        "top": serialize_top(session, limit=limit),
    }
    if finished_at is not None:
        payload["finished_at"] = finished_at.isoformat()
    return payload
