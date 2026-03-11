"""
live_exam/views/api.py
───────────────────────
API endpoints for live exam sessions.
"""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import pgettext

from apps.live_exam.auth import get_request_player
from apps.live_exam.domain.session import detect_multi, get_question_by_index, get_total_questions, question_time_limit
from apps.live_exam.models import LiveSession
from apps.live_exam.serializers import serialize_question, serialize_question_results, serialize_top
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
    if not is_host and get_request_player(request, pin=pin) is None:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
            status=403,
        )

    total = get_total_questions(session)

    data = {
        "ok": True,
        "pin": session.pin,
        "state": session.state,
        "current_index": int(session.current_index or 0),
        "total_questions": total,
        "question_started_at": (session.question_started_at.isoformat() if session.question_started_at else None),
        "question_ends_at": (session.question_ends_at.isoformat() if session.question_ends_at else None),
    }
    if session.state == LiveSession.STATE_FINISHED:
        data["top"] = serialize_top(session, limit=50)
        return JsonResponse(data)

    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if not eq or session.state not in {LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL} or not session.question_started_at:
        return JsonResponse(data)

    # ✅ started/ends session-dan gəlməlidir (refresh-də dəyişməsin)
    started = session.question_started_at
    ends = session.question_ends_at

    # fallback: əgər started var, ends yoxdursa -> time_limit ilə hesabla
    time_limit = question_time_limit(session, eq)
    if started and not ends:
        ends = started + timezone.timedelta(seconds=time_limit)

    _, _, correct_ids = detect_multi(eq)
    question = serialize_question(session, eq, idx=idx, total=total, started_at=started, ends_at=ends)

    data["question"] = question

    # reveal-də correct ids lazımdır
    data["correct_option_ids"] = correct_ids if session.state == LiveSession.STATE_REVEAL else []
    if session.state == LiveSession.STATE_REVEAL:
        data["results"] = serialize_question_results(session, eq.id, limit=50)
        data["top"] = serialize_top(session, limit=10)

    return JsonResponse(data)
