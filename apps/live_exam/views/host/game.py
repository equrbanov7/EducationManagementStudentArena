"""live_exam host paketi — game."""

import json
import random
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.utils import log_action
from apps.live_exam.domain.session import (
    build_question_phase_times,
    clear_question_phase_override,
    get_exam_question_ids,
    get_question_by_index,
    get_total_questions,
    question_time_limit,
    set_question_phase_override,
)
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.session_settings import (
    allowed_max_participants_for_user,
    get_session_settings,
    normalize_session_setting_updates,
    update_session_settings,
)
from apps.live_exam.transport import (
    broadcast,
    broadcast_host,
    broadcast_play,
    broadcast_players,
    build_finished_payload,
    build_lobby_state_payload,
    build_player_reveal_payload,
    build_question_payload,
    build_question_phase_payload,
    build_reveal_payload,
)
from core.constants import AuditAction

from ._shared import (
    _ensure_host_org_permission,
)


@require_POST
@login_required
def host_start_game(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    # ── State guard: game can only be started from LOBBY ──
    if session.state != LiveSession.STATE_LOBBY:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "game_already_started")},
            status=409,
        )

    # 1) Host neçə sual istəyir? (form input name="question_count")
    raw = (request.POST.get("question_count") or "").strip()

    all_ids = get_exam_question_ids(session)
    total_in_exam = len(all_ids)

    if total_in_exam <= 0:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "no_questions_in_exam")},
            status=400,
        )

    desired = None
    if raw:
        try:
            desired = int(raw)
        except Exception:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "invalid_question_count")},
                status=400,
            )

        if desired <= 0:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "question_count_minimum")},
                status=400,
            )

        if desired > total_in_exam:
            return JsonResponse(
                {
                    "ok": False,
                    "message": pgettext("live_exam.view.message", "question_count_exceeds_total").format(
                        total_in_exam=total_in_exam,
                        desired=desired,
                    ),
                },
                status=400,
            )

    settings = get_session_settings(session)
    randomize_questions = bool(settings.get("randomize_questions", True))

    selected_ids = list(all_ids)
    if randomize_questions:
        random.shuffle(selected_ids)

    if desired is not None:
        selected_ids = selected_ids[:desired]

    session.selected_question_ids = selected_ids
    session.question_limit = len(selected_ids)

    # 3) Oyun reset
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

    # 4) Wait room-da olan player-ları player_screen-ə yönləndir
    broadcast(
        pin,
        {
            "type": "game_started",
            "redirect": reverse("liveExam:player_screen", kwargs={"pin": pin}),
        },
        "lobby",
    )

    # 5) Start basan kimi 1-ci sualı publish et
    eq = get_question_by_index(session, 0)
    if not eq:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "question_not_found")},
            status=400,
        )

    total = get_total_questions(session)
    payload, now, ends = build_question_payload(session, eq, idx=0, total=total)

    session.current_question_id = eq.id
    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["current_question_id", "question_started_at", "question_ends_at"])

    broadcast_play(pin, payload)

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=session.exam.organization,
        obj=session,
        new_values={"state": session.state, "question_count": len(selected_ids)},
        reason="game_started",
        request=request,
    )

    return JsonResponse(
        {
            "ok": True,
            "published": True,
            "question_count": len(selected_ids),
            "total_in_exam": total_in_exam,
        }
    )


@require_POST
@login_required
def host_next_question(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    # ── State guard: next question only from QUESTION or REVEAL ──
    if session.state not in (LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL):
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_state_for_next")},
            status=409,
        )

    # Kahoot axını:
    # Reveal mərhələsindən sonra növbəti sual üçün index++ edirik
    if session.state == LiveSession.STATE_REVEAL:
        session.current_index = int(session.current_index or 0) + 1

    idx = int(session.current_index or 0)
    total = get_total_questions(session)

    eq = get_question_by_index(session, idx)
    if eq is None:
        # sual qurtardı -> finished
        session.state = LiveSession.STATE_FINISHED
        session.current_question_id = None
        clear_question_phase_override(session)
        session.save(update_fields=["state", "current_question_id", "host_settings"])

        broadcast_play(pin, build_finished_payload(session, finished_at=timezone.now(), limit=50))
        return JsonResponse({"ok": True, "finished": True})

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

    broadcast_play(pin, payload)
    return JsonResponse({"ok": True, "index": idx + 1, "total": total})


