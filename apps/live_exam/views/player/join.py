"""live_exam player paketi — join."""

import io

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

import qrcode

from apps.live_exam.auth import (
    LIVE_CLIENT_ID_COOKIE_MAX_AGE,
    LIVE_CLIENT_ID_COOKIE_NAME,
    PLAYER_COOKIE_NAME,
    PLAYER_TOKEN_MAX_AGE,
    build_player_token,
    clean_nickname,
    get_client_id,
    get_request_client_id,
    get_request_player,
    has_signed_player_token,
    is_client_kicked,
)
from apps.live_exam.constants import (
    ACCESSORY_KEYS,
    AVATAR_KEYS,
    DEFAULT_ACCESSORY_KEY,
    DEFAULT_AVATAR_KEY,
    build_wait_room_catalog,
)
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.serializers import serialize_player_identity
from apps.live_exam.session_settings import DEFAULT_MAX_PARTICIPANTS, generate_guest_nickname, get_session_settings
from apps.live_exam.transport import build_join_url
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls

from ._shared import (
    _broadcast_lobby_state,
    _ensure_live_client_cookie,
    _join_resume_copy,
    _live_ip_key,
    _nickname_conflict_message,
    _nickname_is_taken,
    _normalize_pin,
    _pin_entry_copy,
    _pin_entry_theme_key,
    _random_join_accessory_key,
    _random_join_avatar_key,
    _resolve_live_session,
    pin_lookup_limited,
    record_pin_miss,
)
from .constants import (
    LIVE_JOIN_IP_LIMIT_SCOPE,
    LIVE_JOIN_IP_RATE_LIMIT_DEFAULT,
    LIVE_JOIN_LIMIT_SCOPE,
    LIVE_RATE_LIMIT_MESSAGE,
)


def _join_ip_rate():
    return getattr(settings, "LIVE_EXAM_JOIN_IP_RATE_LIMIT", LIVE_JOIN_IP_RATE_LIMIT_DEFAULT)


def _json_error(message, status, *, retry_after=None):
    response = JsonResponse({"ok": False, "message": message}, status=status)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


def _render_pin_entry(request, *, pin_value, error_message="", theme_key="aurora", status=200, retry_after=None):
    from apps.live_exam.models import MIN_PIN_LENGTH, PIN_LENGTH

    response = render(
        request,
        "liveExam/pin_entry.html",
        {
            "copy": _pin_entry_copy(),
            "pin_value": pin_value,
            "pin_length": PIN_LENGTH,
            "pin_slots": range(1, PIN_LENGTH + 1),
            "min_pin_length": MIN_PIN_LENGTH,
            "error_message": error_message,
            "theme_key": theme_key,
        },
        status=status,
    )
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return _ensure_live_client_cookie(request, response)


@never_cache
def live_pin_entry(request):
    from apps.live_exam.models import MIN_PIN_LENGTH

    copy = _pin_entry_copy()
    is_post = request.method == "POST"
    raw_pin = request.POST.get("pin") if is_post else request.GET.get("pin")
    raw_theme = request.POST.get("theme") if is_post else request.GET.get("theme")
    pin_value = _normalize_pin(raw_pin)
    is_lookup = is_post or bool(raw_pin)

    # Audit 2026-09-28 LXS-06: büdcə bitibsə PIN ümumiyyətlə HƏLL OLUNMUR — əvvəl
    # POST onu həll edib 429 səhifəsində sessiyanın mövzusunu qaytarırdı (orakul).
    if is_lookup:
        limited, retry_after = pin_lookup_limited(request)
        if limited:
            return _render_pin_entry(
                request,
                pin_value=pin_value,
                error_message=LIVE_RATE_LIMIT_MESSAGE,
                theme_key=_pin_entry_theme_key(None, raw_theme),
                status=429 if is_post else 200,
                retry_after=retry_after,
            )

    pin_value, matched_session = _resolve_live_session(raw_pin) if is_lookup else (pin_value, None)
    if matched_session is not None:
        return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=matched_session.pin))

    theme_key = _pin_entry_theme_key(None, raw_theme)
    if not is_lookup:
        return _render_pin_entry(request, pin_value=pin_value, theme_key=theme_key)

    record_pin_miss(request)
    if not is_post:
        return _render_pin_entry(request, pin_value=pin_value, theme_key=theme_key)
    if len(pin_value) < MIN_PIN_LENGTH:
        return _render_pin_entry(
            request, pin_value=pin_value, error_message=copy["invalid_pin"], theme_key=theme_key, status=400
        )
    return _render_pin_entry(
        request, pin_value=pin_value, error_message=copy["session_not_found"], theme_key=theme_key, status=404
    )


