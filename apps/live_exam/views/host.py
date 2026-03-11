"""
live_exam/views/host.py
────────────────────────
Host/teacher views for live exam sessions.
"""

from __future__ import annotations

import random

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import Exam, ExamQuestion
from apps.live_exam.domain.session import get_exam_question_ids, get_question_by_index, get_total_questions
from apps.live_exam.models import LiveSession
from apps.live_exam.transport import (
    broadcast,
    build_finished_payload,
    build_question_payload,
    build_reveal_payload,
    get_public_base_url,
)


# ════════════════════════════════════════════════════════════════════════════
# Host / Session
# ════════════════════════════════════════════════════════════════════════════


@login_required
def live_create_session_by_slug(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    if not getattr(request.user, "is_teacher", False):
        raise Http404(pgettext("live_exam.view.permission", "host_teacher_only"))

    if exam.author != request.user:
        raise Http404(pgettext("live_exam.view.permission", "host_author_only"))

    session = LiveSession.objects.create(exam=exam, host_user=request.user)
    return redirect("liveExam:host_lobby", pin=session.pin)


@login_required
def live_host_lobby(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    if session.host_user != request.user:
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    entry_url = f"{get_public_base_url(request)}{reverse('liveExam:pin_entry')}"

    exam_total = ExamQuestion.objects.filter(exam=session.exam).count()

    selected = get_total_questions(session)
    # ✅ təhlükəsizlik: selected max-dan böyük ola bilməsin
    if exam_total > 0:
        selected = max(1, min(selected, exam_total))
    else:
        selected = 0

    context = {
        "session": session,
        "entry_url": entry_url,
        "qr_url": reverse("liveExam:qr_png", kwargs={"pin": session.pin}),
        "total_questions": selected,
        "exam_total_questions": exam_total,
        "selected_total_questions": selected,
    }
    return render(request, "liveExam/host_lobby.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Host Game Controls (Kahoot Flow)
# ════════════════════════════════════════════════════════════════════════════


@require_POST
@login_required
def host_start_game(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

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

    # 2) Random seçimi session-a yaz (desired boşdursa hamısı)
    if desired is None:
        # boşdursa -> hamısı (selected_question_ids boş qalır, helper fallback exam order edir)
        session.selected_question_ids = []
        session.question_limit = None
    else:
        session.selected_question_ids = random.sample(all_ids, k=desired)
        session.question_limit = desired

    # 3) Oyun reset
    session.current_index = 0
    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = None
    session.question_ends_at = None

    session.save(
        update_fields=[
            "selected_question_ids",
            "question_limit",
            "current_index",
            "state",
            "question_started_at",
            "question_ends_at",
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

    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["question_started_at", "question_ends_at"])

    broadcast(pin, payload, "play")

    return JsonResponse(
        {
            "ok": True,
            "published": True,
            "question_count": (desired or total_in_exam),
            "total_in_exam": total_in_exam,
        }
    )


@require_POST
@login_required
def host_next_question(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

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
        session.save(update_fields=["state"])

        broadcast(pin, build_finished_payload(session, limit=50), "play")
        return JsonResponse({"ok": True, "finished": True})

    payload, now, ends = build_question_payload(session, eq, idx=idx, total=total)

    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = now
    session.question_ends_at = ends

    session.save(
        update_fields=[
            "state",
            "current_index",
            "question_started_at",
            "question_ends_at",
        ]
    )

    broadcast(pin, payload, "play")
    return JsonResponse({"ok": True, "index": idx + 1, "total": total})


@require_POST
@login_required
def host_reveal(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    idx = int(session.current_index or 0)
    eq = get_question_by_index(session, idx)
    if not eq:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "active_question_not_found")},
            status=400,
        )

    session.state = LiveSession.STATE_REVEAL
    session.save(update_fields=["state"])

    payload = build_reveal_payload(session, eq.id, revealed_at=timezone.now())
    broadcast(pin, payload, "play")

    return JsonResponse({"ok": True, "question_id": eq.id})


@require_POST
@login_required
def host_finish(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    session.state = LiveSession.STATE_FINISHED
    session.save(update_fields=["state"])

    payload = build_finished_payload(session, finished_at=timezone.now(), limit=50)
    broadcast(pin, payload, "play")

    return JsonResponse({"ok": True})