@require_POST
@login_required
def host_skip_question_intro(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    if session.state != LiveSession.STATE_QUESTION or session.question_started_at is None:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "active_question_not_found")},
            status=409,
        )

    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if not eq:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "active_question_not_found")},
            status=404,
        )

    ready_ends_at, answer_starts_at, _ = build_question_phase_times(
        session,
        eq,
        started_at=session.question_started_at,
        idx=idx,
    )
    now = timezone.now()
    if now >= answer_starts_at:
        return JsonResponse({"ok": True, "skipped": False, "already_open": True})

    ends_at = now + timedelta(seconds=question_time_limit(session, eq))
    set_question_phase_override(
        session,
        question_id=eq.id,
        ready_ends_at=now,
        answer_starts_at=now,
        ends_at=ends_at,
    )
    session.question_ends_at = ends_at
    session.save(update_fields=["host_settings", "question_ends_at"])

    total = get_total_questions(session)
    payload = build_question_phase_payload(
        session,
        eq,
        idx=idx,
        total=total,
        started_at=session.question_started_at,
        ready_ends_at=now,
        answer_starts_at=now,
        ends_at=ends_at,
    )
    broadcast_play(pin, payload)
    return JsonResponse({"ok": True, "skipped": True, "ends_at": ends_at.isoformat()})


@require_POST
@login_required
def host_reveal(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    # ── State guard: reveal only from QUESTION state ──
    if session.state != LiveSession.STATE_QUESTION:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "not_in_question_state")},
            status=409,
        )

    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if not eq:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "active_question_not_found")},
            status=400,
        )

    revealed_at = timezone.now()
    session.state = LiveSession.STATE_REVEAL
    session.question_ends_at = revealed_at
    clear_question_phase_override(session)
    session.save(update_fields=["state", "question_ends_at", "host_settings"])

    # Host receives the full reveal payload (includes per-player results for analytics)
    broadcast_host(pin, build_reveal_payload(session, eq.id, revealed_at=revealed_at))
    # Players receive a player-appropriate reveal payload (correct_option_ids visible at
    # reveal stage, but without per-player result details which are host-only)
    broadcast_players(pin, build_player_reveal_payload(session, eq.id, revealed_at=revealed_at))

    return JsonResponse({"ok": True, "question_id": eq.id})


@require_POST
@login_required
def host_finish(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    # ── State guard: cannot finish an already-finished session ──
    if session.state == LiveSession.STATE_FINISHED:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "session_already_finished")},
            status=409,
        )

    session.state = LiveSession.STATE_FINISHED
    session.current_question_id = None
    clear_question_phase_override(session)
    session.save(update_fields=["state", "current_question_id", "host_settings"])

    payload = build_finished_payload(session, finished_at=timezone.now(), limit=50)
    broadcast_play(pin, payload)

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=session.exam.organization,
        obj=session,
        new_values={"state": LiveSession.STATE_FINISHED},
        reason="game_finished",
        request=request,
    )

    return JsonResponse({"ok": True})


@require_POST
@login_required
def host_toggle_lock(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    raw_locked = request.POST.get("locked")
    if raw_locked is None:
        locked = not session.is_locked
    else:
        locked = str(raw_locked).strip().lower() in {"1", "true", "yes", "on"}

    session.is_locked = locked
    session.save(update_fields=["is_locked"])

    broadcast(pin, build_lobby_state_payload(session), "lobby")
    return JsonResponse({"ok": True, "is_locked": locked})


@require_POST
@login_required
def host_remove_player(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    if session.state != LiveSession.STATE_LOBBY:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Players can only be removed in the lobby.")},
            status=409,
        )

    try:
        player_id = int(request.POST.get("player_id"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Player was not found.")},
            status=400,
        )

    player = LivePlayer.objects.filter(session=session, id=player_id).first()
    if player is None:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Player was not found.")},
            status=404,
        )

    player.delete()
    broadcast(pin, build_lobby_state_payload(session), "lobby")
    return JsonResponse({"ok": True, "player_id": player_id})


@require_POST
@login_required
def host_update_settings(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    _ensure_host_org_permission(request, session.exam.organization)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}

    max_participants_cap = allowed_max_participants_for_user(request.user)
    updates = normalize_session_setting_updates(payload, max_participants_cap=max_participants_cap)
    settings = update_session_settings(session, updates, max_participants_cap=max_participants_cap)

    broadcast(pin, build_lobby_state_payload(session), "lobby")
    broadcast_play(
        pin,
        {
            "type": "session_settings",
            "settings": settings,
            "is_locked": bool(session.is_locked),
        },
    )
    return JsonResponse({"ok": True, "settings": settings, "is_locked": bool(session.is_locked)})
