# liveExam/consumers.py

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import pgettext

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.live_exam.auth import PLAYER_COOKIE_NAME, authorize_socket_connection
from apps.live_exam.models import LiveSession
from apps.live_exam.scoring import get_answer_progress, save_answer_and_score
from apps.live_exam.transport import (
    build_answer_progress_payload,
    build_lobby_state_payload,
    build_reveal_payload,
    parse_answer_submission,
)


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
        self.group_name = f"live_{self.pin}_play"
        user = self.scope.get("user")
        user_id = user.id if getattr(user, "is_authenticated", False) else None
        token = (self.scope.get("cookies") or {}).get(PLAYER_COOKIE_NAME)

        self.auth_context = await self._authorize_connection(self.pin, user_id, token)
        self.player_auth = self.auth_context if self.auth_context and self.auth_context["role"] == "player" else None
        if self.auth_context is None:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, data, **kwargs):
        if (data or {}).get("type") != "answer":
            return

        if self.player_auth is None:
            await self.send_json({"type": "error", "message": pgettext("live_exam.consumer.error", "auth_required")})
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

        # 4) progress -> group (host auto-reveal üçün)
        prog = await self._get_answer_progress(self.pin, result["question_id"])
        await self.channel_layer.group_send(
            self.group_name,
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
            reveal_payload = await self._get_reveal_payload(self.pin, result["reveal_question_id"])
            await self.channel_layer.group_send(self.group_name, {"type": "play_event", "data": reveal_payload})

    async def play_event(self, event):
        # view -> group_send(... {"type":"play_event","data":{...}})
        await self.send_json(event.get("data") or {})

    @database_sync_to_async
    def _get_answer_progress(self, pin: str, question_id: int) -> dict:
        return get_answer_progress(pin=pin, question_id=question_id)

    @database_sync_to_async
    def _get_reveal_payload(self, pin: str, question_id: int) -> dict:
        session = LiveSession.objects.get(pin=pin)
        return build_reveal_payload(session, question_id, revealed_at=timezone.now())

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
