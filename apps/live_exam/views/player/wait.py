"""live_exam player paketi — wait."""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.live_exam.auth import clean_nickname, get_request_player, has_signed_player_token
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
from apps.live_exam.text_safety import screen_nickname
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
    LIVE_REACTION_SESSION_LIMIT_SCOPE,
    LIVE_REACTION_SESSION_RATE_LIMIT_DEFAULT,
    REACTION_EMOJI,
)


def _signed_player(request, pin):
    """İmzalı token → oyunçu (``player.session`` ilə) və ya ``None``.

    Audit 2026-09-28 LXS-06: token PIN-ə bağlı imzadır — ƏVVƏL o yoxlanılır, sonra
    DB. Əvvəl sessiya PIN-lə axtarılıb 404 verilirdi: mövcud olmayan PIN-ə 404,
    mövcuda 302/403 — limitsiz PIN orakulu idi. İndi token-siz cavab eynidir.
    """
    if not has_signed_player_token(request, pin=pin):
        return None
    with bypass_rls():
        return get_request_player(request, pin=pin)


def _auth_required():
    return JsonResponse(
        {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
        status=403,
    )


def _json_error(message, status):
    return JsonResponse({"ok": False, "message": message}, status=status)


def live_wait_room(request, pin):
    player = _signed_player(request, pin)
    if player is None:
        return redirect("liveExam:join_page", pin=pin)
    session = player.session
    if session.state != LiveSession.STATE_LOBBY:
        return redirect("liveExam:player_screen", pin=pin)

    with bypass_rls():
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
    player = _signed_player(request, pin)
    if player is None:
        return _auth_required()
    session = player.session

    # Audit 2026-09-28 LXS-07: profil yalnız lobbidə dəyişir — əvvəl oyun gedişində
    # və BİTƏNDƏN sonra da ad dəyişirdi (host-un yoxladığı ad nəticə səhifəsində əvəzlənirdi).
    if session.state != LiveSession.STATE_LOBBY:
        return _json_error(pgettext("live_exam.view.message", "profile_changes_lobby_only"), 409)

    session_settings = get_session_settings(session)
    nickname = clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or DEFAULT_AVATAR_KEY
    accessory_key = request.POST.get("accessory_key") or DEFAULT_ACCESSORY_KEY

    if not nickname:
        return _json_error(pgettext("live_exam.view.message", "nickname_required"), 400)
    # Kilidli lobbidə ad dondurulur (host adları yoxlayıb kilidləyir); avatar dəyişə bilər.
    if session.is_locked and nickname != player.nickname:
        return _json_error(pgettext("live_exam.view.message", "nickname_locked"), 403)
    if not session_settings.get("characters_enabled", True):
        avatar_key = DEFAULT_AVATAR_KEY
        accessory_key = DEFAULT_ACCESSORY_KEY
    elif avatar_key not in AVATAR_KEYS:
        return _json_error(pgettext("live_exam.view.message", "invalid_avatar"), 400)
    if accessory_key not in ACCESSORY_KEYS:
        return _json_error(pgettext("live_exam.view.message", "invalid_accessory"), 400)
    if _nickname_is_taken(session, nickname, exclude_player_id=player.id):
        return _json_error(_nickname_conflict_message(), 409)
    # Sahib 2026-09-30: yalnız DƏYİŞƏN ad yoxlanır; nalayiq ad rədd + audit (IP + live_client_id).
    if nickname != player.nickname:
        rejection = screen_nickname(request, nickname, session=session, client_id=player.client_id, stage="wait")
        if rejection is not None:
            return _json_error(rejection.message, rejection.status)

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


def _reaction_rate_limited(pin, player):
    """``(limited, retry_after)`` — oyunçu başına, sonra sessiya üzrə tavan (LXS-11)."""
    limited, retry_after = record_rate_limit_hit(
        LIVE_REACTION_LIMIT_SCOPE,
        settings.LIVE_REACTION_RATE_LIMIT,
        pin,
        player.id,
        player.client_id,
    )
    if limited:
        return limited, retry_after
    session_rate = getattr(settings, "LIVE_REACTION_SESSION_RATE_LIMIT", LIVE_REACTION_SESSION_RATE_LIMIT_DEFAULT)
    return record_rate_limit_hit(LIVE_REACTION_SESSION_LIMIT_SCOPE, session_rate, pin)


@require_POST
def live_wait_reaction(request, pin):
    player = _signed_player(request, pin)
    if player is None:
        return _auth_required()
    session = player.session

    # Reaksiya paneli yalnız gözləmə otağındadır; oyun gedişində / bitəndən sonra
    # host ekranına reaksiya «spam»-ı göndərilməsin (Audit 2026-09-28 LXS-11).
    if session.state != LiveSession.STATE_LOBBY:
        return _json_error(pgettext("live_exam.view.message", "reactions_lobby_only"), 409)

    if not get_session_settings(session).get("reactions_enabled", True):
        return _json_error(pgettext("live_exam.view.message", "Reactions are disabled for this live exam."), 403)

    reaction_key = (request.POST.get("reaction_key") or "").strip().lower()
    if reaction_key not in REACTION_KEYS:
        return _json_error(pgettext("live_exam.view.message", "invalid_reaction"), 400)

    is_limited, retry_after = _reaction_rate_limited(session.pin, player)
    if is_limited:
        response = _json_error(pgettext("live_exam.view.message", "reaction_rate_limited"), 429)
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
    player = _signed_player(request, pin)
    if player is None:
        return redirect("liveExam:join_page", pin=pin)
    session = player.session

    return render(
        request,
        "liveExam/player_screen.html",
        {
            "session": session,
            "player": player,
            "session_settings": get_session_settings(session),
        },
    )
