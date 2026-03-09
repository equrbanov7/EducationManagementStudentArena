"""
live_exam/views/player.py
──────────────────────────
Player views for live exam sessions.
"""

from __future__ import annotations

import io

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

import qrcode

from apps.live_exam.auth import (
    PLAYER_COOKIE_NAME,
    PLAYER_TOKEN_MAX_AGE,
    build_player_token,
    get_request_player,
)
from apps.live_exam.models import LiveSession

from ._helpers import (
    AVATAR_KEYS,
    _broadcast,
    _build_join_url,
    _clean_nickname,
    _get_client_id,
    _serialize_players,
)

PIN_ENTRY_COPY = {
    "az": {
        "title": "Canlı imtahana qoşul",
        "eyebrow": "EMSArena Live",
        "subtitle": "Müəllimin göstərdiyi 6 rəqəmli PIN-i yaz, sonra adını seçib oyuna daxil ol.",
        "pin_label": "Oyun PIN-i",
        "pin_placeholder": "Məsələn: 368121",
        "button": "Davam et",
        "hint": "PIN-i ekranda gördüyün kimi daxil et. Növbəti addımda ad və avatar seçəcəksən.",
        "feature_fast": "Saniyələr içində qoşul",
        "feature_device": "Telefon, planşet və kompüterdən işləyir",
        "feature_live": "Canlı nəticə və liderlik cədvəli",
        "card_title": "Hazırsan?",
        "card_subtitle": "Bir URL, bir PIN, hamısı eyni oyunda.",
        "footer_left": "Müəllim ekranında PIN və QR kod görünür.",
        "footer_right": "Daxil olduqdan sonra avatar və ad seçimi gəlir.",
        "loading": "Yoxlanılır...",
        "invalid_pin": "6 rəqəmli PIN daxil et.",
        "session_not_found": "Bu PIN tapılmadı və ya oyun bağlanıb.",
    },
    "en": {
        "title": "Join a live exam",
        "eyebrow": "EMSArena Live",
        "subtitle": "Enter the 6-digit PIN shown by the teacher, then choose your name and join the game.",
        "pin_label": "Game PIN",
        "pin_placeholder": "Example: 368121",
        "button": "Continue",
        "hint": "Type the PIN exactly as shown on screen. You will choose your nickname and avatar next.",
        "feature_fast": "Join in seconds",
        "feature_device": "Works on phone, tablet, and desktop",
        "feature_live": "Live results and leaderboard",
        "card_title": "Ready to play?",
        "card_subtitle": "One link, one PIN, everyone in the same session.",
        "footer_left": "The teacher screen shows the PIN and QR code.",
        "footer_right": "After this step, students choose nickname and avatar.",
        "loading": "Checking...",
        "invalid_pin": "Enter a 6-digit PIN.",
        "session_not_found": "This PIN was not found or the session is closed.",
    },
    "ru": {
        "title": "Присоединитесь к живому экзамену",
        "eyebrow": "EMSArena Live",
        "subtitle": "Введите 6-значный PIN, который показал преподаватель, затем выберите имя и войдите в игру.",
        "pin_label": "PIN игры",
        "pin_placeholder": "Например: 368121",
        "button": "Продолжить",
        "hint": "Введите PIN точно как на экране. На следующем шаге вы выберете ник и аватар.",
        "feature_fast": "Подключение за несколько секунд",
        "feature_device": "Работает на телефоне, планшете и компьютере",
        "feature_live": "Живые результаты и таблица лидеров",
        "card_title": "Готовы?",
        "card_subtitle": "Одна ссылка, один PIN, одна общая сессия.",
        "footer_left": "На экране преподавателя видны PIN и QR-код.",
        "footer_right": "После этого шага ученик выбирает ник и аватар.",
        "loading": "Проверяем...",
        "invalid_pin": "Введите 6-значный PIN.",
        "session_not_found": "Такой PIN не найден или сессия уже закрыта.",
    },
    "tr": {
        "title": "Canlı sınava katıl",
        "eyebrow": "EMSArena Live",
        "subtitle": "Öğretmenin gösterdiği 6 haneli PIN kodunu gir, sonra adını seçip oyuna katıl.",
        "pin_label": "Oyun PIN'i",
        "pin_placeholder": "Örnek: 368121",
        "button": "Devam et",
        "hint": "PIN kodunu ekrandaki gibi gir. Sonraki adımda rumuz ve avatar seçeceksin.",
        "feature_fast": "Saniyeler içinde katıl",
        "feature_device": "Telefon, tablet ve bilgisayarda çalışır",
        "feature_live": "Canlı sonuç ve lider tablosu",
        "card_title": "Hazır mısın?",
        "card_subtitle": "Tek link, tek PIN, herkes aynı oturumda.",
        "footer_left": "Öğretmen ekranında PIN ve QR kod görünür.",
        "footer_right": "Bu adımdan sonra öğrenci ad ve avatar seçer.",
        "loading": "Kontrol ediliyor...",
        "invalid_pin": "6 haneli bir PIN gir.",
        "session_not_found": "Bu PIN bulunamadı veya oturum kapanmış.",
    },
}


