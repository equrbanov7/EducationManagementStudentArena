"""
live_exam/views/host.py
────────────────────────
Host/teacher views for live exam sessions.
"""

from __future__ import annotations

import json
import random
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.utils import log_action
from apps.exams.models import Exam, ExamQuestion
from apps.exams.services.access_policy import is_teacher_user
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
from apps.live_exam.services import finish_session
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
    build_join_url,
    build_lobby_state_payload,
    build_player_reveal_payload,
    build_question_payload,
    build_question_phase_payload,
    build_reveal_payload,
)
from core.constants import AuditAction
from core.permissions import request_has_permission

# ════════════════════════════════════════════════════════════════════════════
# Authorization helpers
# ════════════════════════════════════════════════════════════════════════════


def _ensure_host_org_permission(request, exam_organization) -> None:
    """
    Enforce organization-level RBAC for all host endpoints.

    Checks (in order):
    1. An active organization context exists in the request.
    2. The exam's organization matches the request's active organization.
    3. The organization is not suspended or inactive.
    4. The requesting user holds the ``exam.host`` permission, or the broader
       ``exam.manage`` permission.

    Raises ``PermissionDenied`` on any violation.
    """
    org = getattr(request, "organization", None)
    if org is None:
        raise PermissionDenied(pgettext("live_exam.view.permission", "org_context_required"))

    if exam_organization is None or org.id != exam_organization.id:
        raise PermissionDenied(pgettext("live_exam.view.permission", "cross_org_access_denied"))

    if org.is_suspended:
        raise PermissionDenied(pgettext("live_exam.view.permission", "org_suspended_or_inactive"))

    if not (request_has_permission(request, "exam.host") or request_has_permission(request, "exam.manage")):
        raise PermissionDenied(pgettext("live_exam.view.permission", "exam_manage_required"))


# ════════════════════════════════════════════════════════════════════════════
# Host / Session
# ════════════════════════════════════════════════════════════════════════════

LIVE_ACTIVE_STATES = (
    LiveSession.STATE_LOBBY,
    LiveSession.STATE_QUESTION,
    LiveSession.STATE_REVEAL,
)


@login_required
def live_create_session_by_slug(request, slug):
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)

    is_superadmin = request.user.is_superuser or getattr(request.user, "is_superadmin", False)

    if not is_superadmin and not is_teacher_user(request.user):
        raise Http404(pgettext("live_exam.view.permission", "host_teacher_only"))

    if not is_superadmin and exam.author != request.user:
        raise Http404(pgettext("live_exam.view.permission", "host_author_only"))

    _ensure_host_org_permission(request, exam.organization)

    if not exam.is_active:
        messages.warning(request, pgettext("live_exam.view.message", "exam_must_be_active_before_live"))
        return redirect(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))

    force_new_session = str(request.GET.get("force_new") or "").strip().lower() in {"1", "true", "yes", "on"}
    probe_only = str(request.GET.get("probe") or "").strip().lower() in {"1", "true", "yes", "on"}
    active_sessions = LiveSession.objects.filter(
        exam=exam,
        host_user=request.user,
        state__in=LIVE_ACTIVE_STATES,
    ).order_by("-created_at", "-id")
    active_session = active_sessions.first()

    if probe_only:
        if active_session:
            presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": active_session.pin})
            new_url = f"{reverse('liveExam:create_session_slug', kwargs={'slug': exam.slug})}?force_new=1"
            return JsonResponse(
                {
                    "active": True,
                    "pin": active_session.pin,
                    "created": timezone.localtime(active_session.created_at).strftime("%d.%m.%Y %H:%M"),
                    "return_url": f"{presentation_url}?controls=1",
                    "new_url": new_url,
                }
            )
        return JsonResponse({"active": False})

    if active_session and not force_new_session:
        presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": active_session.pin})
        return redirect(f"{presentation_url}?controls=1")

    if force_new_session:
        for old_session in active_sessions:
            finish_session(old_session)

    session = LiveSession.objects.create(exam=exam, host_user=request.user)
    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=exam.organization,
        obj=session,
        new_values={"exam": str(exam.pk), "pin": session.pin},
        request=request,
    )
    presentation_url = reverse("liveExam:host_presentation", kwargs={"pin": session.pin})
    return redirect(f"{presentation_url}?controls=1")


def _host_session_context(request, session: LiveSession, *, auto_fullscreen: str = "0") -> dict[str, object]:
    exam_total = ExamQuestion.objects.filter(exam=session.exam).count()
    selected = get_total_questions(session)
    if exam_total > 0:
        selected = max(1, min(selected, exam_total))
    else:
        selected = 0

    session_settings = get_session_settings(session)

    return {
        "session": session,
        "entry_url": build_join_url(request, session),
        "qr_url": reverse("liveExam:qr_png", kwargs={"pin": session.pin}),
        "total_questions": selected,
        "exam_total_questions": exam_total,
        "selected_total_questions": selected,
        "session_settings": session_settings,
        "session_locked": bool(session.is_locked),
        "max_participants_cap": allowed_max_participants_for_user(request.user),
        "auto_fullscreen": auto_fullscreen,
    }


@login_required
def live_host_lobby(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)

    if session.host_user != request.user:
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    _ensure_host_org_permission(request, session.exam.organization)

    context = _host_session_context(request, session)
    return render(request, "liveExam/host_lobby.html", context)


@login_required
def live_host_presentation(request, pin):
    session = get_object_or_404(LiveSession.objects.select_related("exam__organization"), pin=pin)

    if session.host_user != request.user:
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    _ensure_host_org_permission(request, session.exam.organization)

    controls_enabled = str(request.GET.get("controls") or "").strip().lower() in {"1", "true", "yes", "on"}
    context = _host_session_context(request, session, auto_fullscreen="1" if request.GET.get("autofs") == "1" else "0")
    context["presentation_controls"] = controls_enabled
    return render(request, "liveExam/host_presentation.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Host Game Controls (Kahoot Flow)
# ════════════════════════════════════════════════════════════════════════════


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
