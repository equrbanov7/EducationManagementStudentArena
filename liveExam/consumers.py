import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core import signing
from django.utils import timezone

from liveExam.models import LiveSession, LivePlayer, LiveAnswer
from blog.models import ExamQuestionOption, ExamQuestion  # import yolunu düzəlt
from liveExam.views import PLAYER_COOKIE_NAME, PLAYER_TOKEN_SALT  # eyni modulda olsa import etmə; kopyala


class LivePlayConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.pin = self.scope["url_route"]["kwargs"]["pin"]
        self.group_name = f"live_{self.pin}_play"

        exists = await sync_to_async(LiveSession.objects.filter(pin=self.pin).exists)()
        if not exists:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        data = json.loads(text_data)
        if data.get("type") != "answer":
            return

        token = None
        # websocket scope cookies
        cookies = self.scope.get("cookies") or {}
        token = cookies.get("live_player_token")

        if not token:
            await self.send(text_data=json.dumps({"type": "error", "message": "No token"}))
            return

        try:
            payload = signing.loads(token, salt=PLAYER_TOKEN_SALT, max_age=60*60*6)
        except Exception:
            await self.send(text_data=json.dumps({"type": "error", "message": "Bad token"}))
            return

        pin = payload.get("pin")
        player_id = payload.get("player_id")
        client_id = payload.get("client_id")

        if pin != self.pin:
            return

        question_id = int(data.get("question_id"))
        option_id = int(data.get("option_id"))
        answer_ms = int(data.get("answer_ms") or 0)

        await self._save_answer_and_score(player_id, client_id, question_id, option_id, answer_ms)

    async def play_event(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    @sync_to_async
    def _save_answer_and_score(self, player_id, client_id, question_id, option_id, answer_ms):
        session = LiveSession.objects.get(pin=self.pin)
        player = LivePlayer.objects.get(id=player_id, session=session, client_id=client_id)

        # artıq cavab veribsə ignore
        if LiveAnswer.objects.filter(session=session, player=player, question_id=question_id).exists():
            return

        # correct?
        is_correct = ExamQuestionOption.objects.filter(id=option_id, question_id=question_id, is_correct=True).exists()

        # points
        eq = ExamQuestion.objects.get(id=question_id)
        base = int(eq.points or 1000)

        # speed bonus (sadə)
        bonus = 0
        if is_correct and session.question_ends_at and session.question_started_at:
            total_ms = int((session.question_ends_at - session.question_started_at).total_seconds() * 1000)
            remaining = max(0, total_ms - answer_ms)
            bonus = int((remaining / total_ms) * 500) if total_ms > 0 else 0

        awarded = base + bonus if is_correct else 0

        LiveAnswer.objects.create(
            session=session,
            player=player,
            question_id=question_id,
            choice_id=option_id,
            is_correct=is_correct,
            answer_ms=answer_ms,
            awarded_points=awarded,
        )

        player.score += awarded
        player.last_seen = timezone.now()
        player.save(update_fields=["score", "last_seen"])
