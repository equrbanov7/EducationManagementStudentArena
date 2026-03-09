# liveExam/consumers.py

from __future__ import annotations

from typing import Any, Dict, Tuple

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.exams.models import ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, authenticate_player_token
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.views._helpers import _build_reveal_payload, _get_question_by_index


class LiveSessionSocketAuthMixin:
    @database_sync_to_async
    def _authorize_connection(self, pin: str, user_id: int | None, token: str | None) -> dict[str, Any] | None:
        session = LiveSession.objects.filter(pin=pin).only("id", "host_user_id").first()
        if session is None:
            return None

        payload, player = authenticate_player_token(token, pin=pin)
        if payload is None or player is None:
            if user_id and session.host_user_id == user_id:
                return {"role": "host"}
            return None

        return {
            "role": "player",
            "player_id": player.id,
            "client_id": player.client_id,
        }


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

        self.auth_context = await self._authorize_connection(self.pin, user_id, token)
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
        players = list(session.players.order_by("-created_at").values("id", "nickname", "avatar_key")[:50])
        return {
            "type": "lobby_state",
            "count": session.players.count(),
            "players": players,
        }


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
        ok, parsed_or_msg = self._parse_answer_payload(data)
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
            {"type": "play_event", "data": {"type": "answer_progress", **prog}},
        )

        if result.get("reveal_question_id"):
            reveal_payload = await self._get_reveal_payload(self.pin, result["reveal_question_id"])
            await self.channel_layer.group_send(self.group_name, {"type": "play_event", "data": reveal_payload})

    async def play_event(self, event):
        # view -> group_send(... {"type":"play_event","data":{...}})
        await self.send_json(event.get("data") or {})

    # -------------------- parse helpers --------------------

    def _parse_answer_payload(self, data: Dict[str, Any]) -> Tuple[bool, Any]:
        """
        həm single (option_id), həm multi (option_ids) qəbul edir.
        """
        try:
            question_id = int(data.get("question_id"))
            answer_ms = int(data.get("answer_ms") or 0)

            if isinstance(data.get("option_ids"), list):
                option_ids = [int(x) for x in data.get("option_ids") if str(x).isdigit()]
            else:
                option_ids = [int(data.get("option_id"))]

            # uniq + boş olmasın
            option_ids = list(dict.fromkeys(option_ids))
            if not option_ids:
                return False, pgettext("live_exam.consumer.error", "no_options_selected")

            return True, (question_id, option_ids, answer_ms)
        except Exception:
            return False, pgettext("live_exam.consumer.error", "bad_payload")

    # -------------------- DB helpers --------------------

    @database_sync_to_async
    def _get_answer_progress(self, pin: str, question_id: int) -> dict:
        session = LiveSession.objects.get(pin=pin)
        total_players = LivePlayer.objects.filter(session=session).count()

        # distinct player count (daha doğru)
        answered_count = (
            LiveAnswer.objects.filter(session=session, question_id=question_id).values("player_id").distinct().count()
        )

        return {
            "question_id": question_id,
            "answered_count": answered_count,
            "total_players": total_players,
        }

    def _get_active_question(self, session: LiveSession) -> ExamQuestion | None:
        current_question_id = getattr(session, "current_question_id", None)
        if current_question_id:
            return ExamQuestion.objects.filter(id=current_question_id, exam_id=session.exam_id).first()
        return _get_question_by_index(session, int(session.current_index or 0))

    @database_sync_to_async
    def _get_reveal_payload(self, pin: str, question_id: int) -> dict:
        session = LiveSession.objects.get(pin=pin)
        payload = _build_reveal_payload(session, question_id)
        payload["revealed_at"] = timezone.now().isoformat()
        return payload

    @database_sync_to_async
    def _save_answer_and_score(self, pin, player_id, client_id, question_id, option_ids, answer_ms):
        received_at = timezone.now()

        try:
            with transaction.atomic():
                session = LiveSession.objects.select_for_update().get(pin=pin)
                player = LivePlayer.objects.select_for_update().get(
                    id=player_id,
                    session=session,
                    client_id=client_id,
                )

                eq = ExamQuestion.objects.filter(id=question_id).first()
                if eq is None:
                    return False, pgettext("live_exam.consumer.error", "question_not_found")

                if eq.exam_id != session.exam_id:
                    return False, pgettext("live_exam.consumer.error", "question_not_found")

                active_question = self._get_active_question(session)
                if active_question is None:
                    return False, pgettext("live_exam.consumer.error", "active_question_not_found")

                if int(question_id) != int(active_question.id):
                    return False, pgettext("live_exam.consumer.error", "question_not_active")

                # idempotent only for the active question
                if LiveAnswer.objects.filter(session=session, player=player, question_id=question_id).exists():
                    return True, {
                        "answer": {
                            "message": pgettext("live_exam.consumer.error", "already_answered"),
                            "score": player.score,
                        },
                        "question_id": question_id,
                        "reveal_question_id": None,
                    }

                if (
                    session.state != LiveSession.STATE_QUESTION
                    or session.question_started_at is None
                    or session.question_ends_at is None
                ):
                    return False, pgettext("live_exam.consumer.error", "question_not_accepting_answers")

                if not (session.question_started_at <= received_at <= session.question_ends_at):
                    return False, pgettext("live_exam.consumer.error", "submission_outside_active_window")

                # correct ids
                correct_ids = list(
                    ExamQuestionOption.objects.filter(question_id=question_id, is_correct=True).values_list("id", flat=True)
                )
                if not correct_ids:
                    return False, pgettext("live_exam.consumer.error", "no_correct_options")

                correct_set = set(int(x) for x in correct_ids)
                selected_set = set(int(x) for x in option_ids)

                # perfect match
                is_perfect = selected_set == correct_set

                # partial scoring (penalty)
                T = len(selected_set & correct_set)  # doğru seçilənlər
                W = len(selected_set - correct_set)  # səhv seçilənlər
                C = len(correct_set)  # correct sayı

                # fraction = clamp((T - W) / C)
                fraction = (T - W) / float(C)
                if fraction < 0:
                    fraction = 0.0
                if fraction > 1:
                    fraction = 1.0

                base = int(getattr(eq, "points", 1000) or 1000)

                # speed bonus
                bonus = 0
                total_ms = int((session.question_ends_at - session.question_started_at).total_seconds() * 1000)
                if total_ms > 0:
                    answer_ms = max(0, min(int(answer_ms), total_ms))
                    remaining = total_ms - answer_ms
                    bonus = int((remaining / total_ms) * 500)

                awarded = int((base + bonus) * fraction)

                LiveAnswer.objects.create(
                    session=session,
                    player=player,
                    question_id=question_id,
                    choice_id=(option_ids[0] if option_ids else None),
                    choice_ids=option_ids,
                    is_correct=is_perfect,
                    answer_ms=int(answer_ms),
                    awarded_points=int(awarded),
                )

                player.score = int(player.score or 0) + int(awarded)
                player.last_seen = received_at
                player.save(update_fields=["score", "last_seen"])

                total_players = LivePlayer.objects.filter(session=session).count()
                answered_count = (
                    LiveAnswer.objects.filter(session=session, question_id=question_id)
                    .values("player_id")
                    .distinct()
                    .count()
                )

                reveal_question_id = None
                if total_players > 0 and answered_count >= total_players and session.state == LiveSession.STATE_QUESTION:
                    session.state = LiveSession.STATE_REVEAL
                    session.question_ends_at = received_at
                    session.save(update_fields=["state", "question_ends_at"])
                    reveal_question_id = question_id
        except LiveSession.DoesNotExist:
            return False, pgettext("live_exam.consumer.error", "session_not_found")
        except LivePlayer.DoesNotExist:
            return False, pgettext("live_exam.consumer.error", "player_not_found")

        return True, {
            "answer": {
                "is_correct": is_perfect,
                "fraction": round(float(fraction), 4),
                "picked_correct": T,
                "picked_wrong": W,
                "correct_total": C,
                "awarded_points": awarded,
                "base": base,
                "bonus": bonus,
                "score": player.score,
            },
            "question_id": question_id,
            "reveal_question_id": reveal_question_id,
        }
