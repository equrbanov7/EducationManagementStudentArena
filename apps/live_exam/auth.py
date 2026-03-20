"""
Authentication helpers for live exam player access.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from django.core import signing

from apps.live_exam.models import LivePlayer, LiveSession

PLAYER_COOKIE_NAME = "live_player_token"
PLAYER_TOKEN_SALT = "liveExam.player"  # nosec B105
PLAYER_TOKEN_MAX_AGE = 60 * 60 * 6
LIVE_CLIENT_ID_COOKIE_NAME = "live_client_id"
LIVE_CLIENT_ID_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def clean_nickname(name: str) -> str:
    cleaned = (name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:32]


def get_client_id(request) -> str:
    client_id = request.COOKIES.get(LIVE_CLIENT_ID_COOKIE_NAME)
    return client_id or uuid.uuid4().hex


def _resolve_session_pin(session_or_pin=None, *, pin: str | None = None, session=None) -> str:
    if pin is not None and session is not None:
        raise TypeError("Use either pin= or session=, not both.")

    candidate = pin
    if candidate is None and session is not None:
        candidate = getattr(session, "pin", session)
    if candidate is None and session_or_pin is not None:
        candidate = getattr(session_or_pin, "pin", session_or_pin)
    if candidate is None:
        raise TypeError("A session or pin is required.")

    return str(candidate)


def build_player_token(
    *args, pin: str | None = None, player_id: int | None = None, client_id: str | None = None
) -> str:
    if args:
        if len(args) != 2 or any(value is not None for value in (pin, player_id, client_id)):
            raise TypeError("Use either build_player_token(player, session) or keyword arguments.")
        player, session = args
        pin = _resolve_session_pin(session)
        player_id = int(getattr(player, "id", player))
        client_id = str(getattr(player, "client_id", "") or "")

    if pin is None or player_id is None:
        raise TypeError("pin and player_id are required.")

    normalized_pin = str(pin)
    return signing.dumps(
        {
            "pin": normalized_pin,
            "session_pin": normalized_pin,
            "player_id": int(player_id),
            "client_id": str(client_id or ""),
        },
        salt=PLAYER_TOKEN_SALT,
    )


def _load_signed_player_token_payload(token: str) -> dict[str, Any] | None:
    try:
        payload = signing.loads(token, salt=PLAYER_TOKEN_SALT, max_age=PLAYER_TOKEN_MAX_AGE)
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def load_player_token_payload(
    token: str | None,
    session_or_pin=None,
    *,
    pin: str | None = None,
    session=None,
) -> dict[str, Any] | None:
    if not token:
        return None

    expected_pin = _resolve_session_pin(session_or_pin, pin=pin, session=session)
    payload = _load_signed_player_token_payload(token)
    if payload is None:
        return None

    token_pin = str(payload.get("pin") or payload.get("session_pin") or "")
    if token_pin != expected_pin:
        return None

    try:
        player_id = int(payload.get("player_id"))
    except (TypeError, ValueError):
        return None

    client_id = str(payload.get("client_id") or "").strip()
    if player_id <= 0:
        return None

    return {
        "pin": expected_pin,
        "player_id": player_id,
        "client_id": client_id,
    }


def authenticate_player_token(token: str | None, *, pin: str) -> tuple[dict[str, Any] | None, LivePlayer | None]:
    payload = load_player_token_payload(token, pin=pin)
    if payload is None:
        return None, None

    player_qs = LivePlayer.objects.select_related("session").filter(
        id=payload["player_id"],
        session__pin=str(pin),
    )
    if payload["client_id"]:
        player_qs = player_qs.filter(client_id=payload["client_id"])
    else:
        player_qs = player_qs.filter(client_id="")

    player = player_qs.first()
    if player is None:
        return None, None

    return payload, player


def get_player_from_token(token: str | None, *, pin: str) -> LivePlayer | None:
    _, player = authenticate_player_token(token, pin=pin)
    return player


def get_request_player(request, *, pin: str) -> LivePlayer | None:
    return get_player_from_token(request.COOKIES.get(PLAYER_COOKIE_NAME), pin=pin)


def authorize_socket_connection(
    *,
    pin: str,
    user_id: int | None,
    token: str | None,
    allow_anonymous: bool = False,
) -> dict[str, Any] | None:
    session = LiveSession.objects.filter(pin=pin).only("id", "host_user_id").first()
    if session is None:
        return None

    payload, player = authenticate_player_token(token, pin=pin)
    if payload is not None and player is not None:
        return {
            "role": "player",
            "player_id": player.id,
            "client_id": player.client_id,
        }

    if user_id and session.host_user_id == user_id:
        return {"role": "host"}

    if allow_anonymous:
        return {"role": "viewer"}

    return None
