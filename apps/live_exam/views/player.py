"""
live_exam/views/player.py
──────────────────────────
Player views for live exam sessions.
"""

from __future__ import annotations

import io

from django.core import signing
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

import qrcode

from apps.live_exam.models import LiveSession

from ._helpers import (
    AVATAR_KEYS,
    PLAYER_COOKIE_NAME,
    PLAYER_TOKEN_SALT,
    _broadcast,
    _build_join_url,
    _clean_nickname,
    _get_client_id,
    _serialize_players,
)


# ════════════════════════════════════════════════════════════════════════════
# Player Join / Wait / Screen
# ════════════════════════════════════════════════════════════════════════════


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

    token = signing.dumps(
        {"pin": session.pin, "player_id": player.id, "client_id": client_id},
        salt=PLAYER_TOKEN_SALT,
    )

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
        max_age=60 * 60 * 6,
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
