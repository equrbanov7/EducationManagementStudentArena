import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.core import signing
from django.utils import timezone

from liveExam.models import LiveSession, LivePlayer, LiveAnswer
from blog.models import ExamQuestionOption, ExamQuestion  # yolunu özünə uyğun saxla

# ⚠️ consumers içindən views import eləmə (circular risk).
PLAYER_COOKIE_NAME = "live_player_token"
PLAYER_TOKEN_SALT = "liveExam.player"


class LiveLobbyConsumer(AsyncJsonWebsocketConsumer):
    """
    Wait room / lobby websocket:
    - connect olanda hazırkı players listini göndərir
    - view tərəfdən group_send gələndə realtime update edir
    Group: live_<pin>_lobby
    """

    async def connect(self):
        self.pin = self.scope["url_route"]["kwargs"]["pin"]
        self.group_name = f"live_{self.pin}_lobby"

        if not await self._session_exists(self.pin):
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # ✅ ilk açılan kimi state göndər
        state = await self._get_lobby_state(self.pin)
        await self.send_json(state)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def lobby_event(self, event):
        # view -> group_send(..., {"type":"lobby_event","data":{...}})
        data = event.get("data") or {}
        await self.send_json(data)

    @database_sync_to_async
    def _session_exists(self, pin: str) -> bool:
        return LiveSession.objects.filter(pin=pin).exists()

    @database_sync_to_async
    def _get_lobby_state(self, pin: str) -> dict:
        session = LiveSession.objects.get(pin=pin)
        players = list(
            session.players.order_by("-created_at")
            .values("id", "nickname", "avatar_key")[:50]
        )
        return {"type": "lobby_state", "count": session.players.count(), "players": players}


class LivePlayConsumer(AsyncJsonWebsocketConsumer):
    """
    Oyun websocket:
    - client 'answer' göndərir
    - cookie token ilə player-i tanıyır
    - cavabı saxlayır və score artırır
    - cavab sayını (progress) group-a broadcast edir
    Group: live_<pin>_play
    """

    async def connect(self):
        self.pin = self.scope["url_route"]["kwargs"]["pin"]
        self.group_name = f"live_{self.pin}_play"

        if not await self._session_exists(self.pin):
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, data, **kwargs):
        if (data or {}).get("type") != "answer":
            return

        # ---- token
        cookies = self.scope.get("cookies") or {}
        token = cookies.get(PLAYER_COOKIE_NAME)

        if not token:
            await self.send_json({"type": "error", "message": "No token"})
            return

        try:
            payload = signing.loads(token, salt=PLAYER_TOKEN_SALT, max_age=60 * 60 * 6)
        except Exception:
            await self.send_json({"type": "error", "message": "Bad token"})
            return

        if str(payload.get("pin")) != str(self.pin):
            await self.send_json({"type": "error", "message": "Pin mismatch"})
            return

        # ---- payload validate
        try:
            question_id = int(data.get("question_id"))
            option_id = int(data.get("option_id"))
            answer_ms = int(data.get("answer_ms") or 0)
        except Exception:
            await self.send_json({"type": "error", "message": "Bad payload"})
            return

        ok, result = await self._save_answer_and_score(
            pin=self.pin,
            player_id=payload.get("player_id"),
            client_id=payload.get("client_id"),
            question_id=question_id,
            option_id=option_id,
            answer_ms=answer_ms,
        )

        if not ok:
            await self.send_json({"type": "error", "message": result})
            return

        # client-ə cavab (local UI üçün)
        await self.send_json({"type": "answer_saved", **result})

        # ✅ progress broadcast (host auto-reveal üçün)
        progress = await self._get_answer_progress(self.pin, question_id)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "play_event",
                "data": {
                    "type": "answer_progress",
                    **progress
                }
            }
        )

    async def play_event(self, event):
        # view -> group_send(... {"type":"play_event","data":{...}})
        await self.send_json(event.get("data") or {})

    # -------------------------
    # DB helpers
    # -------------------------
    @database_sync_to_async
    def _session_exists(self, pin: str) -> bool:
        return LiveSession.objects.filter(pin=pin).exists()

    @database_sync_to_async
    def _get_answer_progress(self, pin: str, question_id: int):
        session = LiveSession.objects.get(pin=pin)
        total_players = LivePlayer.objects.filter(session=session).count()
        answered_count = LiveAnswer.objects.filter(session=session, question_id=question_id).count()
        return {
            "question_id": question_id,
            "answered_count": answered_count,
            "total_players": total_players,
        }

    @database_sync_to_async
    def _save_answer_and_score(self, pin, player_id, client_id, question_id, option_id, answer_ms):
        # session
        try:
            session = LiveSession.objects.get(pin=pin)
        except LiveSession.DoesNotExist:
            return False, "Session not found"

        # player
        try:
            player = LivePlayer.objects.get(id=player_id, session=session, client_id=client_id)
        except LivePlayer.DoesNotExist:
            return False, "Player not found"

        # idempotent
        if LiveAnswer.objects.filter(session=session, player=player, question_id=question_id).exists():
            return True, {"message": "Already answered", "score": int(player.score or 0)}

        # question exists?
        try:
            eq = ExamQuestion.objects.get(id=question_id)
        except ExamQuestion.DoesNotExist:
            return False, "Question not found"

        # option həmin question-a aiddir və correct?
        is_correct = ExamQuestionOption.objects.filter(
            id=option_id,
            question_id=question_id,
            is_correct=True
        ).exists()

        base = int(getattr(eq, "points", 1000) or 1000)

        # bonus
        bonus = 0
        if is_correct and session.question_started_at and session.question_ends_at:
            total_ms = int((session.question_ends_at - session.question_started_at).total_seconds() * 1000)
            if total_ms > 0:
                answer_ms = max(0, min(int(answer_ms or 0), total_ms))
                remaining = total_ms - answer_ms
                bonus = int((remaining / total_ms) * 500)

        awarded = (base + bonus) if is_correct else 0

        LiveAnswer.objects.create(
            session=session,
            player=player,
            question_id=question_id,
            choice_id=option_id,
            is_correct=is_correct,
            answer_ms=int(answer_ms or 0),
            awarded_points=int(awarded),
        )

        player.score = int(player.score or 0) + int(awarded)
        player.last_seen = timezone.now()
        player.save(update_fields=["score", "last_seen"])

        return True, {
            "question_id": question_id,
            "is_correct": bool(is_correct),
            "awarded_points": int(awarded),
            "base": int(base),
            "bonus": int(bonus),
            "score": int(player.score or 0),
        }