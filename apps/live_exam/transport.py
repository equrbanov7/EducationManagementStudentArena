"""
Transport helpers for live exam HTTP and websocket payloads.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import async_to_sync
from channels.exceptions import InvalidChannelLayerError
from channels.layers import get_channel_layer

from apps.live_exam.domain.session import question_time_limit
from apps.live_exam.serializers import serialize_players, serialize_question, serialize_question_results, serialize_top


def get_public_base_url(request) -> str:
    configured = (
        getattr(settings, "LIVE_EXAM_PUBLIC_HOST", None) or getattr(settings, "LAN_HOST", None) or ""
    ).strip()

    if configured:
        configured = configured.rstrip("/")
        if configured.startswith(("http://", "https://")):
            return configured
        scheme = "https" if request.is_secure() else "http"
        return f"{scheme}://{configured}"

    return request.build_absolute_uri("/").rstrip("/")


def build_join_url(request, session) -> str:
    return f"{get_public_base_url(request)}{session.join_url_path()}"


def broadcast(pin: str, payload: dict[str, Any], group_suffix: str) -> None:
    try:
        layer = get_channel_layer()
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return
    if layer is None:
        return

    event_type = "play_event" if group_suffix == "play" else "lobby_event"
    try:
        async_to_sync(layer.group_send)(
            f"live_{pin}_{group_suffix}",
            {"type": event_type, "data": payload},
        )
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return


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


def build_lobby_state_payload(session, *, limit: int = 50) -> dict[str, Any]:
    return {
        "type": "lobby_state",
        "count": session.players.count(),
        "players": serialize_players(session, limit=limit),
    }


def build_answer_progress_payload(*, question_id: int, answered_count: int, total_players: int) -> dict[str, Any]:
    return {
        "type": "answer_progress",
        "question_id": question_id,
        "answered_count": answered_count,
        "total_players": total_players,
    }


def build_question_payload(session, exam_question, *, idx: int, total: int):
    started_at = timezone.now()
    ends_at = started_at + timezone.timedelta(seconds=question_time_limit(session, exam_question))
    payload = {
        "type": "question_published",
        "question": serialize_question(
            session,
            exam_question,
            idx=idx,
            total=total,
            started_at=started_at,
            ends_at=ends_at,
        ),
    }
    return payload, started_at, ends_at


def build_reveal_payload(session, question_id: int, *, revealed_at=None) -> dict[str, Any]:
    from apps.exams.models import ExamQuestion
    from apps.live_exam.domain.session import detect_multi

    exam_question = ExamQuestion.objects.filter(exam=session.exam, id=question_id).first()
    if not exam_question:
        return {"type": "error", "message": pgettext("live_exam.view.message", "question_not_found")}

    _, _, correct_ids = detect_multi(exam_question)
    payload = {
        "type": "reveal",
        "question_id": question_id,
        "correct_option_ids": correct_ids,
        "results": serialize_question_results(session, question_id, limit=50),
        "top": serialize_top(session, limit=10),
    }
    if revealed_at is not None:
        payload["revealed_at"] = revealed_at.isoformat()
    return payload


def build_finished_payload(session, *, finished_at=None, limit: int = 50) -> dict[str, Any]:
    payload = {
        "type": "finished",
        "top": serialize_top(session, limit=limit),
    }
    if finished_at is not None:
        payload["finished_at"] = finished_at.isoformat()
    return payload
