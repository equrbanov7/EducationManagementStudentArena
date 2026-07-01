"""live_exam player paketi — wait."""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.live_exam.auth import clean_nickname, get_request_player
from apps.live_exam.constants import (
    ACCESSORY_KEYS,
    AVATAR_KEYS,
    DEFAULT_ACCESSORY_KEY,
    DEFAULT_AVATAR_KEY,
    REACTION_KEYS,
    build_wait_room_catalog,
)
from apps.live_exam.models import LiveSession
from apps.live_exam.serializers import serialize_player_identity, serialize_players
from apps.live_exam.session_settings import get_session_settings
from apps.live_exam.transport import broadcast, build_reaction_event_payload
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls

from ._shared import (
    _broadcast_lobby_state,
    _nickname_conflict_message,
    _nickname_is_taken,
)
from .constants import (
    LIVE_REACTION_LIMIT_SCOPE,
    REACTION_EMOJI,
)


def live_wait_room(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None:
            return redirect("liveExam:join_page", pin=pin)
        if session.state != LiveSession.STATE_LOBBY:
            return redirect("liveExam:player_screen", pin=pin)

        players = serialize_players(session)
    return render(
        request,
        "liveExam/wait_room.html",
        {
            "session": session,
            "players": players,
            "my_player": serialize_player_identity(player),
            "my_player_id": player.id,
            "player_screen_url": reverse("liveExam:player_screen", kwargs={"pin": session.pin}),
            "live_catalog": build_wait_room_catalog(),
            "session_settings": get_session_settings(session),
        },
    )


@require_POST
def live_wait_profile_update(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None or player.session_id != session.id:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
                status=403,
            )

    session_settings = get_session_settings(session)
    nickname = clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or DEFAULT_AVATAR_KEY
    accessory_key = request.POST.get("accessory_key") or DEFAULT_ACCESSORY_KEY

    if not nickname:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "nickname_required")},
            status=400,
        )
    if not session_settings.get("characters_enabled", True):
        avatar_key = DEFAULT_AVATAR_KEY
        accessory_key = DEFAULT_ACCESSORY_KEY
    elif avatar_key not in AVATAR_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_avatar")},
            status=400,
        )
    if accessory_key not in ACCESSORY_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_accessory")},
            status=400,
        )
    if _nickname_is_taken(session, nickname, exclude_player_id=player.id):
        return JsonResponse(
            {"ok": False, "message": _nickname_conflict_message()},
            status=409,
        )

    with bypass_rls():
        player.nickname = nickname
        player.avatar_key = avatar_key
        player.accessory_key = accessory_key
        player.is_connected = True
        player.last_seen = timezone.now()
        player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])

    _broadcast_lobby_state(session)

    return JsonResponse(
        {
            "ok": True,
            "player": serialize_player_identity(player),
        }
    )


@require_POST
def live_wait_reaction(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None or player.session_id != session.id:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
                status=403,
            )

    if not get_session_settings(session).get("reactions_enabled", True):
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Reactions are disabled for this live exam.")},
            status=403,
        )

    reaction_key = (request.POST.get("reaction_key") or "").strip().lower()
    if reaction_key not in REACTION_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_reaction")},
            status=400,
        )

    is_limited, retry_after = record_rate_limit_hit(
        LIVE_REACTION_LIMIT_SCOPE,
        settings.LIVE_REACTION_RATE_LIMIT,
        pin,
        player.id,
        player.client_id,
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "reaction_rate_limited")},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    created_at = timezone.now()
    broadcast(
        session.pin,
        build_reaction_event_payload(
            player=player,
            reaction_key=reaction_key,
            emoji=REACTION_EMOJI[reaction_key],
            created_at=created_at,
        ),
        "lobby",
    )

    return JsonResponse(
        {
            "ok": True,
            "reaction_key": reaction_key,
        }
    )


def live_player_screen(request, pin):
    with bypass_rls():
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
            "session_settings": get_session_settings(session),
        },
    )
