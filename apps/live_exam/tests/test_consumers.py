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
from apps.organizations.models import Organization
from config.asgi import application
from core.constants import OrganizationType

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
        return [(b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]

    def _host_session_headers(self):
        client = Client()
        client.login(username="answer_teacher", password="StrongPass123!")
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [(b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode())]

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
        second_player = LivePlayer.objects.create(
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
