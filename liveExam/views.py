import io
import re
import uuid
import qrcode

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from liveExam.models import LiveSession, LivePlayer, LiveAnswer
from blog.models import Exam, ExamQuestion, ExamQuestionOption


AVATAR_KEYS = [
    "avatar_1","avatar_2","avatar_3","avatar_4","avatar_5","avatar_6",
    "avatar_7","avatar_8","avatar_9","avatar_10","avatar_11","avatar_12",
]

PLAYER_COOKIE_NAME = "live_player_token"
PLAYER_TOKEN_SALT = "liveExam.player"


# ------------------------
# Helpers
# ------------------------
def _clean_nickname(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:32]


def _get_client_id(request):
    cid = request.COOKIES.get("live_client_id")
    return cid or uuid.uuid4().hex


def _broadcast(pin: str, payload: dict, group_suffix: str):
    """
    group_suffix:
      - "lobby" => live_<pin>_lobby
      - "play"  => live_<pin>_play
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"live_{pin}_{group_suffix}",
        {
            "type": "play_event" if group_suffix == "play" else "lobby_event",
            "data": payload,
        },
    )


def _serialize_players(session: LiveSession, limit: int = 50):
    return list(
        session.players.order_by("-created_at")
        .values("id", "nickname", "avatar_key")[:limit]
    )


def _serialize_top(session: LiveSession, limit: int = 10):
    return list(
        session.players.order_by("-score", "created_at")
        .values("nickname", "avatar_key", "score")[:limit]
    )


def _get_total_questions(session: LiveSession) -> int:
    return ExamQuestion.objects.filter(exam=session.exam).count()


def _get_question_by_index(session: LiveSession, index: int):
    qs = ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id")
    try:
        return qs[index]
    except Exception:
        return None


def _question_time_limit(session: LiveSession, eq: ExamQuestion) -> int:
    # səndə ExamQuestion.effective_time_limit property var — varsa onu istifadə elə
    if hasattr(eq, "effective_time_limit"):
        try:
            return int(eq.effective_time_limit)
        except Exception:
            pass

    tl = getattr(eq, "time_limit_seconds", None)
    if tl:
        return int(tl)

    default_tl = getattr(session.exam, "default_question_time_seconds", None)
    return int(default_tl or 15)


def _question_points(session: LiveSession, eq: ExamQuestion) -> int:
    # ExamQuestion.points yoxdursa Exam.default_question_points
    p = getattr(eq, "points", None)
    if p:
        return int(p)
    default_p = getattr(session.exam, "default_question_points", None)
    return int(default_p or 1)


def _serialize_question_results(session: LiveSession, question_id: int, limit: int = 50):
    """
    Reveal üçün:
    - kim doğru yazdı
    - bu sualdan neçə bal qazandı
    - total score
    """
    answers = (
        LiveAnswer.objects
        .filter(session=session, question_id=question_id)
        .select_related("player")
        .order_by("-awarded_points", "-created_at")
    )[:limit]

    out = []
    for a in answers:
        out.append({
            "nickname": a.player.nickname,
            "avatar_key": a.player.avatar_key,
            "is_correct": bool(a.is_correct),
            "awarded_points": int(a.awarded_points or 0),
            "total_score": int(a.player.score or 0),
        })
    return out


def _is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _build_question_payload(session: LiveSession, eq: ExamQuestion, idx: int, total: int):
    time_limit = _question_time_limit(session, eq)
    now = timezone.now()
    ends = now + timezone.timedelta(seconds=time_limit)

    opts = list(
        ExamQuestionOption.objects
        .filter(question=eq)
        .order_by("label", "id")
        .values("id", "label", "text")
    )

    payload = {
        "type": "question_published",
        "question": {
            "id": eq.id,
            "text": eq.text,
            "time_limit": time_limit,
            "points": _question_points(session, eq),
            "options": opts,
            # timer üçün
            "started_at": now.isoformat(),
            "ends_at": ends.isoformat(),
            # info
            "index": idx + 1,
            "total": total,
        }
    }
    return payload, now, ends


# ------------------------
# Host / Session
# ------------------------
@login_required
def live_create_session_by_slug(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    if not getattr(request.user, "is_teacher", False):
        raise Http404("Only teacher can create live session.")

    if exam.author != request.user:
        raise Http404("Only exam author can host live session.")

    session = LiveSession.objects.create(exam=exam, host_user=request.user)
    return redirect("liveExam:host_lobby", pin=session.pin)


@login_required
def live_host_lobby(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    if session.host_user != request.user:
        raise Http404("Not allowed.")

    join_url = request.build_absolute_uri(
        reverse("liveExam:join_page", kwargs={"pin": session.pin})
    )

    context = {
        "session": session,
        "join_url": join_url,
        "qr_url": reverse("liveExam:qr_png", kwargs={"pin": session.pin}),
        "total_questions": _get_total_questions(session),
    }
    return render(request, "liveExam/host_lobby.html", context)


# ------------------------
# Player join / wait / screen
# ------------------------
def live_join_page(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    context = {"session": session, "avatars": AVATAR_KEYS}
    return render(request, "liveExam/join.html", context)


@require_POST
def live_join_enter(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    if session.is_locked:
        return JsonResponse({"ok": False, "message": "Lobby kilidlənib."}, status=403)

    nickname = _clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or "avatar_1"
    if avatar_key not in AVATAR_KEYS:
        avatar_key = "avatar_1"

    if not nickname:
        return JsonResponse({"ok": False, "message": "Nickname boş ola bilməz."}, status=400)

    client_id = _get_client_id(request)
    now = timezone.now()

    player = LivePlayer.objects.filter(session=session, client_id=client_id).first()
    if player:
        player.nickname = nickname
        player.avatar_key = avatar_key
        player.is_connected = True
        player.last_seen = now
        player.save(update_fields=["nickname", "avatar_key", "is_connected", "last_seen"])
    else:
        player = LivePlayer.objects.create(
            session=session,
            client_id=client_id,
            nickname=nickname,
            avatar_key=avatar_key,
            is_connected=True,
            last_seen=now,
        )

    token = signing.dumps(
        {"pin": session.pin, "player_id": player.id, "client_id": client_id},
        salt=PLAYER_TOKEN_SALT,
    )

    # lobby-yə realtime update
    _broadcast(session.pin, {
        "type": "lobby_state",
        "count": session.players.count(),
        "players": _serialize_players(session),
    }, "lobby")

    wait_url = reverse("liveExam:wait_room", kwargs={"pin": session.pin})
    resp = JsonResponse({"ok": True, "redirect": wait_url})

    resp.set_cookie("live_client_id", client_id, max_age=60 * 60 * 24 * 30, samesite="Lax")
    resp.set_cookie(PLAYER_COOKIE_NAME, token, max_age=60 * 60 * 6, samesite="Lax", httponly=True)

    return resp


def live_qr_png(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    join_url = request.build_absolute_uri(
        reverse("liveExam:join_page", kwargs={"pin": session.pin})
    )

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


def live_wait_room(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    players = _serialize_players(session)
    return render(
        request,
        "liveExam/wait_room.html",
        {
            "session": session,
            "players": players,
            "player_screen_url": reverse("liveExam:player_screen", kwargs={"pin": session.pin}),
        },
    )


def live_player_screen(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    token = request.COOKIES.get(PLAYER_COOKIE_NAME)
    if not token:
        return redirect("liveExam:join_page", pin=pin)

    return render(request, "liveExam/player_screen.html", {"session": session})


# ✅ NEW: cari state-i HTTP ilə almaq (late join / miss olunan WS üçün)
def live_state_json(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    total = _get_total_questions(session)

    data = {
        "ok": True,
        "pin": session.pin,
        "state": session.state,
        "current_index": int(session.current_index or 0),
        "total_questions": total,
        "question_started_at": session.question_started_at.isoformat() if session.question_started_at else None,
        "question_ends_at": session.question_ends_at.isoformat() if session.question_ends_at else None,
    }

    # cari sual (index-dən)
    eq = _get_question_by_index(session, int(session.current_index or 0))
    if eq:
        # reveal olduqda correct ids də lazımdır
        correct_ids = list(
            ExamQuestionOption.objects.filter(question=eq, is_correct=True)
            .values_list("id", flat=True)
        )
        # question payload (timer üçün ends_at)
        payload, now, ends = _build_question_payload(session, eq, int(session.current_index or 0), total)

        # payload-dakı started/ends-i session-dan override edək (əgər artıq publish olunubsa)
        if session.question_started_at:
            payload["question"]["started_at"] = session.question_started_at.isoformat()
        if session.question_ends_at:
            payload["question"]["ends_at"] = session.question_ends_at.isoformat()

        data["question"] = payload["question"]
        data["correct_option_ids"] = correct_ids if session.state == LiveSession.STATE_REVEAL else []

    return JsonResponse(data)


# ------------------------
# Host game controls (Kahoot flow)
# ------------------------
@require_POST
@login_required
def host_start_game(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    # oyun reset
    session.current_index = 0
    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = None
    session.question_ends_at = None
    session.save(update_fields=["current_index", "state", "question_started_at", "question_ends_at"])

    # ✅ Wait_room-da olan player-lara player_screen-ə keç siqnalı
    _broadcast(pin, {
        "type": "game_started",
        "redirect": reverse("liveExam:player_screen", kwargs={"pin": pin}),
    }, "lobby")

    # ✅ Start klikində dərhal 1-ci sualı publish et (sual gəlmir problemini bağlayır)
    total = _get_total_questions(session)
    eq = _get_question_by_index(session, 0)
    if eq:
        payload, now, ends = _build_question_payload(session, eq, 0, total)
        session.question_started_at = now
        session.question_ends_at = ends
        session.save(update_fields=["question_started_at", "question_ends_at"])
        _broadcast(pin, payload, "play")

    if _is_ajax(request):
        return JsonResponse({"ok": True, "published": bool(eq)})

    return redirect("liveExam:host_lobby", pin=pin)


@require_POST
@login_required
def host_next_question(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    # Kahoot axını:
    # reveal-dan sonra növbəti sual üçün index++
    if session.state == LiveSession.STATE_REVEAL:
        session.current_index = int(session.current_index or 0) + 1

    idx = int(session.current_index or 0)
    total = _get_total_questions(session)

    eq = _get_question_by_index(session, idx)
    if eq is None:
        return JsonResponse({"ok": False, "message": "Sual qalmayıb."}, status=400)

    payload, now, ends = _build_question_payload(session, eq, idx, total)

    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

    _broadcast(pin, payload, "play")
    return JsonResponse({"ok": True, "index": idx + 1, "total": total})


@require_POST
@login_required
def host_reveal(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    idx = int(session.current_index or 0)
    eq = _get_question_by_index(session, idx)
    if not eq:
        return JsonResponse({"ok": False, "message": "Aktiv sual tapılmadı."}, status=400)

    correct_ids = list(
        ExamQuestionOption.objects
        .filter(question=eq, is_correct=True)
        .values_list("id", flat=True)
    )

    session.state = LiveSession.STATE_REVEAL
    session.save(update_fields=["state"])

    payload = {
        "type": "reveal",
        "question_id": eq.id,
        "correct_option_ids": correct_ids,
        "results": _serialize_question_results(session, eq.id, limit=50),
        "top": _serialize_top(session, limit=10),
    }
    _broadcast(pin, payload, "play")

    return JsonResponse({"ok": True})


@require_POST
@login_required
def host_finish(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    session.state = LiveSession.STATE_FINISHED
    session.save(update_fields=["state"])

    payload = {
        "type": "finished",
        "top": _serialize_top(session, limit=50),
    }
    _broadcast(pin, payload, "play")

    return JsonResponse({"ok": True})
