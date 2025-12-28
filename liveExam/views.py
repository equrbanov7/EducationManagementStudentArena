import io
import re
import uuid
import qrcode

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import IntegrityError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from liveExam.models import LiveSession, LivePlayer, LiveAnswer

# ✅ Exam modellərin haradadırsa onu seç:
# Variant A: Exam modeli blog app-dadırsa
from blog.models import Exam, ExamQuestion, ExamQuestionOption

# Variant B: Exam modeli başqa app-dadırsa (məsələn exams app)
# from exams.models import Exam, ExamQuestion, ExamQuestionOption




AVATAR_KEYS = [
    "avatar_1","avatar_2","avatar_3","avatar_4","avatar_5","avatar_6",
    "avatar_7","avatar_8","avatar_9","avatar_10","avatar_11","avatar_12",
]

PLAYER_TOKEN_SALT = "liveExam.player"
PLAYER_COOKIE_NAME = "live_player_token"


def _clean_nickname(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:32]


def _get_client_id(request):
    # login olmadan istifadəçi üçün stabil id
    # 1) cookie varsa al, 2) yoxdursa yeni yarat
    cid = request.COOKIES.get("live_client_id")
    if cid:
        return cid
    return uuid.uuid4().hex


@login_required
def live_create_session_by_slug(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    # müəllim yoxlaması
    if not getattr(request.user, "is_teacher", False):
        raise Http404("Only teacher can create live session.")

    # yalnız müəllif host olsun
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
    }
    return render(request, "liveExam/host_lobby.html", context)



def live_join_page(request, pin):
    """
    Player join səhifəsi: nickname + avatar seçir.
    """
    session = get_object_or_404(LiveSession, pin=pin)

    if session.state != LiveSession.STATE_LOBBY:
        # oyun başlayıbsa belə, istəsən "late join" qaydası tətbiq edərik
        pass

    context = {
        "session": session,
        "avatars": AVATAR_KEYS,
    }
    return render(request, "liveExam/join.html", context)


@require_POST
def live_join_enter(request, pin):
    """
    Player qeydiyyatı (login olmadan):
    - nickname + avatar
    - client_id cookie ilə eyni cihazı tanı (yoxdursa uuid yarat)
    - session + client_id UNIQUE => duplicate olmasın
    - token cookie set et
    - host lobby-yə realtime update göndər
    """
    session = get_object_or_404(LiveSession, pin=pin)

    if session.is_locked:
        return JsonResponse({"ok": False, "message": "Lobby kilidlənib."}, status=403)

    # 1) Input validation
    nickname = _clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or "avatar_1"
    if avatar_key not in AVATAR_KEYS:
        avatar_key = "avatar_1"

    if not nickname:
        return JsonResponse({"ok": False, "message": "Nickname boş ola bilməz."}, status=400)

    # 2) ✅ client_id: birbaşa cookie-dən oxu, yoxdursa yarat
    client_id = request.COOKIES.get("live_client_id")
    if not client_id:
        client_id = uuid.uuid4().hex

    now = timezone.now()

    # 3) ✅ Duplicate olmasın: əvvəl tap, yoxdursa yarat (unique constraint də qoruyur)
    player = LivePlayer.objects.filter(session=session, client_id=client_id).first()

    if player:
        player.nickname = nickname
        player.avatar_key = avatar_key
        player.is_connected = True
        player.last_seen = now
        player.save(update_fields=["nickname", "avatar_key", "is_connected", "last_seen"])
    else:
        try:
            player = LivePlayer.objects.create(
                session=session,
                client_id=client_id,
                nickname=nickname,
                avatar_key=avatar_key,
                is_connected=True,
                last_seen=now,
            )
        except IntegrityError:
            # race condition (parallel request) üçün fallback
            player = LivePlayer.objects.get(session=session, client_id=client_id)
            player.nickname = nickname
            player.avatar_key = avatar_key
            player.is_connected = True
            player.last_seen = now
            player.save(update_fields=["nickname", "avatar_key", "is_connected", "last_seen"])

    # 4) Token cookie (player auth kimi)
    token = signing.dumps(
        {"pin": session.pin, "player_id": player.id, "client_id": client_id},
        salt=PLAYER_TOKEN_SALT,
    )

    # 5) Response
    # resp = JsonResponse({
    #     "ok": True,
    #     # istersen burani wait_room-a change edersen:
    #     "redirect": reverse("liveExam:join_page", kwargs={"pin": session.pin}),
    # })
    resp = JsonResponse({"ok": True, "redirect": reverse("liveExam:wait_room", kwargs={"pin": session.pin})})


    # 6) ✅ client_id cookie-ni HƏMİŞƏ set et (stabil olsun)
    resp.set_cookie(
        "live_client_id",
        client_id,
        max_age=60 * 60 * 24 * 30,
        samesite="Lax",
    )

    # 7) Player token cookie
    resp.set_cookie(
        PLAYER_COOKIE_NAME,
        token,
        max_age=60 * 60 * 6,
        samesite="Lax",
    )

    # 8) ✅ host lobby-yə realtime update
    channel_layer = get_channel_layer()
    players = list(
        session.players.order_by("-created_at").values("id", "nickname", "avatar_key")[:50]
    )
    async_to_sync(channel_layer.group_send)(
        f"live_{session.pin}_lobby",
        {
            "type": "lobby_event",
            "data": {
                "type": "lobby_state",
                "count": session.players.count(),
                "players": players,
            },
        },
    )

    return resp


