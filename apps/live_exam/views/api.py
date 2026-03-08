"""
live_exam/views/api.py
───────────────────────
API endpoints for live exam sessions.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.live_exam.models import LiveSession

from ._helpers import (
    _build_options,
    _detect_multi,
    _get_question_by_index,
    _get_question_text,
    _get_total_questions,
    _options_seed,
    _question_points,
    _question_time_limit,
    _safe_int,
)


# ════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ════════════════════════════════════════════════════════════════════════════


def live_state_json(request, pin):
    """
    ✅ NEW: cari state-i HTTP ilə almaq (late join / miss olunan WS üçün)
    """
    session = get_object_or_404(LiveSession, pin=pin)
    total = _get_total_questions(session)

    data = {
        "ok": True,
        "pin": session.pin,
        "state": session.state,
        "current_index": int(session.current_index or 0),
        "total_questions": total,
        "question_started_at": (session.question_started_at.isoformat() if session.question_started_at else None),
        "question_ends_at": (session.question_ends_at.isoformat() if session.question_ends_at else None),
    }

    idx = int(session.current_index or 0)
    eq = _get_question_by_index(session, idx)
    if not eq:
        return JsonResponse(data)

    # ✅ started/ends session-dan gəlməlidir (refresh-də dəyişməsin)
    started = session.question_started_at
    ends = session.question_ends_at

    # fallback: əgər started var, ends yoxdursa -> time_limit ilə hesabla
    time_limit = _question_time_limit(session, eq)
    if started and not ends:
        ends = started + timezone.timedelta(seconds=time_limit)

    multi, max_select, correct_ids = _detect_multi(eq)

    # ✅ deterministik shuffle seed (refresh-də eyni olsun)
    seed = _options_seed(session.pin, eq.id, started) if started else None

    question = {
        "id": eq.id,
        "text": _get_question_text(eq),
        "time_limit": time_limit,
        "points": _question_points(session, eq),
        "multi": multi,
        "max_select": max_select,
        "options": _build_options(eq, seed=seed),  # ✅ eyni sıra
        "started_at": started.isoformat() if started else None,
        "ends_at": ends.isoformat() if ends else None,
        "index": idx + 1,
        "total": total,
    }

    data["question"] = question

    # reveal-də correct ids lazımdır
    data["correct_option_ids"] = correct_ids if session.state == LiveSession.STATE_REVEAL else []

    return JsonResponse(data)
