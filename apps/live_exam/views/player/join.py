"""live_exam player paketi — join."""

import io

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
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
    get_request_player,
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
from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.rls import bypass_rls

from ._shared import (
    _broadcast_lobby_state,
    _ensure_live_client_cookie,
    _join_resume_copy,
    _live_client_id_key,
    _nickname_conflict_message,
    _pin_entry_copy,
    _pin_entry_theme_key,
    _random_join_accessory_key,
    _random_join_avatar_key,
    _resolve_live_session,
)
from .constants import (
    LIVE_JOIN_LIMIT_SCOPE,
    LIVE_PIN_LIMIT_SCOPE,
    LIVE_RATE_LIMIT_MESSAGE,
)


@never_cache
def live_pin_entry(request):
    from apps.live_exam.models import MIN_PIN_LENGTH, PIN_LENGTH

    copy = _pin_entry_copy()
    pin_value, matched_session = _resolve_live_session(
        request.POST.get("pin") if request.method == "POST" else request.GET.get("pin")
    )
    raw_theme = request.POST.get("theme") if request.method == "POST" else request.GET.get("theme")
    theme_key = _pin_entry_theme_key(pin_value, raw_theme)
    error_message = ""
    status_code = 200
    session_exists = matched_session is not None

    if request.method != "POST" and session_exists:
        return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=matched_session.pin))

    if request.method == "POST":
        is_limited, retry_after = is_rate_limited(
            LIVE_PIN_LIMIT_SCOPE,
            settings.LIVE_EXAM_JOIN_RATE_LIMIT,
            _live_client_id_key(request),
        )
        if is_limited:
            response = render(
                request,
                "liveExam/pin_entry.html",
                {
                    "copy": copy,
                    "pin_value": pin_value,
                    "pin_length": PIN_LENGTH,
                    "pin_slots": range(1, PIN_LENGTH + 1),
                    "min_pin_length": MIN_PIN_LENGTH,
                    "error_message": LIVE_RATE_LIMIT_MESSAGE,
                    "theme_key": theme_key,
                },
                status=429,
            )
            if retry_after:
                response.headers["Retry-After"] = str(retry_after)
            return _ensure_live_client_cookie(request, response)

        if len(pin_value) < MIN_PIN_LENGTH:
            record_rate_limit_hit(
                LIVE_PIN_LIMIT_SCOPE,
                settings.LIVE_EXAM_JOIN_RATE_LIMIT,
                _live_client_id_key(request),
            )
            error_message = copy["invalid_pin"]
            status_code = 400
        elif not session_exists:
            record_rate_limit_hit(
                LIVE_PIN_LIMIT_SCOPE,
                settings.LIVE_EXAM_JOIN_RATE_LIMIT,
                _live_client_id_key(request),
            )
            error_message = copy["session_not_found"]
            status_code = 404
        else:
            return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=matched_session.pin))

    response = render(
        request,
        "liveExam/pin_entry.html",
        {
            "copy": copy,
            "pin_value": pin_value,
            "pin_length": PIN_LENGTH,
            "pin_slots": range(1, PIN_LENGTH + 1),
            "min_pin_length": MIN_PIN_LENGTH,
            "error_message": error_message,
            "theme_key": theme_key,
        },
        status=status_code,
    )
    return _ensure_live_client_cookie(request, response)


@never_cache
def live_join_page(request, pin):
    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
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


@require_POST
def live_join_enter(request, pin):
    is_limited, retry_after = record_rate_limit_hit(
        LIVE_JOIN_LIMIT_SCOPE,
        settings.LIVE_EXAM_JOIN_RATE_LIMIT,
        pin,
        _live_client_id_key(request),
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": LIVE_RATE_LIMIT_MESSAGE},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
        raise Http404()
    session_settings = get_session_settings(session)

    if session.is_locked:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "lobby_locked")},
            status=403,
        )

    nickname = clean_nickname(request.POST.get("nickname"))
    if not nickname and session_settings.get("nickname_generator"):
        nickname = generate_guest_nickname()

    characters_enabled = bool(session_settings.get("characters_enabled", True))
    avatar_key = request.POST.get("avatar_key") or ""
    accessory_key = request.POST.get("accessory_key") or ""
    if not characters_enabled:
        avatar_key = DEFAULT_AVATAR_KEY
        accessory_key = DEFAULT_ACCESSORY_KEY
    else:
        if avatar_key not in AVATAR_KEYS:
            avatar_key = _random_join_avatar_key()
        if accessory_key not in ACCESSORY_KEYS:
            accessory_key = _random_join_accessory_key()

    if not nickname:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "nickname_required")},
            status=400,
        )

    client_id = get_client_id(request)
    now = timezone.now()
    max_participants = max(1, int(session_settings.get("max_participants", DEFAULT_MAX_PARTICIPANTS) or 0))

    with bypass_rls():
        with transaction.atomic():
            locked_session = LiveSession.objects.select_for_update().get(pk=session.pk)
            player = LivePlayer.objects.select_for_update().filter(session=locked_session, client_id=client_id).first()

            if player is None and LivePlayer.objects.filter(session=locked_session).count() >= max_participants:
                return JsonResponse(
                    {
                        "ok": False,
                        "message": pgettext("live_exam.view.message", "participant_limit_reached").format(
                            limit=max_participants
                        ),
                    },
                    status=403,
                )

            nickname_conflict = (
                LivePlayer.objects.filter(session=locked_session, nickname__iexact=nickname)
                .exclude(client_id=client_id)
                .exists()
            )
            if nickname_conflict:
                return JsonResponse(
                    {"ok": False, "message": _nickname_conflict_message()},
                    status=409,
                )

            if player:
                player.nickname = nickname
                player.avatar_key = avatar_key
                player.accessory_key = accessory_key
                player.is_connected = True
                player.last_seen = now
                player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])
            else:
                try:
                    player = LivePlayer.objects.create(
                        session=locked_session,
                        client_id=client_id,
                        nickname=nickname,
                        avatar_key=avatar_key,
                        accessory_key=accessory_key,
                        is_connected=True,
                        last_seen=now,
                    )
                except IntegrityError:
                    player = (
                        LivePlayer.objects.select_for_update()
                        .filter(
                            session=locked_session,
                            client_id=client_id,
                        )
                        .first()
                    )
                    if player is None:
                        raise

                    player.nickname = nickname
                    player.avatar_key = avatar_key
                    player.accessory_key = accessory_key
                    player.is_connected = True
                    player.last_seen = now
                    player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])

    token = build_player_token(pin=session.pin, player_id=player.id, client_id=client_id)

    _broadcast_lobby_state(session)

    wait_url = reverse("liveExam:wait_room", kwargs={"pin": session.pin})
    resp = JsonResponse({"ok": True, "redirect": wait_url})

    # Set cookies with appropriate security flags
    resp.set_cookie(
        LIVE_CLIENT_ID_COOKIE_NAME,
        client_id,
        max_age=LIVE_CLIENT_ID_COOKIE_MAX_AGE,
        samesite="Lax",
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

    from django.http import HttpResponse

    return HttpResponse(buf.getvalue(), content_type="image/png")
