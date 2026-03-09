"""
Consumer tests for live_exam websocket auth.
"""

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.models import LivePlayer, LiveSession
from config.asgi import application

User = get_user_model()


class LiveExamConsumerAuthTest(TestCase):
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

    def test_lobby_ws_rejects_missing_auth(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/lobby/")
            connected, _ = await communicator.connect()
            await communicator.wait()
            return connected

        connected = async_to_sync(scenario)()
        self.assertFalse(connected)

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
