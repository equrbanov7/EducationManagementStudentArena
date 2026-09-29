"""live_exam host paketi — game.

Bütün oyun keçidləri ``apps.live_exam.services``-dədir: sessiya sətri kilidlənir,
vəziyyət kilid altında yoxlanılır (Audit 2026-09-28 LXBE-04/05). View-lar yalnız
icazəni yoxlayır və nəticəni HTTP cavabına çevirir.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.public import log_action
from apps.live_exam import services
from apps.live_exam.domain.session import get_exam_question_ids, get_question_by_index
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import SessionSettingsError, allowed_max_participants_for_user
from apps.live_exam.transport import broadcast, broadcast_play
from core.constants import AuditAction

from ._shared import (
    _ensure_host_org_permission,
)


def _message(msgid: str) -> str:
    return pgettext("live_exam.view.message", msgid)


def _host_session_or_404(request, pin) -> LiveSession:
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()
    _ensure_host_org_permission(request, session.exam.organization)
    return session


def _parse_question_count(raw: str, total_in_exam: int):
    """``(dəyər, None)`` və ya ``(None, JsonResponse)``."""
    if not raw:
        return None, None
    try:
        desired = int(raw)
    except (TypeError, ValueError):
        return None, JsonResponse({"ok": False, "message": _message("invalid_question_count")}, status=400)
    if desired <= 0:
        return None, JsonResponse({"ok": False, "message": _message("question_count_minimum")}, status=400)
    if desired > total_in_exam:
        message = _message("question_count_exceeds_total").format(total_in_exam=total_in_exam, desired=desired)
        return None, JsonResponse({"ok": False, "message": message}, status=400)
    return desired, None


@require_POST
@login_required
def host_start_game(request, pin):
    session = _host_session_or_404(request, pin)

    # ── State guard: game can only be started from LOBBY ──
    if session.state != LiveSession.STATE_LOBBY:
        return JsonResponse({"ok": False, "message": _message("game_already_started")}, status=409)

    total_in_exam = len(get_exam_question_ids(session))
    if total_in_exam <= 0:
        return JsonResponse({"ok": False, "message": _message("no_questions_in_exam")}, status=400)
    desired, error_response = _parse_question_count((request.POST.get("question_count") or "").strip(), total_in_exam)
    if error_response is not None:
        return error_response

    # Audit 2026-09-13 backend F-07: sessiya yazıları + audit qeydi BİR tranzaksiyada;
    # yayımlar `on_commit`-də. Audit 2026-09-28 LXBE-05: sətir kilidlənir və vəziyyət
    # kilid altında yenidən yoxlanır — ikiqat «Başla» oyunu iki dəfə başlatmır.
    with transaction.atomic():
        locked = services.lock_session(session)
        if locked.state != LiveSession.STATE_LOBBY:
            return JsonResponse({"ok": False, "message": _message("game_already_started")}, status=409)
        selected_ids = services.select_question_ids(locked, desired)
        locked.selected_question_ids = selected_ids
        locked.question_limit = len(selected_ids)
        locked.save(update_fields=["selected_question_ids", "question_limit"])

        eq = get_question_by_index(locked, 0)
        if not eq:
            transaction.set_rollback(True)
            return JsonResponse({"ok": False, "message": _message("question_not_found")}, status=400)
        payload = services.publish_question(locked, eq, idx=0, total=len(selected_ids))

        # Wait room-da olan player-ları player_screen-ə yönləndir, sonra 1-ci sual.
        game_started = services.game_started_payload(reverse("liveExam:player_screen", kwargs={"pin": pin}))
        transaction.on_commit(lambda: broadcast(pin, game_started, "lobby"))
        transaction.on_commit(lambda: broadcast_play(pin, payload))

        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=session.exam.organization,
            obj=locked,
            new_values={"state": locked.state, "question_count": len(selected_ids)},
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
    session = _host_session_or_404(request, pin)

    # ── State guard: next question only from REVEAL (LXBE-05) ──
    result = services.advance_to_next(session)
    if not result.get("ok"):
        return JsonResponse(
            {"ok": False, "message": _message(result.get("code") or "invalid_state_for_next")}, status=409
        )
    if result.get("finished"):
        return JsonResponse({"ok": True, "finished": True})
    return JsonResponse({"ok": True, "index": result["index"], "total": result["total"]})


@require_POST
@login_required
def host_skip_question_intro(request, pin):
    session = _host_session_or_404(request, pin)

    result = services.skip_question_intro(session)
    if not result.get("ok"):
        return JsonResponse({"ok": False, "message": _message(result["code"])}, status=result.get("status", 409))
    return JsonResponse(result)


@require_POST
@login_required
def host_reveal(request, pin):
    session = _host_session_or_404(request, pin)

    # ── State guard: reveal only from QUESTION state ──
    result = services.reveal_current(session)
    if not result.get("ok"):
        status = 400 if result.get("code") == "active_question_not_found" else 409
        return JsonResponse({"ok": False, "message": _message(result["code"])}, status=status)
    return JsonResponse({"ok": True, "question_id": result["question_id"]})


@require_POST
@login_required
def host_finish(request, pin):
    session = _host_session_or_404(request, pin)

    # ── State guard: cannot finish an already-finished session ──
    if session.state == LiveSession.STATE_FINISHED:
        return JsonResponse({"ok": False, "message": _message("session_already_finished")}, status=409)

    services.finish_session(session)

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
    session = _host_session_or_404(request, pin)

    raw_locked = request.POST.get("locked")
    if raw_locked is None:
        locked = None
    else:
        locked = str(raw_locked).strip().lower() in {"1", "true", "yes", "on"}

    locked = services.toggle_session_lock(session, locked=locked)
    return JsonResponse({"ok": True, "is_locked": locked})


@require_POST
@login_required
def host_remove_player(request, pin):
    session = _host_session_or_404(request, pin)

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

    try:
        removed = services.remove_player(session, player_id)
    except ValueError:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Players can only be removed in the lobby.")},
            status=409,
        )
    if not removed:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Player was not found.")},
            status=404,
        )
    return JsonResponse({"ok": True, "player_id": player_id})


@require_POST
@login_required
def host_update_settings(request, pin):
    session = _host_session_or_404(request, pin)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}

    try:
        settings = services.update_host_settings(
            session,
            payload,
            max_participants_cap=allowed_max_participants_for_user(request.user),
        )
    except SessionSettingsError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "settings": settings, "is_locked": bool(session.is_locked)})
