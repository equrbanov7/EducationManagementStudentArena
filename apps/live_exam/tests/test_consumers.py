"""
Consumer tests for live_exam websocket auth.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from config.asgi import application

User = get_user_model()

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LiveExamConsumerAuthTest(TransactionTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("consumer_teacher", "teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="Consumer Exam",
            slug="consumer-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="SocketPlayer",
            avatar_key="avatar_1",
            client_id="socket-client",
        )

    def _player_headers(self, *, pin=None):
        token = build_player_token(
            pin=pin or self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )
        return [(b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]

    def _host_session_headers(self):
        client = Client()
        client.login(username="consumer_teacher", password="StrongPass123!")
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [(b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode())]

    def test_lobby_ws_allows_viewer_without_auth(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/lobby/")
            connected, _ = await communicator.connect()
            message = await communicator.receive_json_from() if connected else None
            if connected:
                await communicator.disconnect()
            return connected, message

        connected, message = async_to_sync(scenario)()
        self.assertTrue(connected)
        self.assertEqual(message["type"], "lobby_state")
        self.assertEqual(message["count"], 1)

    def test_play_ws_rejects_missing_auth(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/play/")
            connected, _ = await communicator.connect()
            await communicator.wait()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(connected)

    def test_lobby_ws_accepts_authenticated_player(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/lobby/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            message = await communicator.receive_json_from() if connected else None
            if connected:
                await communicator.disconnect()
            return connected, message

        connected, message = async_to_sync(scenario)()
        self.assertTrue(connected)
        self.assertEqual(message["type"], "lobby_state")
        self.assertEqual(message["players"][0]["accessory_key"], "accessory_none")

    def test_lobby_ws_delivers_reaction_events(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/lobby/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=1)
            await get_channel_layer().group_send(
                f"live_{self.session.pin}_lobby",
                {
                    "type": "lobby_event",
                    "data": {
                        "type": "reaction_event",
                        "reaction_key": "like",
                        "emoji": "👍",
                        "player": {
                            "id": self.player.id,
                            "nickname": self.player.nickname,
                            "avatar_key": self.player.avatar_key,
                            "accessory_key": self.player.accessory_key,
                        },
                    },
                },
            )
            try:
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "reaction_event")
        self.assertEqual(message["player"]["accessory_key"], "accessory_none")

    def test_play_ws_accepts_authenticated_player(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected

        connected = async_to_sync(scenario)()
        self.assertTrue(connected)

    def test_play_ws_accepts_host_session_auth(self):
        headers = self._host_session_headers()

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=headers,
            )
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected

        connected = async_to_sync(scenario)()
        self.assertTrue(connected)


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LiveExamAnswerSubmissionConsumerTest(TransactionTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("answer_teacher", "answer@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            title="Answer Validation Exam",
            slug="answer-validation-exam",
            author=self.teacher,
            is_active=True,
        )
        self.other_exam = Exam.objects.create(
            title="Other Exam",
            slug="other-answer-validation-exam",
            author=self.teacher,
            is_active=True,
        )

        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Current question",
            order=1,
            points=10,
        )
        self.correct_option = ExamQuestionOption.objects.create(
            question=self.question,
            text="Correct",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.question,
            text="Wrong",
            is_correct=False,
        )

        self.other_question_same_exam = ExamQuestion.objects.create(
            exam=self.exam,
            text="Not current",
            order=2,
            points=10,
        )
        self.other_option_same_exam = ExamQuestionOption.objects.create(
            question=self.other_question_same_exam,
            text="Other question option",
            is_correct=True,
        )

        self.cross_exam_question = ExamQuestion.objects.create(
            exam=self.other_exam,
            text="Cross exam question",
            order=1,
            points=10,
        )
        self.cross_exam_option = ExamQuestionOption.objects.create(
            question=self.cross_exam_question,
            text="Cross exam option",
            is_correct=True,
        )

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        now = timezone.now()
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(update_fields=["state", "current_index", "question_started_at", "question_ends_at"])

        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="Player One",
            avatar_key="avatar_1",
            client_id="player-one-client",
        )

    def _player_headers(self, player):
        token = build_player_token(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )
        return [(b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]

    def _host_and_player_headers(self, player):
        host_client = Client()
        host_client.login(username="answer_teacher", password="StrongPass123!")
        session_cookie = host_client.cookies[settings.SESSION_COOKIE_NAME].value
        player_cookie = build_player_token(
            pin=self.session.pin,
            player_id=player.id,
            client_id=player.client_id,
        )
        return [
            (
                b"cookie",
                (
                    f"{settings.SESSION_COOKIE_NAME}={session_cookie}; "
                    f"{PLAYER_COOKIE_NAME}={player_cookie}"
                ).encode(),
            )
        ]

    def test_play_ws_rejects_non_current_question_answers(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.other_question_same_exam.id,
                        "option_id": self.other_option_same_exam.id,
                        "answer_ms": 250,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "error")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_play_ws_rejects_late_answers(self):
        now = timezone.now()
        self.session.question_started_at = now - timezone.timedelta(seconds=20)
        self.session.question_ends_at = now - timezone.timedelta(seconds=1)
        self.session.save(update_fields=["question_started_at", "question_ends_at"])

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 250,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "error")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_play_ws_rejects_answers_during_intro_window(self):
        now = timezone.now()
        self.session.question_started_at = now - timezone.timedelta(seconds=2)
        self.session.question_ends_at = now + timezone.timedelta(seconds=20)
        self.session.save(update_fields=["question_started_at", "question_ends_at"])

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 10,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "error")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_play_ws_rejects_cross_exam_answers(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.cross_exam_question.id,
                        "option_id": self.cross_exam_option.id,
                        "answer_ms": 250,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "error")
        self.assertEqual(LiveAnswer.objects.count(), 0)

    def test_play_ws_reveals_immediately_after_all_players_answer(self):
        second_player = LivePlayer.objects.create(
            session=self.session,
            nickname="Player Two",
            avatar_key="avatar_2",
            client_id="player-two-client",
        )

        async def scenario():
            ws1 = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            ws2 = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(second_player),
            )

            connected1, _ = await ws1.connect()
            connected2, _ = await ws2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            try:
                await ws1.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 250,
                    }
                )
                first_sender_messages = [
                    await ws1.receive_json_from(timeout=1),
                    await ws1.receive_json_from(timeout=1),
                ]
                first_other_message = await ws2.receive_json_from(timeout=1)

                await ws2.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 300,
                    }
                )
                second_sender_messages = [
                    await ws2.receive_json_from(timeout=1),
                    await ws2.receive_json_from(timeout=1),
                    await ws2.receive_json_from(timeout=1),
                ]
                first_player_completion_messages = [
                    await ws1.receive_json_from(timeout=1),
                    await ws1.receive_json_from(timeout=1),
                ]

                return (
                    [message["type"] for message in first_sender_messages],
                    first_other_message["type"],
                    [message["type"] for message in second_sender_messages],
                    second_sender_messages[2],
                    [message["type"] for message in first_player_completion_messages],
                )
            finally:
                await ws1.disconnect()
                await ws2.disconnect()

        (
            first_sender_types,
            first_other_type,
            second_sender_types,
            reveal_message,
            first_player_completion_types,
        ) = async_to_sync(scenario)()

        self.assertEqual(first_sender_types, ["answer_saved", "answer_progress"])
        self.assertEqual(first_other_type, "answer_progress")
        self.assertEqual(second_sender_types, ["answer_saved", "answer_progress", "reveal"])
        self.assertEqual(first_player_completion_types, ["answer_progress", "reveal"])
        self.assertIn("previous_top", reveal_message)
        self.assertIn("distribution", reveal_message)
        self.assertIn("next_question_at", reveal_message)
        self.assertTrue(any("player_id" in row for row in reveal_message["top"]))

        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, question_id=self.question.id).count(),
            2,
        )

    def test_play_ws_prefers_player_cookie_when_host_session_is_also_present(self):
        headers = self._host_and_player_headers(self.player)

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=headers,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 200,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "answer_saved")
        self.assertEqual(message["answer_rank"], 1)
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=self.player, question_id=self.question.id).count(),
            1,
        )
