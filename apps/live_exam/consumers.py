# liveExam/consumers.py

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils.translation import pgettext

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.live_exam.auth import (
    LIVE_CLIENT_ID_COOKIE_NAME,
    PLAYER_COOKIE_NAME,
    authorize_socket_connection,
    load_player_token_payload,
)
from apps.live_exam.models import LiveSession
from apps.live_exam.scoring import get_answer_progress, save_answer_and_score
from apps.live_exam.transport import (
    build_answer_progress_payload,
    build_lobby_state_payload,
    build_player_reveal_payload,
    build_reveal_payload,
    parse_answer_submission,
)
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls

logger = logging.getLogger("live_exam.ws.rate_limit")

# Rate limit scope identifiers
_WS_CONNECT_SCOPE = "live_exam.ws.connect"
_WS_MSG_SCOPE = "live_exam.ws.message"
_WS_ANSWER_SCOPE = "live_exam.ws.answer"

# Async wrapper for the synchronous rate limit helper
_record_rate_limit_hit = sync_to_async(record_rate_limit_hit, thread_sensitive=False)


def _get_scope_ip(scope) -> str:
    """Extract client IP from the ASGI WebSocket scope."""
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and len(client) >= 1:
        return str(client[0])
    return "unknown"


def _get_connect_rate_identity(scope, pin: str) -> str:
    """
    Build a stable per-client rate-limit identity for WebSocket connects.

    Using only IP+PIN is too aggressive for classrooms where many students
    share the same NAT IP. Prefer a per-player token / live client cookie and
    fall back to the authenticated user or source IP only when no better
    identifier exists.
    """
    cookies = scope.get("cookies") or {}

    token_payload = load_player_token_payload(cookies.get(PLAYER_COOKIE_NAME), pin=pin)
    if token_payload is not None:
        client_id = str(token_payload.get("client_id") or "").strip()
        if client_id:
            return f"player-client:{client_id}"
        player_id = token_payload.get("player_id")
        if player_id:
            return f"player:{player_id}"

    live_client_id = str(cookies.get(LIVE_CLIENT_ID_COOKIE_NAME) or "").strip()
    if live_client_id:
        return f"viewer-client:{live_client_id}"

    user = scope.get("user")
    if getattr(user, "is_authenticated", False):
        return f"user:{user.id}"

    return f"ip:{_get_scope_ip(scope)}"


class LiveSessionSocketAuthMixin:
    @database_sync_to_async
    def _authorize_connection(
        self,
        pin: str,
        user_id: int | None,
        token: str | None,
        *,
        allow_anonymous: bool = False,
    ) -> dict[str, Any] | None:
        return authorize_socket_connection(pin=pin, user_id=user_id, token=token, allow_anonymous=allow_anonymous)


# -------------------------
# Lobby consumer
# -------------------------


class LiveLobbyConsumer(LiveSessionSocketAuthMixin, AsyncJsonWebsocketConsumer):
    """
    Wait room / lobby websocket:
    - connect olanda hazırkı players listini göndərir
    - view tərəfdən group_send gələndə realtime update edir
    Group: live_<pin>_lobby
    """

    async def connect(self):
        self.pin = self.scope["url_route"]["kwargs"]["pin"]
        self.group_name = f"live_{self.pin}_lobby"
        connect_identity = _get_connect_rate_identity(self.scope, self.pin)

        # Rate-limit reconnect flooding per client identity within the PIN.
        is_limited, retry_after = await _record_rate_limit_hit(
            _WS_CONNECT_SCOPE,
            settings.LIVE_WS_CONNECT_RATE_LIMIT,
            self.pin,
            connect_identity,
        )
        if is_limited:
            logger.warning(
                "WebSocket connect flood blocked on lobby",
                extra={"pin": self.pin, "connect_identity": connect_identity, "retry_after": retry_after},
            )
            await self.close(code=4429)
            return

        user = self.scope.get("user")
        user_id = user.id if getattr(user, "is_authenticated", False) else None
        token = (self.scope.get("cookies") or {}).get(PLAYER_COOKIE_NAME)

        self.auth_context = await self._authorize_connection(self.pin, user_id, token, allow_anonymous=True)
        if self.auth_context is None:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # ilk açılan kimi state göndər
        state = await self._get_lobby_state(self.pin)
        await self.send_json(state)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def lobby_event(self, event):
        # view -> group_send(..., {"type":"lobby_event","data":{...}})
        data = event.get("data") or {}
        await self.send_json(data)

    @database_sync_to_async
    def _get_lobby_state(self, pin: str) -> dict:
        with bypass_rls():
            session = LiveSession.objects.get(pin=pin)
            return build_lobby_state_payload(session)


