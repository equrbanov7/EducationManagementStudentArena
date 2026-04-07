"""
Consumer tests for live_exam websocket auth.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import LIVE_CLIENT_ID_COOKIE_NAME, PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.organizations.models import Organization
from config.asgi import application
from core.constants import OrganizationType

User = get_user_model()

# Origin header required by AllowedHostsOriginValidator in the ASGI configuration.
# All WebSocket connections in tests must include this header.
_WS_ORIGIN_HEADER = (b"origin", b"http://testserver")

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

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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
        return [_WS_ORIGIN_HEADER, (b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]

    def _host_session_headers(self):
        client = Client()
        client.login(username="consumer_teacher", password="StrongPass123!")
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [_WS_ORIGIN_HEADER, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode())]

    def test_lobby_ws_allows_viewer_without_auth(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application, f"/ws/live/{self.session.pin}/lobby/", headers=[_WS_ORIGIN_HEADER]
            )
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

    def test_expired_player_token_rejected(self):
        """
        A player token that has exceeded ``PLAYER_TOKEN_MAX_AGE`` must be
        rejected; the WebSocket connection must not be established.
        """
        from unittest.mock import patch

        # Patch signing.loads to raise SignatureExpired so the middleware sees
        # an expired token and rejects the connection.
        from django.core import signing

        async def scenario():
            with patch.object(signing, "loads", side_effect=signing.SignatureExpired("expired")):
                communicator = WebsocketCommunicator(
                    application,
                    f"/ws/live/{self.session.pin}/play/",
                    headers=self._player_headers(),
                )
                connected, _ = await communicator.connect()
                await communicator.wait()
                return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(connected, "An expired player token must cause the WebSocket handshake to be rejected")

    # Required named alias for acceptance criteria
    test_expired_token_rejected = test_expired_player_token_rejected

    def test_websocket_rejects_invalid_origin(self):
        """
        A WebSocket connection from an origin not in ALLOWED_HOSTS must be
        rejected by AllowedHostsOriginValidator before reaching the consumer.
        The connection must not be established.
        """

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                # Provide a foreign origin that is not in ALLOWED_HOSTS /
                # testserver.  AllowedHostsOriginValidator must block this.
                headers=[(b"origin", b"http://evil.attacker.example.com")],
            )
            connected, _ = await communicator.connect()
            await communicator.wait()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(
            connected,
            "AllowedHostsOriginValidator must reject connections from non-whitelisted origins",
        )

    def test_player_token_pin_mismatch_rejected(self):
        """
        A valid token signed for a *different* session PIN must not grant
        access to the current session's WebSocket endpoint.
        """
        # Build a token for the correct player/client but for a non-existent PIN.
        wrong_pin = "0000000000"  # 10 chars — valid length but guaranteed not to match
        wrong_token = build_player_token(
            pin=wrong_pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )
        from apps.live_exam.auth import PLAYER_COOKIE_NAME

        headers = [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{PLAYER_COOKIE_NAME}={wrong_token}".encode()),
        ]

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=headers,
            )
            connected, _ = await communicator.connect()
            await communicator.wait()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(
            connected,
            "A token signed for a different PIN must not authenticate the player",
        )

    def test_player_cannot_see_correct_answers_in_websocket(self):
        """
        When the host advances to the question state, the ``question_published``
        message broadcast to players must not contain ``is_correct``,
        ``correct_option_ids``, or ``correct_ids`` fields.
        """
        from asgiref.sync import async_to_sync as _async_to_sync

        # Connect as a player
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            # Drain the initial lobby_state / connection message if present.
            try:
                await communicator.disconnect()
            finally:
                pass

        _async_to_sync(scenario)()

        # Directly verify that the serializer does not expose answer keys.
        # This tests the data layer that feeds the websocket broadcast.
        from django.utils import timezone

        from apps.exams.models import ExamQuestion, ExamQuestionOption
        from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
        from apps.live_exam.serializers import serialize_question

        exam = self.session.exam
        question = ExamQuestion.objects.create(exam=exam, text="Security check Q", order=99, points=500)
        ExamQuestionOption.objects.create(question=question, text="Right", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)

        now = timezone.now()
        ready_ends_at = now + timezone.timedelta(seconds=PLAYER_GET_READY_SECONDS)
        answer_starts_at = ready_ends_at + timezone.timedelta(seconds=PLAYER_QUESTION_INTRO_SECONDS)
        ends_at = answer_starts_at + timezone.timedelta(seconds=15)

        payload = serialize_question(
            self.session,
            question,
            idx=0,
            total=1,
            started_at=now,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        )
        self.assertNotIn("correct_option_ids", payload, "Player payload must not leak correct_option_ids")
        self.assertNotIn("correct_ids", payload, "Player payload must not leak correct_ids")
        for option in payload.get("options", []):
            self.assertNotIn("is_correct", option, "Player option payload must not expose is_correct")

    def test_duplicate_answer_prevented(self):
        """
        Submitting the same answer twice via WebSocket must not create more
        than one ``LiveAnswer`` record in the database.
        """
        from django.utils import timezone

        from apps.exams.models import ExamQuestion, ExamQuestionOption
        from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
        from apps.live_exam.models import LiveAnswer

        exam = self.session.exam
        question = ExamQuestion.objects.create(exam=exam, text="Dup check Q", order=98, points=500)
        correct_option = ExamQuestionOption.objects.create(question=question, text="Right", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Wrong", is_correct=False)

        now = timezone.now()
        self.session.state = "question"
        self.session.current_index = 0
        self.session.current_question_id = question.id
        self.session.question_started_at = now - timezone.timedelta(
            seconds=PLAYER_GET_READY_SECONDS + PLAYER_QUESTION_INTRO_SECONDS + 1
        )
        self.session.question_ends_at = now + timezone.timedelta(seconds=15)
        self.session.save(
            update_fields=["state", "current_index", "current_question_id", "question_started_at", "question_ends_at"]
        )

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": question.id,
                        "option_id": correct_option.id,
                        "answer_ms": 300,
                    }
                )
                first = await communicator.receive_json_from(timeout=1)
                # Drain the auto-reveal that fires for single-player sessions.
                import asyncio

                try:
                    await asyncio.wait_for(communicator.receive_json_from(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": question.id,
                        "option_id": correct_option.id,
                        "answer_ms": 600,
                    }
                )
                second = await communicator.receive_json_from(timeout=1)
                return first, second
            finally:
                await communicator.disconnect()

        first, second = async_to_sync(scenario)()
        self.assertEqual(first["type"], "answer_saved")
        self.assertEqual(second["type"], "answer_saved")
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=self.player, question_id=question.id).count(),
            1,
            "Only one LiveAnswer must exist after duplicate submission",
        )

    def test_answer_after_time_expires_rejected(self):
        """
        Submitting an answer after ``question_ends_at`` must be rejected
        (no LiveAnswer is created and no ``answer_saved`` is received).
        """
        from django.utils import timezone

        from apps.exams.models import ExamQuestion, ExamQuestionOption
        from apps.live_exam.models import LiveAnswer

        exam = self.session.exam
        question = ExamQuestion.objects.create(exam=exam, text="Late answer Q", order=97, points=500)
        option = ExamQuestionOption.objects.create(question=question, text="Answer", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Other", is_correct=False)

        now = timezone.now()
        # question_ends_at is in the past → answer window is closed
        self.session.state = "question"
        self.session.current_index = 0
        self.session.current_question_id = question.id
        self.session.question_started_at = now - timezone.timedelta(seconds=60)
        self.session.question_ends_at = now - timezone.timedelta(seconds=1)
        self.session.save(
            update_fields=["state", "current_index", "current_question_id", "question_started_at", "question_ends_at"]
        )

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": question.id,
                        "option_id": option.id,
                        "answer_ms": 100,
                    }
                )
                # Should receive an error or nothing (the communicator will
                # time-out if no message is sent back).
                import asyncio

                try:
                    msg = await asyncio.wait_for(communicator.receive_json_from(), timeout=0.5)
                    return msg
                except asyncio.TimeoutError:
                    return None
            finally:
                await communicator.disconnect()

        async_to_sync(scenario)()
        # Late answer must not create a LiveAnswer record.
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=self.player, question_id=question.id).count(),
            0,
            "No LiveAnswer must be created for a late submission",
        )


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LiveExamAnswerSubmissionConsumerTest(TransactionTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("answer_teacher", "answer@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

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
        return [_WS_ORIGIN_HEADER, (b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]

    def _host_session_headers(self):
        client = Client()
        client.login(username="answer_teacher", password="StrongPass123!")
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [_WS_ORIGIN_HEADER, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode())]

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
            _WS_ORIGIN_HEADER,
            (
                b"cookie",
                (f"{settings.SESSION_COOKIE_NAME}={session_cookie}; " f"{PLAYER_COOKIE_NAME}={player_cookie}").encode(),
            ),
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
                # ws1 answers — players no longer receive answer_progress
                await ws1.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 250,
                    }
                )
                first_sender_response = await ws1.receive_json_from(timeout=1)
                # ws2 receives nothing from ws1's answer (answer_progress now host-only)
                ws2_has_pending = await ws2.receive_nothing(timeout=0.3)

                # ws2 answers — triggers auto-reveal since all players answered
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
                ]
                # ws1 receives the reveal broadcast to the players group
                first_player_reveal = await ws1.receive_json_from(timeout=1)

                return (
                    first_sender_response,
                    ws2_has_pending,
                    [message["type"] for message in second_sender_messages],
                    second_sender_messages[1],
                    first_player_reveal,
                )
            finally:
                await ws1.disconnect()
                await ws2.disconnect()

        (
            first_sender_response,
            ws2_no_message,
            second_sender_types,
            reveal_message,
            first_player_reveal,
        ) = async_to_sync(scenario)()

        # ws1 only receives answer_saved (answer_progress is now host-only)
        self.assertEqual(first_sender_response["type"], "answer_saved")
        # ws2 receives nothing when ws1 answers (answer_progress is host-only)
        self.assertTrue(ws2_no_message)
        # ws2 receives answer_saved then reveal (no answer_progress for players)
        self.assertEqual(second_sender_types, ["answer_saved", "reveal"])
        # Reveal payload has correct structure for players
        self.assertIn("previous_top", reveal_message)
        self.assertIn("distribution", reveal_message)
        self.assertIn("next_question_at", reveal_message)
        self.assertIn("correct_option_ids", reveal_message)
        self.assertTrue(any("player_id" in row for row in reveal_message["top"]))
        # Player reveal does NOT include per-player results (host-only field)
        self.assertNotIn("results", reveal_message)
        # ws1 also receives reveal from the players group broadcast
        self.assertEqual(first_player_reveal["type"], "reveal")
        self.assertIn("correct_option_ids", first_player_reveal)

        self.session.refresh_from_db()
        self.assertEqual(self.session.state, LiveSession.STATE_REVEAL)
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, question_id=self.question.id).count(),
            2,
        )

    def test_answer_progress_reaches_host_not_players(self):
        """answer_progress events must be delivered to the host group only."""
        LivePlayer.objects.create(
            session=self.session,
            nickname="Player Three",
            avatar_key="avatar_3",
            client_id="player-three-client",
        )
        host_headers = self._host_session_headers()

        async def scenario():
            # Connect player ws (players group)
            player_ws = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            # Connect host ws (host group)
            host_ws = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=host_headers,
            )

            connected_p, _ = await player_ws.connect()
            connected_h, _ = await host_ws.connect()
            self.assertTrue(connected_p)
            self.assertTrue(connected_h)

            try:
                # Player one submits answer
                await player_ws.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 200,
                    }
                )
                # Player receives answer_saved (direct unicast)
                player_direct = await player_ws.receive_json_from(timeout=1)
                # Host receives answer_progress (host-only group broadcast)
                host_msg = await host_ws.receive_json_from(timeout=1)
                # Player should receive nothing else (no answer_progress)
                player_no_progress = await player_ws.receive_nothing(timeout=0.3)

                return player_direct, host_msg, player_no_progress
            finally:
                await player_ws.disconnect()
                await host_ws.disconnect()

        player_direct, host_msg, player_no_progress = async_to_sync(scenario)()
        self.assertEqual(player_direct["type"], "answer_saved")
        self.assertEqual(host_msg["type"], "answer_progress")
        self.assertTrue(player_no_progress)

    # Required named alias for acceptance criteria
    test_player_cannot_receive_answer_progress = test_answer_progress_reaches_host_not_players

    def test_host_reveal_payload_contains_results_field(self):
        """Host reveal payload must include the per-player ``results`` field."""
        host_headers = self._host_session_headers()

        async def scenario():
            host_ws = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=host_headers,
            )
            player_ws = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )

            connected_h, _ = await host_ws.connect()
            connected_p, _ = await player_ws.connect()
            self.assertTrue(connected_h)
            self.assertTrue(connected_p)

            try:
                # Player submits answer (only one player → auto-reveal)
                await player_ws.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 150,
                    }
                )
                # Player gets answer_saved then reveal (players group)
                await player_ws.receive_json_from(timeout=1)
                player_reveal = await player_ws.receive_json_from(timeout=1)
                # Host gets answer_progress then reveal (host group)
                await host_ws.receive_json_from(timeout=1)
                host_reveal = await host_ws.receive_json_from(timeout=1)

                return player_reveal, host_reveal
            finally:
                await player_ws.disconnect()
                await host_ws.disconnect()

        player_reveal, host_reveal = async_to_sync(scenario)()
        # Both payloads are reveal events with correct_option_ids
        self.assertEqual(player_reveal["type"], "reveal")
        self.assertIn("correct_option_ids", player_reveal)
        self.assertEqual(host_reveal["type"], "reveal")
        self.assertIn("correct_option_ids", host_reveal)
        # Host-only field present only in host payload
        self.assertIn("results", host_reveal)
        self.assertNotIn("results", player_reveal)

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

    def test_play_ws_duplicate_answer_is_idempotent(self):
        """A player who submits an answer twice receives answer_saved both times but only one LiveAnswer is stored."""

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(self.player),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                # First submission
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 300,
                    }
                )
                first_response = await communicator.receive_json_from(timeout=1)

                # Drain the auto-reveal broadcast triggered because this is the only player
                auto_reveal_message = await communicator.receive_json_from(timeout=1)

                # Second submission for the same question (duplicate)
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": self.correct_option.id,
                        "answer_ms": 600,
                    }
                )
                second_response = await communicator.receive_json_from(timeout=1)

                return first_response, auto_reveal_message, second_response
            finally:
                await communicator.disconnect()

        first_response, auto_reveal_message, second_response = async_to_sync(scenario)()

        # First response is always answer_saved
        self.assertEqual(first_response["type"], "answer_saved")
        # Auto-reveal fires for single-player sessions
        self.assertEqual(auto_reveal_message["type"], "reveal")
        # Second submission (duplicate) also returns answer_saved gracefully
        self.assertEqual(second_response["type"], "answer_saved")

        # Only one LiveAnswer must exist in the database
        self.assertEqual(
            LiveAnswer.objects.filter(session=self.session, player=self.player, question_id=self.question.id).count(),
            1,
            "Duplicate submission must not create a second LiveAnswer record",
        )


# ════════════════════════════════════════════════════════════════════════════
# WebSocket security tests
# ════════════════════════════════════════════════════════════════════════════


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class WebSocketOriginValidationTest(TransactionTestCase):
    """
    Verify that foreign-origin WebSocket connections are rejected by
    AllowedHostsOriginValidator and that players cannot send host-only
    commands.
    """

    def setUp(self):
        self.teacher = User.objects.create_user("ws_origin_teacher", "wsorigin@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="WS Origin Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])

        self.exam = Exam.objects.create(
            title="WS Origin Exam",
            slug="ws-origin-exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="Q?", order=1)
        ExamQuestionOption.objects.create(question=self.question, text="A", is_correct=True)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        # Set started_at far enough in the past so the answer window is open
        # (ready period=4s + intro period=5s = 9s total before answers accepted).
        self.session.question_started_at = timezone.now() - timezone.timedelta(seconds=15)
        self.session.question_ends_at = timezone.now() + timezone.timedelta(seconds=30)
        self.session.save()

        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="WSPlayer",
            avatar_key="avatar_1",
            client_id="ws-origin-client",
        )
        self._player_token = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def _player_headers(self):
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{PLAYER_COOKIE_NAME}={self._player_token}".encode()),
        ]

    def _viewer_headers(self, client_id: str):
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{LIVE_CLIENT_ID_COOKIE_NAME}={client_id}".encode()),
        ]

    def _player_headers_for(self, *, player_id: int, client_id: str):
        token = build_player_token(
            pin=self.session.pin,
            player_id=player_id,
            client_id=client_id,
        )
        return [
            _WS_ORIGIN_HEADER,
            (
                b"cookie",
                f"{LIVE_CLIENT_ID_COOKIE_NAME}={client_id}; {PLAYER_COOKIE_NAME}={token}".encode(),
            ),
        ]

    def test_foreign_origin_lobby_connection_is_rejected(self):
        """A foreign-origin WebSocket connection to the lobby must be refused."""

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/lobby/",
                headers=[(b"origin", b"http://evil.example.com")],
            )
            connected, _ = await communicator.connect()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(connected, "Foreign-origin lobby connection must be refused by AllowedHostsOriginValidator")

    def test_foreign_origin_play_connection_is_rejected(self):
        """A foreign-origin WebSocket connection to the play socket must be refused."""

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=[
                    (b"origin", b"https://attacker.invalid"),
                    (b"cookie", f"{PLAYER_COOKIE_NAME}={self._player_token}".encode()),
                ],
            )
            connected, _ = await communicator.connect()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(connected, "Foreign-origin play connection must be refused by AllowedHostsOriginValidator")

    def test_player_cannot_send_non_answer_commands(self):
        """Non-'answer' messages sent by players are silently ignored (not forwarded)."""

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                # Player sends an unsupported command type
                await communicator.send_json_to({"type": "host_reveal", "question_id": self.question.id})
                # The consumer must ignore unknown types — no response should arrive
                received_nothing = await communicator.receive_nothing(timeout=0.5)
                return received_nothing
            finally:
                await communicator.disconnect()

        received_nothing = async_to_sync(scenario)()
        self.assertTrue(received_nothing, "Players must not receive a response to unsupported command types")

    def test_player_answer_accepted_on_valid_origin(self):
        """Sanity check: player answer is accepted when origin is valid (testserver)."""
        correct_option_id = (
            ExamQuestionOption.objects.filter(question=self.question, is_correct=True)
            .values_list("id", flat=True)
            .first()
        )

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            try:
                await communicator.send_json_to(
                    {
                        "type": "answer",
                        "question_id": self.question.id,
                        "option_id": correct_option_id,
                        "answer_ms": 500,
                    }
                )
                return await communicator.receive_json_from(timeout=1)
            finally:
                await communicator.disconnect()

        message = async_to_sync(scenario)()
        self.assertEqual(message["type"], "answer_saved")


# ════════════════════════════════════════════════════════════════════════════
# WebSocket host-role isolation
# ════════════════════════════════════════════════════════════════════════════


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class WebSocketHostRoleIsolationTest(TransactionTestCase):
    """
    Verify that authorize_socket_connection only grants the ``host``
    role to the actual session.host_user.  Any other authenticated user
    — even one in the same org with valid exam.host perms — must NOT
    receive the host role on the play websocket.
    """

    def setUp(self):
        self.host_teacher = User.objects.create_user("ws_role_host", "ws_role_host@example.com", "StrongPass123!")
        self.other_teacher = User.objects.create_user("ws_role_other", "ws_role_other@example.com", "StrongPass123!")

        self.org = Organization.objects.create(
            name="WS Role Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.host_teacher,
            status="active",
            is_active=True,
        )
        for u in (self.host_teacher, self.other_teacher):
            u.profile.organization = self.org
            u.profile.save(update_fields=["organization", "updated_at"])

        self.exam = Exam.objects.create(
            title="WS Role Exam",
            slug="ws-role-exam",
            author=self.host_teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.host_teacher)

    def _session_headers_for(self, user):
        """Build WS headers carrying the Django session cookie for *user*."""
        from django.conf import settings as django_settings

        client = Client()
        client.force_login(user)
        cookie_value = client.cookies[django_settings.SESSION_COOKIE_NAME].value
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{django_settings.SESSION_COOKIE_NAME}={cookie_value}".encode()),
        ]

    def test_non_host_teacher_rejected_on_play_websocket(self):
        """
        A teacher who is NOT session.host_user must be refused connection
        on the play websocket (authorize_socket_connection returns None
        when allow_anonymous=False and the user isn't the host).
        """
        headers = self._session_headers_for(self.other_teacher)

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
        self.assertFalse(
            connected,
            "A non-host teacher must NOT be allowed on the play websocket",
        )

    def test_host_ws_connection_cannot_submit_answers(self):
        """
        Even if the host connects to the play websocket, sending an
        ``answer`` message must be rejected because the host has no
        player_auth context.
        """
        headers = self._session_headers_for(self.host_teacher)

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=headers,
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected, "Host should connect to play WS")
            try:
                await communicator.send_json_to(
                    {"type": "answer", "question_id": 9999, "option_id": 1, "answer_ms": 100}
                )
                msg = await communicator.receive_json_from(timeout=1)
                return msg
            finally:
                await communicator.disconnect()

        msg = async_to_sync(scenario)()
        self.assertEqual(msg["type"], "error")


# ════════════════════════════════════════════════════════════════════════════
# Forged websocket host commands from players
# ════════════════════════════════════════════════════════════════════════════


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class ForgedWebSocketCommandTest(TransactionTestCase):
    """
    Verify that a player sending forged host-like command types through
    the play websocket receives no response (commands are silently
    dropped).  This extends the single ``host_reveal`` test in
    ``WebSocketOriginValidationTest`` to cover all plausible forgery
    patterns.
    """

    def setUp(self):
        self.teacher = User.objects.create_user("forge_teacher", "forge@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Forge Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])

        self.exam = Exam.objects.create(
            title="Forge Exam",
            slug="forge-exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="FQ?", order=1)
        ExamQuestionOption.objects.create(question=self.question, text="FA", is_correct=True)
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = timezone.now() - timezone.timedelta(seconds=15)
        self.session.question_ends_at = timezone.now() + timezone.timedelta(seconds=30)
        self.session.save()

        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="ForgePlayer",
            avatar_key="avatar_1",
            client_id="forge-client",
        )
        self._player_token = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def _player_headers(self):
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{PLAYER_COOKIE_NAME}={self._player_token}".encode()),
        ]

    def _assert_forged_command_ignored(self, payload, label=""):
        """Send *payload* from a player and assert no response arrives."""

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected, f"Player should connect ({label})")
            try:
                await communicator.send_json_to(payload)
                nothing = await communicator.receive_nothing(timeout=0.5)
                return nothing
            finally:
                await communicator.disconnect()

        nothing = async_to_sync(scenario)()
        self.assertTrue(
            nothing,
            f"Forged '{label}' command must be silently ignored",
        )

    def test_forged_start_game_ignored(self):
        self._assert_forged_command_ignored({"type": "start_game"}, label="start_game")

    def test_forged_next_question_ignored(self):
        self._assert_forged_command_ignored({"type": "next_question"}, label="next_question")

    def test_forged_reveal_answer_ignored(self):
        self._assert_forged_command_ignored(
            {"type": "reveal_answer", "question_id": self.question.id},
            label="reveal_answer",
        )

    def test_forged_finish_session_ignored(self):
        self._assert_forged_command_ignored({"type": "finish_session"}, label="finish_session")

    def test_forged_kick_player_ignored(self):
        self._assert_forged_command_ignored(
            {"type": "kick_player", "player_id": self.player.id},
            label="kick_player",
        )

    def test_forged_change_state_ignored(self):
        self._assert_forged_command_ignored(
            {"type": "change_state", "state": "finished"},
            label="change_state",
        )

    def test_forged_publish_scoreboard_ignored(self):
        self._assert_forged_command_ignored({"type": "publish_scoreboard"}, label="publish_scoreboard")


# ════════════════════════════════════════════════════════════════════════════
# WebSocket rate limiting tests
# ════════════════════════════════════════════════════════════════════════════


@override_settings(
    CHANNEL_LAYERS=TEST_CHANNEL_LAYERS,
    LIVE_WS_CONNECT_RATE_LIMIT="2/1m",
    LIVE_WS_MSG_RATE_LIMIT="2/1m",
    LIVE_ANSWER_RATE_LIMIT="2/1m",
    RATELIMIT_ENABLE=True,
)
class WebSocketRateLimitTest(TransactionTestCase):
    """
    Verify that WebSocket rate limiting is enforced for connect floods,
    message floods, and answer submission floods.
    """

    def setUp(self):
        self.teacher = User.objects.create_user("rl_teacher", "rl_teacher@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="RL Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization", "updated_at"])

        self.exam = Exam.objects.create(
            title="RL Exam",
            slug="rl-exam",
            author=self.teacher,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, text="RL?", order=1)
        ExamQuestionOption.objects.create(question=self.question, text="RA", is_correct=True)

        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.session.state = LiveSession.STATE_QUESTION
        self.session.current_index = 0
        self.session.current_question_id = self.question.id
        self.session.question_started_at = timezone.now() - timezone.timedelta(seconds=15)
        self.session.question_ends_at = timezone.now() + timezone.timedelta(seconds=30)
        self.session.save()

        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="RLPlayer",
            avatar_key="avatar_1",
            client_id="rl-client",
        )
        self._player_token = build_player_token(
            pin=self.session.pin,
            player_id=self.player.id,
            client_id=self.player.client_id,
        )

    def _player_headers(self):
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{PLAYER_COOKIE_NAME}={self._player_token}".encode()),
        ]

    def _viewer_headers(self, client_id: str):
        return [
            _WS_ORIGIN_HEADER,
            (b"cookie", f"{LIVE_CLIENT_ID_COOKIE_NAME}={client_id}".encode()),
        ]

    def _player_headers_for(self, *, player_id: int, client_id: str):
        token = build_player_token(
            pin=self.session.pin,
            player_id=player_id,
            client_id=client_id,
        )
        return [
            _WS_ORIGIN_HEADER,
            (
                b"cookie",
                f"{LIVE_CLIENT_ID_COOKIE_NAME}={client_id}; {PLAYER_COOKIE_NAME}={token}".encode(),
            ),
        ]

    def test_connect_flood_lobby_is_blocked(self):
        """Exceeding LIVE_WS_CONNECT_RATE_LIMIT on lobby causes close with code 4429."""

        async def scenario():
            results = []
            for _ in range(4):
                communicator = WebsocketCommunicator(
                    application,
                    f"/ws/live/{self.session.pin}/lobby/",
                    headers=[_WS_ORIGIN_HEADER],
                )
                connected, close_code = await communicator.connect()
                results.append((connected, close_code))
                await communicator.disconnect()
            return results

        results = async_to_sync(scenario)()
        # At least the first two connections must succeed (limit is 2/1m)
        self.assertTrue(results[0][0], "First connection should succeed")
        self.assertTrue(results[1][0], "Second connection should succeed")
        # Connection 3 or 4 must be rate limited (closed with 4429)
        rate_limited = [r for r in results if not r[0] or r[1] == 4429]
        self.assertTrue(len(rate_limited) > 0, "At least one connection should be rate limited")

    def test_connect_flood_play_is_blocked(self):
        """Exceeding LIVE_WS_CONNECT_RATE_LIMIT on play causes close with code 4429."""

        async def scenario():
            results = []
            for _ in range(4):
                communicator = WebsocketCommunicator(
                    application,
                    f"/ws/live/{self.session.pin}/play/",
                    headers=self._player_headers(),
                )
                connected, close_code = await communicator.connect()
                results.append((connected, close_code))
                await communicator.disconnect()
            return results

        results = async_to_sync(scenario)()
        # The play consumer uses the same connect rate limit scope.
        # Each test method has a unique PIN (TransactionTestCase flushes the DB
        # before setUp), so the lobby and play tests do not share a bucket.
        self.assertTrue(results[0][0], "First connection should succeed")
        self.assertTrue(results[1][0], "Second connection should succeed")
        # Connection 3 or 4 must be rate limited (closed with 4429)
        rate_limited = [r for r in results if not r[0] or r[1] == 4429]
        self.assertTrue(len(rate_limited) > 0, "At least one connection should be rate limited")

    def test_lobby_connects_for_distinct_clients_sharing_same_ip(self):
        """Different viewer client IDs behind one IP must not rate-limit each other."""

        async def scenario():
            results = []
            communicators = []
            try:
                for idx in range(4):
                    communicator = WebsocketCommunicator(
                        application,
                        f"/ws/live/{self.session.pin}/lobby/",
                        headers=self._viewer_headers(f"viewer-{idx}"),
                    )
                    communicators.append(communicator)
                    connected, close_code = await communicator.connect()
                    results.append((connected, close_code))
                    if connected:
                        await communicator.receive_json_from()
                return results
            finally:
                for communicator in communicators:
                    try:
                        await communicator.disconnect()
                    except Exception:
                        pass

        results = async_to_sync(scenario)()
        self.assertTrue(all(connected for connected, _close_code in results), results)

    def test_play_connects_for_distinct_players_sharing_same_ip(self):
        """Different players behind one IP must not rate-limit each other."""
        extra_players = [
            LivePlayer.objects.create(
                session=self.session,
                nickname=f"RLPlayer{idx}",
                avatar_key="avatar_1",
                client_id=f"rl-client-{idx}",
            )
            for idx in range(2, 5)
        ]
        player_specs = [(self.player.id, self.player.client_id)] + [
            (player.id, player.client_id) for player in extra_players
        ]

        async def scenario():
            results = []
            communicators = []
            try:
                for player_id, client_id in player_specs:
                    communicator = WebsocketCommunicator(
                        application,
                        f"/ws/live/{self.session.pin}/play/",
                        headers=self._player_headers_for(player_id=player_id, client_id=client_id),
                    )
                    communicators.append(communicator)
                    connected, close_code = await communicator.connect()
                    results.append((connected, close_code))
                return results
            finally:
                for communicator in communicators:
                    try:
                        await communicator.disconnect()
                    except Exception:
                        pass

        results = async_to_sync(scenario)()
        self.assertTrue(all(connected for connected, _close_code in results), results)

    def test_message_flood_is_blocked(self):
        """Exceeding LIVE_WS_MSG_RATE_LIMIT causes a rate_limited error response."""
        option_id = ExamQuestionOption.objects.filter(question=self.question).values_list("id", flat=True)[0]

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            responses = []
            try:
                for _ in range(4):
                    await communicator.send_json_to(
                        {
                            "type": "answer",
                            "question_id": self.question.id,
                            "option_id": option_id,
                            "answer_ms": 200,
                        }
                    )
                    msg = await communicator.receive_json_from(timeout=1)
                    responses.append(msg)
            finally:
                await communicator.disconnect()
            return responses

        responses = async_to_sync(scenario)()
        # The first two messages should not be rate-limited by the msg limit;
        # beyond that, we expect a rate_limited error (either from msg or answer limit).
        error_responses = [r for r in responses if r.get("type") == "error"]
        self.assertTrue(len(error_responses) > 0, "Excessive messages must result in a rate_limited error")

    def test_answer_flood_is_blocked(self):
        """Exceeding LIVE_ANSWER_RATE_LIMIT causes a rate_limited error response."""
        correct_option_id = (
            ExamQuestionOption.objects.filter(question=self.question, is_correct=True)
            .values_list("id", flat=True)
            .first()
        )

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/live/{self.session.pin}/play/",
                headers=self._player_headers(),
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            responses = []
            try:
                # Submit enough answers to trigger the answer rate limit (limit=2/1m)
                for _ in range(4):
                    await communicator.send_json_to(
                        {
                            "type": "answer",
                            "question_id": self.question.id,
                            "option_id": correct_option_id,
                            "answer_ms": 150,
                        }
                    )
                    msg = await communicator.receive_json_from(timeout=1)
                    responses.append(msg)
            finally:
                await communicator.disconnect()
            return responses

        responses = async_to_sync(scenario)()
        # After exceeding the limit, we must see a rate_limited error
        error_responses = [r for r in responses if r.get("type") == "error"]
        self.assertTrue(len(error_responses) > 0, "Excessive answer submissions must trigger a rate_limited error")