@never_cache
def live_join_page(request, pin):
    # Audit 2026-09-28 LXS-06: join səhifəsi də PIN həll edir — eyni «miss» büdcəsi
    # (əvvəl limitsiz 404/200 orakulu idi). Artıq qoşulmuş (imzalı token) oyunçu kəsilmir.
    if not has_signed_player_token(request, pin=pin):
        limited, retry_after = pin_lookup_limited(request)
        if limited:
            return _render_pin_entry(
                request,
                pin_value=_normalize_pin(pin),
                error_message=LIVE_RATE_LIMIT_MESSAGE,
                status=429,
                retry_after=retry_after,
            )
    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
        record_pin_miss(request)
        raise Http404()
    if resolved_pin != pin:
        return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=resolved_pin))
    remembered_player = get_request_player(request, pin=pin)
    session_settings = get_session_settings(session)
    context = {
        "session": session,
        "avatars": AVATAR_KEYS,
        "live_catalog": build_wait_room_catalog(),
        "remembered_player": serialize_player_identity(remembered_player) if remembered_player else None,
        "remembered_join_copy": _join_resume_copy(remembered_player.nickname) if remembered_player else None,
        "resume_url": reverse("liveExam:wait_room", kwargs={"pin": session.pin}),
        "session_settings": session_settings,
        "generated_nickname": generate_guest_nickname() if session_settings.get("nickname_generator") else "",
    }
    response = render(request, "liveExam/join.html", context)
    return _ensure_live_client_cookie(request, response)


def _join_rate_limited(request, session, cookie_client_id):
    """Qoşulma vedrələri — ``(limited, retry_after)`` (Audit 2026-09-28 LXS-05).

    * per-klient sərt vedrə (pin + etibarlı cookie) — bir cihazın təkrarı;
    * pin+İP vedrəsi YALNIZ yeni oyunçu cəhdlərini sayır: artıq qəbul olunmuş
      oyunçunun reconnect-i (eyni cookie) sinfin ortaq NAT büdcəsini yemir.
    """
    if cookie_client_id:
        limited, retry_after = record_rate_limit_hit(
            LIVE_JOIN_LIMIT_SCOPE, settings.LIVE_EXAM_JOIN_RATE_LIMIT, session.pin, f"client:{cookie_client_id}"
        )
        if limited:
            return True, retry_after
        with bypass_rls():
            if LivePlayer.objects.filter(session=session, client_id=cookie_client_id).exists():
                return False, None
    return record_rate_limit_hit(LIVE_JOIN_IP_LIMIT_SCOPE, _join_ip_rate(), session.pin, _live_ip_key(request))


def _new_player_rejection(locked_session, client_id, max_participants):
    """YENİ oyunçu qəbul olunmursa JSON cavabı (kilid yalnız yenilərə aiddir — LXS-08)."""
    if locked_session.is_locked:
        return _json_error(pgettext("live_exam.view.message", "lobby_locked"), 403)
    # EXAM-P1-12: oyun lobby-dən çıxandan sonra yeni oyunçu qoşula bilməz.
    if locked_session.state != LiveSession.STATE_LOBBY:
        return _json_error(pgettext("live_exam.view.message", "game_already_started"), 403)
    # Audit 2026-09-28 LXS-09: host-un çıxardığı klient eyni cookie ilə qayıtmır.
    if is_client_kicked(locked_session, client_id):
        return _json_error(pgettext("live_exam.view.message", "removed_by_host"), 403)
    if LivePlayer.objects.filter(session=locked_session).count() >= max_participants:
        message = pgettext("live_exam.view.message", "participant_limit_reached").format(limit=max_participants)
        return _json_error(message, 403)
    return None


def _refresh_returning_player(locked_session, player, *, profile, now):
    """Qayıdan oyunçu: yalnız AÇIQ lobbidə profil dəyişir (Audit 2026-09-28 LXS-07).

    Oyun gedişində / kilidli lobbidə «reconnect» kimliyi dəyişmir — host-un
    lobbidə yoxladığı ad sonradan (liderlik cədvəlində, nəticədə) dəyişməsin.
    """
    fields = ["is_connected", "last_seen"]
    if locked_session.state == LiveSession.STATE_LOBBY and not locked_session.is_locked:
        nickname = profile["nickname"]
        if nickname != player.nickname and _nickname_is_taken(locked_session, nickname, exclude_player_id=player.id):
            return _json_error(_nickname_conflict_message(), 409)
        player.nickname = nickname
        player.avatar_key = profile["avatar_key"]
        player.accessory_key = profile["accessory_key"]
        fields += ["nickname", "avatar_key", "accessory_key"]
    player.is_connected = True
    player.last_seen = now
    player.save(update_fields=fields)
    return None