def live_qr_png(request, pin):
    """
    QR code image: join link-i encode edir.
    """
    session = get_object_or_404(LiveSession, pin=pin)

    join_url = request.build_absolute_uri(
        reverse("liveExam:join_page", kwargs={"pin": session.pin})
    )

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")



def live_player_screen(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    # player token yoxdursa join page-ə qaytar
    token = request.COOKIES.get(PLAYER_COOKIE_NAME)
    if not token:
        return redirect("liveExam:join_page", pin=pin)

    context = {"session": session}
    return render(request, "liveExam/player_screen.html", context)


def live_wait_room(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    return render(request, "liveExam/wait_room.html", {"session": session})


def _broadcast(pin: str, payload: dict, group_suffix: str = "play"):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"live_{pin}_{group_suffix}",
        {"type": "play_event", "data": payload},
    )


def _get_current_exam_question(session: LiveSession):
    # ExamQuestion -> exam + order
    # order field adı səndə "order" kimi görünür :contentReference[oaicite:0]{index=0}
    qs = ExamQuestion.objects.filter(exam=session.exam).order_by("order")
    idx = session.current_index
    items = list(qs[: idx + 1])
    if idx < 0 or idx >= len(items):
        return None
    return items[idx]


@require_POST
@login_required
def host_start_game(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    session.state = LiveSession.STATE_QUESTION
    session.current_index = 0
    session.save(update_fields=["state", "current_index"])

    return redirect("liveExam:host_lobby", pin=pin)


@require_POST
@login_required
def host_next_question(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    # sualı hazırla
    eq = _get_current_exam_question(session)
    if eq is None:
        # ilk dəfə basılırsa current_index 0 olmalıdır, yoxsa bitib
        return redirect("liveExam:host_lobby", pin=pin)

    # vaxt
    time_limit = eq.time_limit_seconds or session.exam.default_question_time_seconds
    now = timezone.now()
    ends = now + timezone.timedelta(seconds=time_limit)

    session.state = LiveSession.STATE_QUESTION
    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["state", "question_started_at", "question_ends_at"])

    # cavabları (options) yığ
    opts = list(
        ExamQuestionOption.objects
        .filter(question=eq)
        .order_by("label")
        .values("id", "label", "text")
    )

    payload = {
        "type": "question_published",
        "question": {
            "id": eq.id,
            "text": eq.text,
            "time_limit": time_limit,
            "points": eq.points,
            "options": opts,
        }
    }
    _broadcast(pin, payload, "play")
    return JsonResponse({"ok": True})


@require_POST
@login_required
def host_reveal(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    eq = _get_current_exam_question(session)
    if not eq:
        return JsonResponse({"ok": False}, status=400)

    correct_ids = list(
        ExamQuestionOption.objects.filter(question=eq, is_correct=True).values_list("id", flat=True)
    )

    # scoreboard
    top = list(
        session.players.order_by("-score", "created_at").values("nickname", "avatar_key", "score")[:10]
    )

    session.state = LiveSession.STATE_REVEAL
    session.save(update_fields=["state"])

    _broadcast(pin, {
        "type": "reveal",
        "question_id": eq.id,
        "correct_option_ids": correct_ids,
        "top": top,
    }, "play")

    return JsonResponse({"ok": True})


@require_POST
@login_required
def host_finish(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user != request.user:
        raise Http404()

    session.state = LiveSession.STATE_FINISHED
    session.save(update_fields=["state"])

    top = list(
        session.players.order_by("-score", "created_at").values("nickname", "avatar_key", "score")[:50]
    )

    _broadcast(pin, {"type": "finished", "top": top}, "play")
    return JsonResponse({"ok": True})
