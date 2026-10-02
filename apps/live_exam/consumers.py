# liveExam/consumers.py
"""
Canlı viktorina WebSocket-ləri.

Audit 2026-09-28 LX-BE miqyas qaydaları (50–90, ehtiyatla 150 oyunçu):

* DB işi ``database_sync_to_async(..., thread_sensitive=False)`` ilə ASGI thread
  hovuzunda gedir (LXBE-02). Default ``thread_sensitive=True`` WebSocket-lərdə
  prosesin BÜTÜN socket-lərinin DB işini TƏK thread-də növbəyə düzürdü — 90 cavab
  bir-birini gözləyirdi.
* Reveal/final-da hər oyunçunun şəxsi nəticəsi hadisənin ``personal`` xəritəsindən
  götürülür — consumer başına DB sorğusu YOXDUR (LXBE-03).
* Cavab vaxtı mesajın serverə ÇATDIĞI an götürülür (LXBE-01).
* Lobby siyahısı socket başına ən çox ``LOBBY_STATE_COALESCE_SECONDS``-da bir dəfə
  göndərilir (qoşulma axınında O(N²) trafik əvəzinə) (LXBE-15).

LXNET 2026-10-02 (zəif şəbəkə):

* ``{"type":"ping","id":n}`` → ``{"type":"pong","id":n,"server_time":…}`` — klient «ölü»
  (TCP-də ilişmiş) socket-i tez tanıyır və saatını RTT ilə sinxronlaşdırır. DB/keş YOXDUR;
  socket başına sürət həddi yaddaşda (``PING_MIN_INTERVAL_SECONDS``), ümumi mesaj limitinə
  düşmür (limitə düşən ping «ölü socket» kimi yanlış yenidən qoşulma doğurardı).
* ``{"type":"seen","question_id":q}`` (yalnız oyunçu, yalnız BU socket-in ötürdüyü sual, bir dəfə) —
  sualın telefona çatdığının server-vaxtlı sübutu (``delivery.py``): gec çatana ədalətli sürət
  ankeri + host-a «N telefon aldı» (``delivery_progress``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.live_exam import consumer_support as support
from apps.live_exam.auth import authorize_socket_connection
from apps.live_exam.constants import LOBBY_STATE_COALESCE_SECONDS
from apps.live_exam.delivery import build_delivery_progress_payload, record_question_seen
from apps.live_exam.models import LiveSession
from apps.live_exam.reveal import build_reveal_bundle
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.serializers import serialize_player_question_result
from apps.live_exam.services import auto_reveal_if_due
from apps.live_exam.transport import (
    build_answer_progress_payload,
    build_answer_saved_payload,
    build_lobby_state_payload,
    bundle_events,
    parse_answer_submission,
)
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

logger = logging.getLogger("live_exam.ws.rate_limit")

# Async wrappers — DB/cache işi thread hovuzunda (thread_sensitive=False).
_record_rate_limit_hit = sync_to_async(record_rate_limit_hit, thread_sensitive=False)
_cache_add = sync_to_async(cache.add, thread_sensitive=False)
_record_seen = sync_to_async(record_question_seen, thread_sensitive=False)

#: Eyni socket-dən iki ``pong`` arasında minimum interval (klient ~6 s-də bir ping göndərir).
PING_MIN_INTERVAL_SECONDS = 0.8


def _pool(func):
    return database_sync_to_async(func, thread_sensitive=False)


def _error(msgid: str) -> dict[str, Any]:
    return {"type": "error", "message": pgettext("live_exam.consumer.error", msgid)}


class LiveSocketBase(AsyncJsonWebsocketConsumer):
    """Ortaq: ucuz ön-autentifikasiya, qoşulma limitləri, mesaj qoruyucuları, kick."""

    kind = "socket"
    auth_context: dict[str, Any] | None = None
    player_auth: dict[str, Any] | None = None

    async def _admit(self) -> bool:
        """Autentifikasiya + limitlər. ``False`` → socket artıq bağlanıb."""
        self.pin = str(self.scope["url_route"]["kwargs"]["pin"])[:32]
        token, token_payload = support.signed_player_token(self.scope, self.pin)
        user_id = support.scope_user_id(self.scope)
        if token_payload is None and not user_id:
            # LXS-15: anonim socket DB-yə toxunmadan, PIN-dən asılı olmayaraq rədd edilir.
            await self.close(code=support.CLOSE_UNAUTHORIZED)
            return False

        identity = support.connect_identity(self.scope, token_payload)
        for scope_name, rate, key in (
            (support.WS_CONNECT_SCOPE, self._connect_rate(), identity),
            (support.WS_CONNECT_IP_SCOPE, support.connect_ip_rate(), f"ip:{support.scope_ip(self.scope)}"),
        ):
            is_limited, retry_after = await _record_rate_limit_hit(scope_name, rate, self.pin, key)
            if is_limited:
                logger.warning(
                    "WebSocket connect flood blocked on %s",
                    self.kind,
                    extra={"pin": self.pin, "connect_identity": key, "retry_after": retry_after},
                )
                await self.close(code=support.CLOSE_RATE_LIMITED)
                return False

        self.auth_context = await self._authorize_connection(self.pin, user_id, token)
        if self.auth_context is None:
            await self.close(code=support.CLOSE_UNAUTHORIZED)
            return False
        self.player_auth = self.auth_context if self.auth_context.get("role") == "player" else None
        return True

    @staticmethod
    def _connect_rate():
        from django.conf import settings

        return settings.LIVE_WS_CONNECT_RATE_LIMIT

    @_pool
    def _authorize_connection(self, pin: str, user_id: int | None, token: str | None) -> dict[str, Any] | None:
        # Auth helper performs PIN/token based system lookup under bypass_rls().
        with rls_worker_atomic():
            return authorize_socket_connection(pin=pin, user_id=user_id, token=token, allow_anonymous=False)

    @classmethod
    async def decode_json(cls, text_data):
        return support.decode_client_json(text_data)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        # Binar kadr — protokolda yoxdur, sükutla atılır (əvvəl ValueError → 1011 idi).
        if text_data is None:
            return
        if len(text_data) > support.WS_MAX_MESSAGE_CHARS:
            await self.close(code=support.CLOSE_MESSAGE_TOO_BIG)
            return
        await super().receive(text_data=text_data, **kwargs)

    def _own_player_id(self) -> int | None:
        return int(self.player_auth["player_id"]) if self.player_auth else None

    async def _reply_pong(self, data: dict[str, Any]) -> None:
        """LXNET: ürək döyüntüsü — server vaxtı ilə cavab (DB/keş yoxdur, yaddaşda sürət həddi)."""
        now = asyncio.get_running_loop().time()
        if now - getattr(self, "_last_pong_at", -1e9) < PING_MIN_INTERVAL_SECONDS:
            return
        self._last_pong_at = now
        ping_id = data.get("id")
        echo = ping_id if isinstance(ping_id, int) and not isinstance(ping_id, bool) and 0 <= ping_id < 2**31 else None
        await self.send_json({"type": "pong", "id": echo, "server_time": timezone.now().isoformat()})

    async def player_kicked(self, event):
        """LXBE-07: host oyunçunu çıxardı — onun socket-i bağlanır, başqalarına ötürülmür."""
        if self._own_player_id() is not None and int(event.get("player_id") or 0) == self._own_player_id():
            self._on_kicked()
            await self.send_json({"type": "kicked"})
            await self.close(code=support.CLOSE_KICKED)

    def _on_kicked(self) -> None:
        """Alt siniflər gözləyən taymerləri burada ləğv edir (bağlandıqdan sonra göndəriş olmasın)."""


# -------------------------
# Lobby consumer
# -------------------------


class LiveLobbyConsumer(LiveSocketBase):
    """
    Wait room / lobby websocket:
    - connect olanda hazırkı players listini göndərir
    - view tərəfdən group_send gələndə realtime update edir
    Group: live_<pin>_lobby
    """

    kind = "lobby"

    async def connect(self):
        self._pending_lobby_state = None
        self._lobby_flush_handle = None
        self._last_lobby_sent = 0.0
        if not await self._admit():
            return
        self.group_name = f"live_{self.pin}_lobby"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # ilk açılan kimi state göndər
        state = await self._get_lobby_state(self.pin)
        if state is not None:
            self._last_lobby_sent = asyncio.get_running_loop().time()
            await self.send_json(state)

    def _on_kicked(self) -> None:
        handle = getattr(self, "_lobby_flush_handle", None)
        if handle is not None:
            handle.cancel()
        self._lobby_flush_handle = None
        self._pending_lobby_state = None

    async def disconnect(self, close_code):
        self._on_kicked()
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Lobby socket-i klientdən yalnız ürək döyüntüsü (ping) qəbul edir.
        if isinstance(content, dict) and content.get("type") == "ping":
            await self._reply_pong(content)

    async def lobby_event(self, event):
        # view -> group_send(..., {"type":"lobby_event","data":{...}})
        data = event.get("data") or {}
        if data.get("type") == "lobby_state":
            await self._throttled_lobby_state(data)
            return
        await self._flush_lobby_state()
        await self.send_json(data)

    async def _throttled_lobby_state(self, data: dict[str, Any]) -> None:
        """Ön kənar dərhal, sonrakılar birləşdirilir (ən sonuncu qalib gəlir)."""
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_lobby_sent
        if self._lobby_flush_handle is None and elapsed >= LOBBY_STATE_COALESCE_SECONDS:
            self._last_lobby_sent = loop.time()
            await self.send_json(data)
            return
        self._pending_lobby_state = data
        if self._lobby_flush_handle is None:
            delay = max(0.0, LOBBY_STATE_COALESCE_SECONDS - elapsed)
            self._lobby_flush_handle = loop.call_later(delay, lambda: asyncio.ensure_future(self._flush_lobby_state()))

    async def _flush_lobby_state(self) -> None:
        if self._lobby_flush_handle is not None:
            self._lobby_flush_handle.cancel()
            self._lobby_flush_handle = None
        pending, self._pending_lobby_state = self._pending_lobby_state, None
        if pending is not None:
            self._last_lobby_sent = asyncio.get_running_loop().time()
            await self.send_json(pending)

    @_pool
    def _get_lobby_state(self, pin: str) -> dict | None:
        # PIN-based live-session lookup is system-scoped; keep existing bypass.
        with rls_worker_atomic(), bypass_rls():
            session = LiveSession.objects.filter(pin=pin).first()
            return build_lobby_state_payload(session) if session is not None else None


# -------------------------
# Play consumer
# -------------------------


class LivePlayConsumer(LiveSocketBase):
    """
    Oyun websocket:
    - client 'answer' göndərir (variant id-ləri və ya yazılı ``text``)
    - cookie token ilə player-i tanıyır
    - cavabı saxlayır və score artırır
    - sonra answer_progress broadcast edir (host qrupu)
    Group: live_<pin>_play_host / live_<pin>_play_players
    """

    kind = "play"

    async def connect(self):
        self._auto_reveal_task = None
        # LXNET: bu socket-in ötürdüyü son sual və artıq təsdiqlənmiş sual (``seen`` bir dəfə).
        self._published_question_id = None
        self._seen_question_id = None
        if not await self._admit():
            return

        # Host and players join separate channel-layer groups so that
        # host-only events (e.g. answer_progress) never reach players.
        if self.auth_context.get("role") == "host":
            self.play_group = f"live_{self.pin}_play_host"
        else:
            self.play_group = f"live_{self.pin}_play_players"

        await self.channel_layer.group_add(self.play_group, self.channel_name)
        await self.accept()

    def _on_kicked(self) -> None:
        self._cancel_auto_reveal()

    async def disconnect(self, close_code):
        self._cancel_auto_reveal()
        play_group = getattr(self, "play_group", None)
        if play_group:
            await self.channel_layer.group_discard(play_group, self.channel_name)

    def _rate_limit_key(self) -> str:
        """Stable per-connection key for message rate limiting."""
        if self.player_auth:
            return f"player:{self.player_auth['player_id']}"
        if self.auth_context:
            return f"{self.auth_context.get('role', 'unknown')}:{self.channel_name}"
        return self.channel_name

    async def receive_json(self, data, **kwargs):
        # LXBE-01: bal üçün vaxt mesajın ÇATDIĞI an (limit/DB növbəsindən əvvəl).
        received_at = timezone.now()
        if not isinstance(data, dict):
            return
        message_type = data.get("type")
        if message_type == "ping":
            await self._reply_pong(data)
            return
        if message_type == "seen":
            await self._handle_seen(data, received_at)
            return

        from django.conf import settings

        # Per-connection general message rate limit (flood protection)
        player_key = self._rate_limit_key()
        is_msg_limited, msg_retry_after = await _record_rate_limit_hit(
            support.WS_MSG_SCOPE, settings.LIVE_WS_MSG_RATE_LIMIT, self.pin, player_key
        )
        if is_msg_limited:
            logger.warning(
                "WebSocket message flood blocked",
                extra={"pin": self.pin, "player_key": player_key, "retry_after": msg_retry_after},
            )
            await self.send_json(_error("rate_limited"))
            return

        if data.get("type") != "answer":
            return
        if self.player_auth is None:
            await self.send_json(_error("auth_required"))
            return

        # Per-player answer submission rate limit
        is_answer_limited, answer_retry_after = await _record_rate_limit_hit(
            support.WS_ANSWER_SCOPE, settings.LIVE_ANSWER_RATE_LIMIT, self.pin, self.player_auth["player_id"]
        )
        if is_answer_limited:
            logger.warning(
                "WebSocket answer flood blocked",
                extra={"pin": self.pin, "player_id": self.player_auth["player_id"], "retry_after": answer_retry_after},
            )
            await self.send_json(_error("rate_limited"))
            return

        ok, parsed_or_msg = parse_answer_submission(data)
        if not ok:
            await self.send_json({"type": "error", "message": parsed_or_msg})
            return
        question_id, option_ids, answer_ms, text = parsed_or_msg

        try:
            ok, result = await self._save_answer_and_score(
                question_id=question_id,
                option_ids=option_ids,
                answer_ms=answer_ms,
                text=text,
                received_at=received_at,
            )
        except Exception:
            logger.exception("live answer save failed", extra={"pin": self.pin})
            await self.send_json(_error("answer_retry"))
            return
        if not ok:
            await self.send_json({"type": "error", "message": result})
            return

        # Audit 2026-09-28 EX28-10: düzlük/bal reveal-ə qədər göndərilmir.
        await self.send_json(build_answer_saved_payload(result))

        # progress -> host group only (players do not need this; host uses it for the counter)
        progress = result.get("progress")
        if progress:
            await self.channel_layer.group_send(
                f"live_{self.pin}_play_host",
                {"type": "play_event", "data": build_answer_progress_payload(**progress)},
            )

        if result.get("reveal_question_id"):
            bundle = await self._build_reveal_bundle(result["reveal_question_id"])
            if bundle is not None:
                await self._send_bundle(bundle)

    async def _handle_seen(self, data: dict[str, Any], received_at) -> None:
        """LXNET: sual telefona çatdı — server vaxtı ilə ilk sübut + host sayğacı."""
        if self.player_auth is None:
            return
        try:
            question_id = int(data.get("question_id"))
        except (TypeError, ValueError):
            return
        # Yalnız bu socket-in ötürdüyü sual və yalnız bir dəfə (keşə saxta açar yazılmasın).
        if question_id != self._published_question_id or question_id == self._seen_question_id:
            return
        self._seen_question_id = question_id
        received = await _record_seen(self.pin, question_id, self._own_player_id(), at=received_at)
        if received is not None:
            await self.channel_layer.group_send(
                f"live_{self.pin}_play_host",
                {
                    "type": "play_event",
                    "data": build_delivery_progress_payload(question_id=question_id, received=received),
                },
            )

    async def play_event(self, event):
        # view -> group_send(... {"type":"play_event","data":{...}})
        data = event.get("data") or {}
        event_type = data.get("type")
        if event_type == "question_published":
            self._schedule_auto_reveal(data.get("question"))
            try:
                self._published_question_id = int((data.get("question") or {}).get("id"))
            except (TypeError, ValueError):
                self._published_question_id = None
        elif event_type in {"reveal", "finished"}:
            self._cancel_auto_reveal()

        if self.player_auth and event_type in {"reveal", "finished"}:
            merged = support.merge_personal(data, event, self._own_player_id())
            if merged is None and event_type == "reveal" and data.get("question_id"):
                # Köhnə formatlı hadisə (personal xəritəsi yoxdur) — ehtiyat DB yolu.
                player_answer = await self._get_own_player_answer(data["question_id"])
                merged = {**data, "player_answer": player_answer} if player_answer else dict(data)
            data = merged if merged is not None else data
        await self.send_json(data)

    # ── Server auto-reveal (LXBE-08) ────────────────────────────────────────

    def _schedule_auto_reveal(self, question: dict[str, Any] | None) -> None:
        self._cancel_auto_reveal()
        due = support.auto_reveal_delay(question)
        if due is not None:
            self._auto_reveal_task = asyncio.ensure_future(self._auto_reveal_after(*due))

    def _cancel_auto_reveal(self) -> None:
        task = getattr(self, "_auto_reveal_task", None)
        if task is not None and not task.done():
            task.cancel()
        self._auto_reveal_task = None

    async def _auto_reveal_after(self, question_id: int, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            try:
                claimed = await _cache_add(f"live_exam:auto_reveal:{self.pin}:{question_id}", "1", 60)
            except Exception:
                claimed = True  # keş əlçatmazdır — DB-dəki şərtli keçid onsuz da tək qalibdir
            if not claimed:
                return
            bundle = await self._auto_reveal(question_id)
            if bundle is not None:
                await self._send_bundle(bundle)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("live auto-reveal failed", extra={"pin": self.pin, "question_id": question_id})

    async def _send_bundle(self, bundle) -> None:
        for group, event in bundle_events(self.pin, bundle):
            await self.channel_layer.group_send(group, event)

    # ── DB (thread hovuzu) ──────────────────────────────────────────────────

    @_pool
    def _auto_reveal(self, question_id: int):
        with rls_worker_atomic(), bypass_rls():
            return auto_reveal_if_due(self.pin, question_id)

    @_pool
    def _build_reveal_bundle(self, question_id: int):
        with rls_worker_atomic(), bypass_rls():
            session = LiveSession.objects.select_related("exam").filter(pin=self.pin).first()
            return build_reveal_bundle(session, question_id) if session is not None else None

    @_pool
    def _get_own_player_answer(self, question_id: int):
        with rls_worker_atomic(), bypass_rls():
            session = LiveSession.objects.select_related("exam").filter(pin=self.pin).first()
            if session is None:
                return None
            return serialize_player_question_result(session, question_id, self._own_player_id())

    @_pool
    def _save_answer_and_score(self, *, question_id, option_ids, answer_ms, text, received_at):
        # Scoring is PIN/player-token scoped and keeps its existing bypass_rls().
        with rls_worker_atomic():
            return save_answer_and_score(
                pin=self.pin,
                player_id=self.player_auth["player_id"],
                client_id=self.player_auth["client_id"],
                question_id=question_id,
                option_ids=option_ids,
                answer_ms=answer_ms,
                received_at=received_at,
                text=text,
            )