def _join_profile(request, session_settings):
    nickname = clean_nickname(request.POST.get("nickname"))
    if not nickname and session_settings.get("nickname_generator"):
        nickname = generate_guest_nickname()
    avatar_key = request.POST.get("avatar_key") or ""
    accessory_key = request.POST.get("accessory_key") or ""
    if not session_settings.get("characters_enabled", True):
        avatar_key, accessory_key = DEFAULT_AVATAR_KEY, DEFAULT_ACCESSORY_KEY
    else:
        if avatar_key not in AVATAR_KEYS:
            avatar_key = _random_join_avatar_key()
        if accessory_key not in ACCESSORY_KEYS:
            accessory_key = _random_join_accessory_key()
    return {"nickname": nickname, "avatar_key": avatar_key, "accessory_key": accessory_key}


def _admit_player(session, client_id, profile, max_participants):
    """Kilidli sessiya sətri altında qəbul — ``(player, error_response)``."""
    now = timezone.now()
    with bypass_rls(), transaction.atomic():
        locked_session = LiveSession.objects.select_for_update().get(pk=session.pk)
        player = LivePlayer.objects.select_for_update().filter(session=locked_session, client_id=client_id).first()

        # EXAM-P1-12: bitmiş oyuna heç kim qoşula bilməz (reconnect də). Yoxlamalar
        # kilid daxilindədir ki, host-un state keçidi ilə yarış olmasın.
        if locked_session.state == LiveSession.STATE_FINISHED:
            return None, _json_error(pgettext("live_exam.view.message", "session_finished"), 403)
        if player is not None:
            return player, _refresh_returning_player(locked_session, player, profile=profile, now=now)

        rejection = _new_player_rejection(locked_session, client_id, max_participants)
        if rejection is not None:
            return None, rejection
        if _nickname_is_taken(locked_session, profile["nickname"], exclude_client_id=client_id):
            return None, _json_error(_nickname_conflict_message(), 409)
        try:
            with transaction.atomic():
                player = LivePlayer.objects.create(
                    session=locked_session, client_id=client_id, is_connected=True, last_seen=now, **profile
                )
        except IntegrityError:
            player = LivePlayer.objects.select_for_update().filter(session=locked_session, client_id=client_id).first()
            if player is None:
                raise
            return player, _refresh_returning_player(locked_session, player, profile=profile, now=now)
    return player, None


@require_POST
def live_join_enter(request, pin):
    if not has_signed_player_token(request, pin=pin):
        limited, retry_after = pin_lookup_limited(request)
        if limited:
            return _json_error(LIVE_RATE_LIMIT_MESSAGE, 429, retry_after=retry_after)
    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
        record_pin_miss(request)
        raise Http404()

    cookie_client_id = get_request_client_id(request)
    limited, retry_after = _join_rate_limited(request, session, cookie_client_id)
    if limited:
        return _json_error(LIVE_RATE_LIMIT_MESSAGE, 429, retry_after=retry_after)

    session_settings = get_session_settings(session)
    profile = _join_profile(request, session_settings)
    if not profile["nickname"]:
        return _json_error(pgettext("live_exam.view.message", "nickname_required"), 400)

    client_id = cookie_client_id or get_client_id(request)
    max_participants = max(1, int(session_settings.get("max_participants", DEFAULT_MAX_PARTICIPANTS) or 0))
    player, error_response = _admit_player(session, client_id, profile, max_participants)
    if error_response is not None:
        return error_response

    token = build_player_token(pin=session.pin, player_id=player.id, client_id=client_id)

    _broadcast_lobby_state(session)

    wait_url = reverse("liveExam:wait_room", kwargs={"pin": session.pin})
    resp = JsonResponse({"ok": True, "redirect": wait_url})

    # Audit 2026-09-28 LXS-10: hər iki cookie HttpOnly (JS ``live_client_id``-ni oxumur).
    resp.set_cookie(
        LIVE_CLIENT_ID_COOKIE_NAME,
        client_id,
        max_age=LIVE_CLIENT_ID_COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=True,
        secure=request.is_secure(),
    )
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
    with bypass_rls():
        session = LiveSession.objects.filter(pin=pin).first()

    if (
        session is None
        or not getattr(request.user, "is_authenticated", False)
        or session.host_user_id != request.user.id
    ):
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    join_url = build_join_url(request, session)

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return HttpResponse(buf.getvalue(), content_type="image/png")
