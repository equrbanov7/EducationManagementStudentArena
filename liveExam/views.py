from __future__ import annotations
import io
import re
import uuid
import qrcode
import random
import hashlib




from django.contrib.auth.decorators import login_required
from django.core import signing
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from typing import Any, Dict, List, Optional, Tuple

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from liveExam.models import LiveSession, LivePlayer, LiveAnswer
from liveExam.constants import AVATAR_EMOJI
from blog.models import Exam, ExamQuestion, ExamQuestionOption


AVATAR_KEYS = [
    "avatar_1","avatar_2","avatar_3","avatar_4","avatar_5","avatar_6",
    "avatar_7","avatar_8","avatar_9","avatar_10","avatar_11","avatar_12",
]

PLAYER_COOKIE_NAME = "live_player_token"
PLAYER_TOKEN_SALT = "liveExam.player"


# ------------------------
# Helpers (clean & stable)
# ------------------------


# ------------------------
# Small utils
# ------------------------

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _clean_nickname(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name[:32]


def _get_client_id(request) -> str:
    """
    client_id cookie yoxdursa yenisini qaytarır (uuid hex).
    """
    cid = request.COOKIES.get("live_client_id")
    return cid or uuid.uuid4().hex


# ------------------------
# Broadcast (Channels group_send)
# ------------------------

def _broadcast(pin: str, payload: dict, group_suffix: str) -> None:
    """
    group_suffix: 'lobby' | 'play'
    Consumer-lər:
      - LiveLobbyConsumer -> lobby_event
      - LivePlayConsumer  -> play_event
    """
    layer = get_channel_layer()
    event_type = "play_event" if group_suffix == "play" else "lobby_event"

    async_to_sync(layer.group_send)(
        f"live_{pin}_{group_suffix}",
        {"type": event_type, "data": payload},
    )


# ------------------------
# Serializers
# ------------------------

def _serialize_players(session: LiveSession, limit: int = 50) -> List[Dict[str, Any]]:
    return list(
        session.players.order_by("-created_at")
        .values("id", "nickname", "avatar_key")[:limit]
    )


def _serialize_top(session: LiveSession, limit: int = 10) -> List[Dict[str, Any]]:
    return list(
        session.players.order_by("-score", "created_at")
        .values("nickname", "avatar_key", "score")[:limit]
    )


def _serialize_question_results(session: LiveSession, question_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Reveal zamanı: bu sual üzrə kim nə qədər bal aldı, total score nədir.
    """
    answers = (
        LiveAnswer.objects
        .filter(session=session, question_id=question_id)
        .select_related("player")
        .order_by("-awarded_points", "-created_at")
    )[:limit]

    out: List[Dict[str, Any]] = []
    for a in answers:
        out.append({
            "nickname": a.player.nickname,
            "avatar_key": a.player.avatar_key,
            "is_correct": bool(a.is_correct),
            "awarded_points": _safe_int(a.awarded_points, 0),
            "total_score": _safe_int(a.player.score, 0),
        })
    return out


# ------------------------
# Question picking helpers
# ------------------------

def _get_selected_question_ids(session: LiveSession) -> List[int]:
    """
    session.selected_question_ids JSONField ola bilər (list[int] / list[str] / mix).
    """
    ids = getattr(session, "selected_question_ids", None) or []
    out: List[int] = []
    for x in ids:
        try:
            out.append(int(x))
        except Exception:
            pass
    return out


def _get_exam_question_ids(session: LiveSession) -> List[int]:
    """
    Exam-dəki bütün ExamQuestion id-ləri (sıra ilə).
    Səndə order field var deyə: order, id.
    """
    return list(
        ExamQuestion.objects
        .filter(exam=session.exam)
        .order_by("order", "id")
        .values_list("id", flat=True)
    )


def _get_total_questions(session: LiveSession) -> int:
    selected = _get_selected_question_ids(session)
    if selected:
        return len(selected)
    return ExamQuestion.objects.filter(exam=session.exam).count()


def _get_question_by_index(session: LiveSession, index: int) -> Optional[ExamQuestion]:
    """
    index 0-based.
    selected_question_ids doludursa -> ordan,
    yoxsa -> exam order ilə.
    """
    index = _safe_int(index, 0)
    if index < 0:
        return None

    selected = _get_selected_question_ids(session)
    if selected:
        if index >= len(selected):
            return None
        qid = selected[index]
        return ExamQuestion.objects.filter(exam=session.exam, id=qid).first()

    qs = ExamQuestion.objects.filter(exam=session.exam).order_by("order", "id")
    try:
        return qs[index]
    except Exception:
        return None


def _get_current_exam_question(session: LiveSession) -> Optional[ExamQuestion]:
    return _get_question_by_index(session, _safe_int(session.current_index, 0))


# ------------------------
# Timing & points
# ------------------------

def _question_time_limit(session: LiveSession, eq: ExamQuestion) -> int:
    """
    1) eq.effective_time_limit (səndə varsa)
    2) eq.time_limit_seconds
    3) exam.default_question_time_seconds
    default: 15
    """
    if hasattr(eq, "effective_time_limit"):
        v = _safe_int(getattr(eq, "effective_time_limit", 0), 0)
        if v > 0:
            return v

    v = _safe_int(getattr(eq, "time_limit_seconds", 0), 0)
    if v > 0:
        return v

    v = _safe_int(getattr(session.exam, "default_question_time_seconds", 0), 0)
    if v > 0:
        return v

    return 15


def _question_points(session: LiveSession, eq: ExamQuestion) -> int:
    """
    1) eq.points
    2) exam.default_question_points
    default: 1
    """
    v = _safe_int(getattr(eq, "points", 0), 0)
    if v > 0:
        return v

    v = _safe_int(getattr(session.exam, "default_question_points", 0), 0)
    if v > 0:
        return v

    return 1


def _get_question_text(eq: ExamQuestion) -> str:
    """
    Səndə eq.text var deyə əsas onu götürür.
    Alternativ field-lar varsa fallback.
    """
    for attr in ("text", "question_text", "title", "body"):
        v = getattr(eq, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ------------------------
# Options (NULL fix) + Multi detect
# ------------------------

def _get_option_text(opt) -> str:
    """
    “null” problemini öldürmək üçün:
    mövcud field-lardan birini tapıb qaytarır.
    """
    for attr in ("text", "title", "content", "answer", "option_text", "body"):
        v = getattr(opt, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _get_option_label(opt) -> str:
    v = getattr(opt, "label", None)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def _options_seed(pin: str, question_id: int, started_at) -> int:
    seed_str = f"{pin}:{int(question_id)}:{started_at.isoformat()}"
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return int(h[:8], 16)  # 32-bit seed

def _build_options(eq, *, seed: int | None = None):
    """
    ✅ Variantları qarışdırır.
    seed verilsə, shuffle deterministik olur (refresh-də dəyişmir).
    """
    letters = ["A", "B", "C", "D", "E", "F"]

    qs = (
        ExamQuestionOption.objects
        .filter(question=eq)
        .order_by("id")  # baza stabil olsun
    )

    opts = list(qs)

    rnd = random.Random(seed) if seed is not None else random
    rnd.shuffle(opts)

    out = []
    for i, opt in enumerate(opts):
        label = _get_option_label(opt) or (letters[i] if i < len(letters) else str(i + 1))
        text = _get_option_text(opt) or f"Variant {label}"
        out.append({"id": opt.id, "label": label, "text": text})
    return out


def _detect_multi(eq: ExamQuestion) -> Tuple[bool, int, List[int]]:
    """
    Multi sualı aşkarlayır:
    - eq.is_multiple / eq.multi_choice / eq.allow_multiple varsa onları da yoxlayır
    - yoxdursa correct_count > 1 => multi

    max_select:
    - eq.max_select varsa götür
    - yoxdursa correct_count
    """
    correct_ids = list(
        ExamQuestionOption.objects
        .filter(question=eq, is_correct=True)
        .values_list("id", flat=True)
    )
    correct_count = len(correct_ids)

    flags = [
        bool(getattr(eq, "is_multiple", False)),
        bool(getattr(eq, "multi_choice", False)),
        bool(getattr(eq, "allow_multiple", False)),
    ]
    multi = any(flags) or (correct_count > 1)

    if multi:
        max_select = _safe_int(getattr(eq, "max_select", 0), 0)
        if max_select <= 1:
            max_select = max(2, correct_count)  # ən az 2
    else:
        max_select = 1

    return multi, max_select, correct_ids


# ------------------------
# Payload builders
# ------------------------

def _build_question_payload(session: LiveSession, eq: ExamQuestion, idx: int, total: int):
    time_limit = _question_time_limit(session, eq)
    now = timezone.now()
    ends = now + timezone.timedelta(seconds=time_limit)

    multi, max_select, correct_ids = _detect_multi(eq)

    # ✅ deterministik shuffle seed
    seed = _options_seed(session.pin, eq.id, now)

    payload = {
        "type": "question_published",
        "question": {
            "id": eq.id,
            "text": _get_question_text(eq),
            "time_limit": time_limit,
            "points": _question_points(session, eq),
            "multi": multi,
            "max_select": max_select,

            # ✅ qarışdırılmış options
            "options": _build_options(eq, seed=seed),

            "started_at": now.isoformat(),
            "ends_at": ends.isoformat(),
            "index": _safe_int(idx, 0) + 1,
            "total": _safe_int(total, 0),
        }
    }
    return payload, now, ends


def _build_reveal_payload(session: LiveSession, question_id: int) -> Dict[str, Any]:
    """
    reveal event-i üçün yığcam payload.
    """
    eq = ExamQuestion.objects.filter(exam=session.exam, id=question_id).first()
    if not eq:
        return {"type": "error", "message": "Question not found"}

    _, _, correct_ids = _detect_multi(eq)

    return {
        "type": "reveal",
        "question_id": question_id,
        "correct_option_ids": correct_ids,
        "results": _serialize_question_results(session, question_id, limit=50),
        "top": _serialize_top(session, limit=10),
    }


# ------------------------
# Multi scoring helper (consumer üçün)
# ------------------------

def _score_multi_fraction(
    chosen_ids: List[int],
    correct_ids: List[int],
    *,
    mode: str = "strict",  # "strict" | "partial"
) -> float:
    """
    Consumer-də istifadə edəcəksən.

    strict:
      - səhv seçimi varsa => 0
      - hamısı düz seçilibsə => 1, yoxsa 0
    partial:
      - T = düz seçilənlərin sayı
      - W = səhv seçilənlərin sayı
      - C = correct_ids sayı
      - fraction = max(0, (T - W) / C)
    """
    chosen = set(int(x) for x in (chosen_ids or []))
    correct = set(int(x) for x in (correct_ids or []))
    if not correct:
        return 0.0

    T = len(chosen & correct)
    W = len(chosen - correct)
    C = len(correct)

    if mode == "strict":
        if W > 0:
            return 0.0
        return 1.0 if T == C else 0.0

    # partial default
    return max(0.0, (T - W) / float(C))
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

    host = getattr(settings, "LAN_HOST", None) or request.get_host()
    join_url = f"http://{host}{reverse('liveExam:join_page', kwargs={'pin': session.pin})}"

    exam_total = ExamQuestion.objects.filter(exam=session.exam).count()

    selected = _get_total_questions(session)  # səndə necə hesablanırsa
    # ✅ təhlükəsizlik: selected max-dan böyük ola bilməsin
    if exam_total > 0:
        selected = max(1, min(selected, exam_total))
    else:
        selected = 0

    context = {
        "session": session,
        "join_url": join_url,
        "qr_url": reverse("liveExam:qr_png", kwargs={"pin": session.pin}),
        "total_questions": selected,
        "exam_total_questions": exam_total,
        "selected_total_questions": selected,
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


# def live_qr_png(request, pin):
#     session = get_object_or_404(LiveSession, pin=pin)
#     join_url = request.build_absolute_uri(
#         reverse("liveExam:join_page", kwargs={"pin": session.pin})
#     )

#     img = qrcode.make(join_url)
#     buf = io.BytesIO()
#     img.save(buf, format="PNG")
#     return HttpResponse(buf.getvalue(), content_type="image/png")

def live_qr_png(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    host = getattr(settings, "LAN_HOST", None) or request.get_host()
    join_url = f"http://{host}{session.join_url_path()}"

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

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


# ------------------------
# Host game controls (Kahoot flow)
# ------------------------

@require_POST
@login_required
def host_start_game(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    # 1) Host neçə sual istəyir? (form input name="question_count")
    raw = (request.POST.get("question_count") or "").strip()

    all_ids = _get_exam_question_ids(session)
    total_in_exam = len(all_ids)

    if total_in_exam <= 0:
        return JsonResponse({"ok": False, "message": "Bu imtahanda sual yoxdur."}, status=400)

    desired = None
    if raw:
        try:
            desired = int(raw)
        except Exception:
            return JsonResponse({"ok": False, "message": "Sual sayı düzgün deyil."}, status=400)

        if desired <= 0:
            return JsonResponse({"ok": False, "message": "Sual sayı 1-dən böyük olmalıdır."}, status=400)

        if desired > total_in_exam:
            return JsonResponse(
                {"ok": False, "message": f"Bu imtahanda cəmi {total_in_exam} sual var. {desired} seçilə bilməz."},
                status=400
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

    session.save(update_fields=[
        "selected_question_ids", "question_limit",
        "current_index", "state",
        "question_started_at", "question_ends_at",
    ])

    # 4) Wait room-da olan player-ları player_screen-ə yönləndir
    _broadcast(pin, {
        "type": "game_started",
        "redirect": reverse("liveExam:player_screen", kwargs={"pin": pin}),
    }, "lobby")

    # 5) Start basan kimi 1-ci sualı publish et
    eq = _get_question_by_index(session, 0)
    if not eq:
        return JsonResponse({"ok": False, "message": "Sual tapılmadı."}, status=400)

    total = _get_total_questions(session)
    payload, now, ends = _build_question_payload(session=session, eq=eq, idx=0, total=total)

    session.question_started_at = now
    session.question_ends_at = ends
    session.save(update_fields=["question_started_at", "question_ends_at"])

    _broadcast(pin, payload, "play")

    return JsonResponse({
        "ok": True,
        "published": True,
        "question_count": (desired or total_in_exam),
        "total_in_exam": total_in_exam,
    })


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
    total = _get_total_questions(session)

    eq = _get_question_by_index(session, idx)
    if eq is None:
        # sual qurtardı -> finished
        session.state = LiveSession.STATE_FINISHED
        session.save(update_fields=["state"])

        _broadcast(pin, {"type": "finished", "top": _serialize_top(session, limit=50)}, "play")
        return JsonResponse({"ok": True, "finished": True})

    payload, now, ends = _build_question_payload(session=session, eq=eq, idx=idx, total=total)

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
    if session.host_user_id != request.user.id:
        raise Http404()

    idx = int(session.current_index or 0)
    eq = _get_question_by_index(session, idx)
    if not eq:
        return JsonResponse({"ok": False, "message": "Aktiv sual tapılmadı."}, status=400)

    # ✅ multi-choice üçün: bir neçə correct ola bilər
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
        "revealed_at": timezone.now().isoformat(),
    }
    _broadcast(pin, payload, "play")

    return JsonResponse({"ok": True, "question_id": eq.id})


@require_POST
@login_required
def host_finish(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    if session.host_user_id != request.user.id:
        raise Http404()

    session.state = LiveSession.STATE_FINISHED
    session.save(update_fields=["state"])

    payload = {
        "type": "finished",
        "top": _serialize_top(session, limit=50),
        "finished_at": timezone.now().isoformat(),
    }
    _broadcast(pin, payload, "play")

    return JsonResponse({"ok": True})