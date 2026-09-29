"""LX-SEC — WebSocket PoC-ları (consumers.py LX-BE-yə məxsusdur; bax SECURITY_REVIEW.md LXS-15).

Bu testlər TƏHLÜKƏSİZ davranışı iddia edir (LX-BE düzəlişindən sonra ``xfail``
işarələri götürülüb — consumer_support: anonim socket PIN-dən asılı olmayaraq 4401).

* anonim «viewer» yalnız PIN ilə lobbi soketinə qoşulub oyunçu siyahısını
  (ləqəblər) və reaksiyaları oxuyur; mövcud/mövcud olmayan PIN fərqli bağlanır
  (limitsiz PIN orakulu) — heç bir klient anonim lobbi soketi istifadə etmir
  (host və gözləmə otağı token/sessiya ilə qoşulur);
* host oyunçunu çıxaranda həmin oyunçunun açıq lobbi soketi bağlanmır.
"""

from __future__ import annotations

from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator

from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.models import LivePlayer
from config.asgi import application

from .lx_sec_support import make_exam, make_org, make_session, make_teacher, reset_rate_limits

_ORIGIN = (b"origin", b"http://testserver")
_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=_LAYERS)
class LobbySocketExposureTest(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("lxs_ws_owner", "lxs_ws_owner@example.com", "StrongPass123!")
        self.org = make_org("LXS WS Org", owner)
        self.host = make_teacher("lxs_ws_host", self.org)
        self.exam = make_exam(self.host, self.org, "lxs-ws-exam")
        self.session = make_session(self.exam, self.host)
        self.player = LivePlayer.objects.create(session=self.session, nickname="Secret Name", client_id="lxs-ws-1")

    def _connect(self, pin, headers):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/live/{pin}/lobby/", headers=headers)
            connected, code = await communicator.connect()
            payload = await communicator.receive_json_from() if connected else None
            if connected:
                await communicator.disconnect()
            return connected, code, payload

        return async_to_sync(scenario)()

    def test_anonymous_viewer_cannot_read_the_roster(self):
        connected, _code, payload = self._connect(self.session.pin, [_ORIGIN])
        self.assertFalse(connected, payload)

    def test_lobby_socket_is_not_a_pin_oracle(self):
        real = self._connect(self.session.pin, [_ORIGIN])
        ghost = self._connect("ZZZZZZZZZZ", [_ORIGIN])
        self.assertEqual(real[:2], ghost[:2])

    def test_kicked_player_socket_is_closed(self):
        token = build_player_token(pin=self.session.pin, player_id=self.player.id, client_id=self.player.client_id)
        headers = [_ORIGIN, (b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())]
        host_client = Client()
        host_client.force_login(self.host)
        django_session = host_client.session
        django_session["active_organization"] = self.org.slug
        django_session.save()

        url = reverse("liveExam:host_remove_player", kwargs={"pin": self.session.pin})

        # LX-BE: bütün ssenari TƏK event loop-da (əvvəlki iki ``async_to_sync`` çağırışı
        # communicator-u ölü loop-da qoyurdu → CancelledError).
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/live/{self.session.pin}/lobby/", headers=headers)
            connected, _ = await communicator.connect()
            assert connected
            await communicator.receive_json_from()  # ilkin lobby_state
            kick = await sync_to_async(host_client.post)(url, {"player_id": self.player.id})
            outputs = []
            while not await communicator.receive_nothing(timeout=1):
                output = await communicator.receive_output()
                outputs.append(output)
                if output.get("type") == "websocket.close":
                    break
            return kick.status_code, outputs

        status_code, outputs = async_to_sync(scenario)()
        self.assertEqual(status_code, 200)
        self.assertTrue(any(item.get("type") == "websocket.close" for item in outputs), outputs)