def _pin_entry_copy() -> dict[str, str]:
    lang = (get_language() or "az")[:2].lower()
    return PIN_ENTRY_COPY.get(lang, PIN_ENTRY_COPY["az"])


def _normalize_pin(raw_pin: str | None) -> str:
    return "".join(ch for ch in str(raw_pin or "") if ch.isdigit())[:6]


# ════════════════════════════════════════════════════════════════════════════
# Player Join / Wait / Screen
# ════════════════════════════════════════════════════════════════════════════


def live_pin_entry(request):
    copy = _pin_entry_copy()
    pin_value = _normalize_pin(request.POST.get("pin") if request.method == "POST" else request.GET.get("pin"))
    error_message = ""
    status_code = 200

    if request.method == "POST":
        if len(pin_value) != 6:
            error_message = copy["invalid_pin"]
            status_code = 400
        elif not LiveSession.objects.filter(pin=pin_value).exists():
            error_message = copy["session_not_found"]
            status_code = 404
        else:
            return redirect("liveExam:join_page", pin=pin_value)

    return render(
        request,
        "liveExam/pin_entry.html",
        {
            "copy": copy,
            "pin_value": pin_value,
            "error_message": error_message,
        },
        status=status_code,
    )


def live_join_page(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    context = {"session": session, "avatars": AVATAR_KEYS}
    return render(request, "liveExam/join.html", context)


@require_POST
def live_join_enter(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    if session.is_locked:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "lobby_locked")},
            status=403,
        )

    nickname = _clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or "avatar_1"
    if avatar_key not in AVATAR_KEYS:
        avatar_key = "avatar_1"

    if not nickname:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "nickname_required")},
            status=400,
        )

    client_id = _get_client_id(request)
    now = timezone.now()

    from apps.live_exam.models import LivePlayer

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

    token = build_player_token(pin=session.pin, player_id=player.id, client_id=client_id)

    # lobby-yə realtime update
    _broadcast(
        session.pin,
        {
            "type": "lobby_state",
            "count": session.players.count(),
            "players": _serialize_players(session),
        },
        "lobby",
    )

    wait_url = reverse("liveExam:wait_room", kwargs={"pin": session.pin})
    resp = JsonResponse({"ok": True, "redirect": wait_url})

    # Set cookies with appropriate security flags
    resp.set_cookie("live_client_id", client_id, max_age=60 * 60 * 24 * 30, samesite="Lax", secure=request.is_secure())
    resp.set_cookie(
        PLAYER_COOKIE_NAME,
        token,
        max_age=PLAYER_TOKEN_MAX_AGE,
        samesite="Lax",
        httponly=True,
        secure=request.is_secure(),
    )

    return resp


def live_qr_png(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)

    join_url = _build_join_url(request, session)

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    from django.http import HttpResponse

    return HttpResponse(buf.getvalue(), content_type="image/png")


def live_wait_room(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    player = get_request_player(request, pin=pin)
    if player is None:
        return redirect("liveExam:join_page", pin=pin)

    players = _serialize_players(session)
    return render(
        request,
        "liveExam/wait_room.html",
        {
            "session": session,
            "players": players,
            "my_nickname": player.nickname,
            "my_avatar_key": player.avatar_key,
            "player_screen_url": reverse("liveExam:player_screen", kwargs={"pin": session.pin}),
        },
    )


def live_player_screen(request, pin):
    session = get_object_or_404(LiveSession, pin=pin)
    player = get_request_player(request, pin=pin)
    if player is None:
        return redirect("liveExam:join_page", pin=pin)

    return render(
        request,
        "liveExam/player_screen.html",
        {
            "session": session,
            "player": player,
        },
    )