# -------------------------
# Play consumer
# -------------------------


class LivePlayConsumer(LiveSessionSocketAuthMixin, AsyncJsonWebsocketConsumer):
    """
    Oyun websocket:
    - client 'answer' göndərir
    - cookie token ilə player-i tanıyır
    - cavabı saxlayır və score artırır
    - sonra answer_progress broadcast edir (hamı cavab veribsə host auto-reveal edə bilsin)
    Group: live_<pin>_play
    """

    async def connect(self):
        self.pin = self.scope["url_route"]["kwargs"]["pin"]
        connect_identity = _get_connect_rate_identity(self.scope, self.pin)

        # Rate-limit reconnect flooding per client identity within the PIN.
        is_limited, retry_after = await _record_rate_limit_hit(
            _WS_CONNECT_SCOPE,
            settings.LIVE_WS_CONNECT_RATE_LIMIT,
            self.pin,
            connect_identity,
        )
        if is_limited:
            logger.warning(
                "WebSocket connect flood blocked on play",
                extra={"pin": self.pin, "connect_identity": connect_identity, "retry_after": retry_after},
            )
            await self.close(code=4429)
            return

        user = self.scope.get("user")
        user_id = user.id if getattr(user, "is_authenticated", False) else None
        token = (self.scope.get("cookies") or {}).get(PLAYER_COOKIE_NAME)

        self.auth_context = await self._authorize_connection(self.pin, user_id, token)
        self.player_auth = self.auth_context if self.auth_context and self.auth_context["role"] == "player" else None
        if self.auth_context is None:
            await self.close(code=4401)
            return

        # Host and players join separate channel-layer groups so that
        # host-only events (e.g. answer_progress) never reach players.
        role = self.auth_context.get("role")
        if role == "host":
            self.play_group = f"live_{self.pin}_play_host"
        else:
            self.play_group = f"live_{self.pin}_play_players"

        await self.channel_layer.group_add(self.play_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        play_group = getattr(self, "play_group", None)
        if play_group:
            await self.channel_layer.group_discard(play_group, self.channel_name)

    async def receive_json(self, data, **kwargs):
        # Per-connection general message rate limit (flood protection)
        player_key = self._rate_limit_key()
        is_msg_limited, msg_retry_after = await _record_rate_limit_hit(
            _WS_MSG_SCOPE,
            settings.LIVE_WS_MSG_RATE_LIMIT,
            self.pin,
            player_key,
        )
        if is_msg_limited:
            logger.warning(
                "WebSocket message flood blocked",
                extra={"pin": self.pin, "player_key": player_key, "retry_after": msg_retry_after},
            )
            await self.send_json({"type": "error", "message": pgettext("live_exam.consumer.error", "rate_limited")})
            return

        if (data or {}).get("type") != "answer":
            return

        if self.player_auth is None:
            await self.send_json({"type": "error", "message": pgettext("live_exam.consumer.error", "auth_required")})
            return

        # Per-player answer submission rate limit
        is_answer_limited, answer_retry_after = await _record_rate_limit_hit(
            _WS_ANSWER_SCOPE,
            settings.LIVE_ANSWER_RATE_LIMIT,
            self.pin,
            self.player_auth["player_id"],
        )
        if is_answer_limited:
            logger.warning(
                "WebSocket answer flood blocked",
                extra={
                    "pin": self.pin,
                    "player_id": self.player_auth["player_id"],
                    "retry_after": answer_retry_after,
                },
            )
            await self.send_json({"type": "error", "message": pgettext("live_exam.consumer.error", "rate_limited")})
            return

        # 1) parse payload
        ok, parsed_or_msg = parse_answer_submission(data)
        if not ok:
            await self.send_json({"type": "error", "message": parsed_or_msg})
            return

        question_id, option_ids, answer_ms = parsed_or_msg

        # 3) save + score
        ok, result = await self._save_answer_and_score(
            pin=self.pin,
            player_id=self.player_auth["player_id"],
            client_id=self.player_auth["client_id"],
            question_id=question_id,
            option_ids=option_ids,
            answer_ms=answer_ms,
        )
        if not ok:
            await self.send_json({"type": "error", "message": result})
            return

        await self.send_json({"type": "answer_saved", **result["answer"]})

        # 4) progress -> host group only (players do not need this; host uses it for auto-reveal)
        # Reuse counts computed during scoring when available (saves 3 queries);
        # the "already answered" branch falls back to a fresh count.
        prog = result.get("progress") or await self._get_answer_progress(self.pin, result["question_id"])
        await self.channel_layer.group_send(
            f"live_{self.pin}_play_host",
            {
                "type": "play_event",
                "data": build_answer_progress_payload(
                    question_id=prog["question_id"],
                    answered_count=prog["answered_count"],
                    total_players=prog["total_players"],
                ),
            },
        )

        if result.get("reveal_question_id"):
            # Send host-specific reveal (includes per-player results) to host group
            host_reveal = await self._get_reveal_payload(self.pin, result["reveal_question_id"])
            await self.channel_layer.group_send(
                f"live_{self.pin}_play_host",
                {"type": "play_event", "data": host_reveal},
            )
            # Send player-appropriate reveal (correct_option_ids visible at reveal stage,
            # but without per-player result details) to the players group
            player_reveal = await self._get_player_reveal_payload(self.pin, result["reveal_question_id"])
            await self.channel_layer.group_send(
                f"live_{self.pin}_play_players",
                {"type": "play_event", "data": player_reveal},
            )

    def _rate_limit_key(self) -> str:
        """Stable per-connection key for message rate limiting."""
        if self.player_auth:
            return f"player:{self.player_auth['player_id']}"
        if getattr(self, "auth_context", None):
            role = self.auth_context.get("role", "unknown")
            return f"{role}:{self.channel_name}"
        return self.channel_name

    async def play_event(self, event):
        # view -> group_send(... {"type":"play_event","data":{...}})
        await self.send_json(event.get("data") or {})

    @database_sync_to_async
    def _get_answer_progress(self, pin: str, question_id: int) -> dict:
        return get_answer_progress(pin=pin, question_id=question_id)

    @database_sync_to_async
    def _get_reveal_payload(self, pin: str, question_id: int) -> dict:
        with bypass_rls():
            session = LiveSession.objects.get(pin=pin)
            return build_reveal_payload(session, question_id)

    @database_sync_to_async
    def _get_player_reveal_payload(self, pin: str, question_id: int) -> dict:
        with bypass_rls():
            session = LiveSession.objects.get(pin=pin)
            return build_player_reveal_payload(session, question_id)

    @database_sync_to_async
    def _save_answer_and_score(self, pin, player_id, client_id, question_id, option_ids, answer_ms):
        return save_answer_and_score(
            pin=pin,
            player_id=player_id,
            client_id=client_id,
            question_id=question_id,
            option_ids=option_ids,
            answer_ms=answer_ms,
        )
