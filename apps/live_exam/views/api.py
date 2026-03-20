"""
live_exam/views/api.py
───────────────────────
API endpoints for live exam sessions.
"""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext

from apps.live_exam.auth import get_request_player
from apps.live_exam.domain.session import (
    build_question_phase_times,
    detect_multi,
    get_question_by_index,
    get_total_questions,
)
from apps.live_exam.models import LiveSession
from apps.live_exam.serializers import (
    serialize_player_question_result,
    serialize_players,
    serialize_question,
    serialize_top,
    serialize_top_before_question,
)
from apps.live_exam.session_settings import get_session_settings
from apps.live_exam.transport import build_reveal_payload
from core.rate_limit import record_rate_limit_hit
from core.utils import get_client_ip

LIVE_STATE_LIMIT_SCOPE = "live_exam.state"
LIVE_STATE_RATE_LIMIT_MESSAGE = "Çox sayda sorğu göndərildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."


# ════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ════════════════════════════════════════════════════════════════════════════


def live_state_json(request, pin):
    """
    ✅ NEW: cari state-i HTTP ilə almaq (late join / miss olunan WS üçün)
    """
    if getattr(request.user, "is_authenticated", False):
        rate_key = ("host", request.user.id, pin)
    else:
        rate_key = ("player", request.COOKIES.get("live_client_id") or get_client_ip(request) or "unknown", pin)

    is_limited, retry_after = record_rate_limit_hit(
        LIVE_STATE_LIMIT_SCOPE,
        settings.LIVE_STATE_RATE_LIMIT,
        *rate_key,
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": LIVE_STATE_RATE_LIMIT_MESSAGE},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    session = get_object_or_404(LiveSession, pin=pin)
    is_host = bool(getattr(request.user, "is_authenticated", False) and session.host_user_id == request.user.id)
    player = None if is_host else get_request_player(request, pin=pin)
    if not is_host and player is None:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
            status=403,
        )

    total = get_total_questions(session)

    data: dict = {
        "ok": True,
        "pin": session.pin,
        "state": session.state,
        "is_locked": bool(session.is_locked),
        "settings": get_session_settings(session),
        "current_index": int(session.current_index or 0),
        "total_questions": total,
        "question_started_at": (session.question_started_at.isoformat() if session.question_started_at else None),
        "question_ends_at": (session.question_ends_at.isoformat() if session.question_ends_at else None),
    }
    if session.state == LiveSession.STATE_LOBBY:
        # Fetch player list once and derive the count from it to avoid a separate COUNT query.
        players = serialize_players(session)
        data["players"] = players
        data["total_players"] = len(players)
    else:
        data["total_players"] = session.players.count()
    if session.state == LiveSession.STATE_FINISHED:
        data["top"] = serialize_top(session, limit=50)
        return JsonResponse(data)

    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if (
        not eq
        or session.state not in {LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL}
        or not session.question_started_at
    ):
        return JsonResponse(data)

    started = session.question_started_at
    ready_ends_at, answer_starts_at, computed_ends_at = build_question_phase_times(
        session,
        eq,
        started_at=started,
        idx=idx,
    )
    ends = session.question_ends_at or computed_ends_at

    _, _, correct_ids = detect_multi(eq)
    question = serialize_question(
        session,
        eq,
        idx=idx,
        total=total,
        started_at=started,
        ready_ends_at=ready_ends_at,
        answer_starts_at=answer_starts_at,
        ends_at=ends,
    )

    data["question"] = question
    data["answered_count"] = session.answers.filter(question_id=eq.id).values("player_id").distinct().count()
    data["previous_top"] = serialize_top_before_question(session, eq.id, limit=10)
    if player is not None:
        data["player_answer"] = serialize_player_question_result(session, eq.id, player.id)

    data["correct_option_ids"] = correct_ids if session.state == LiveSession.STATE_REVEAL else []
    if session.state == LiveSession.STATE_REVEAL:
        reveal_payload = build_reveal_payload(session, eq.id, revealed_at=ends)
        data["results"] = reveal_payload["results"]
        data["top"] = reveal_payload["top"]
        data["previous_top"] = reveal_payload["previous_top"]
        data["distribution"] = reveal_payload["distribution"]
        data["revealed_at"] = reveal_payload["revealed_at"]
        data["result_duration_ms"] = reveal_payload["result_duration_ms"]
        data["leaderboard_duration_ms"] = reveal_payload["leaderboard_duration_ms"]
        data["transition_duration_ms"] = reveal_payload["transition_duration_ms"]
        data["leaderboard_starts_at"] = reveal_payload["leaderboard_starts_at"]
        data["next_question_at"] = reveal_payload["next_question_at"]

    return JsonResponse(data)
