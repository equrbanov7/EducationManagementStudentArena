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
PLAYER_TOKEN_SALT = "liveExam.player"
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


def build_player_token(*, pin: str, player_id: int, client_id: str) -> str:
    return signing.dumps(
        {
            "pin": str(pin),
            "player_id": int(player_id),
            "client_id": str(client_id),
        },
        salt=PLAYER_TOKEN_SALT,
    )


def load_player_token_payload(token: str | None, *, pin: str) -> dict[str, Any] | None:
    if not token:
        return None

    try:
        payload = signing.loads(token, salt=PLAYER_TOKEN_SALT, max_age=PLAYER_TOKEN_MAX_AGE)
    except Exception:
        return None

    if str(payload.get("pin")) != str(pin):
        return None

    try:
        player_id = int(payload.get("player_id"))
    except (TypeError, ValueError):
        return None

    client_id = str(payload.get("client_id") or "").strip()
    if player_id <= 0 or not client_id:
        return None

    return {
        "pin": str(pin),
        "player_id": player_id,
        "client_id": client_id,
    }


def authenticate_player_token(token: str | None, *, pin: str) -> tuple[dict[str, Any] | None, LivePlayer | None]:
    payload = load_player_token_payload(token, pin=pin)
    if payload is None:
        return None, None

    player = (
        LivePlayer.objects.select_related("session")
        .filter(
            id=payload["player_id"],
            session__pin=str(pin),
            client_id=payload["client_id"],
        )
        .first()
    )
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
