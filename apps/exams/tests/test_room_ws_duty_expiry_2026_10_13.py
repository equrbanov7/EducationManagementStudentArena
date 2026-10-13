"""2026-10-13 (gecə): nəzarətçi növbəsi bitəndə AÇIQ qalmış zal WS-i də bağlanır.

``FinalExamRoomConsumer`` əvvəl icazəni yalnız ``connect``-də yoxlayırdı — növbəsi bitmiş
nəzarətçi açıq tabda canlı hadisələri almağa davam edərdi. İndi ping/hadisə zamanı (ən çox
``REAUTH_INTERVAL``-da bir) təkrar yoxlanır.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.accounts.models import ProfileRole
from apps.exams.consumers import FinalExamRoomConsumer
from apps.exams.models import ExamRoom, ExamRoomSession, InvigilatorDuty
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from config.asgi import application
from core.constants import OrganizationType

User = get_user_model()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class RoomChannelDutyExpiryTests(TransactionTestCase):
    def setUp(self):
        owner = User.objects.create_user("rwd_owner", "rwd_owner@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="RWD University", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        self.invig = User.objects.create_user("rwd_invig", "rwd_invig@test.az", PASSWORD)
        _assign_user_to_org(self.invig, self.org, ProfileRole.TEACHER, "teacher")
        self.room = ExamRoom.objects.create(organization=self.org, name="Zal RW", code="ZRW", capacity=10)
        now = timezone.now()
        self.session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
            state="active",
        )
        self.duty = InvigilatorDuty.objects.create(
            organization=self.org, room=self.room, user=self.invig, starts_at=now, ends_at=now + timedelta(hours=2)
        )

    def _headers(self):
        client = Client()
        client.login(username="rwd_invig", password=PASSWORD)
        cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [(b"origin", b"http://testserver"), (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode())]

    def test_open_socket_is_closed_after_duty_revoked(self):
        duty_pk = self.duty.pk
        headers = self._headers()  # sinxron kontekstdə (login DB-yə toxunur)

        @database_sync_to_async
        def revoke():
            InvigilatorDuty.objects.filter(pk=duty_pk).update(revoked_at=timezone.now())

        async def scenario():
            communicator = WebsocketCommunicator(
                application, f"/ws/exams/final/room/{self.session.pk}/", headers=headers
            )
            connected, _ = await communicator.connect()
            if not connected:
                return None
            await communicator.send_json_to({"action": "ping"})
            first = await communicator.receive_json_from()
            await revoke()
            original = FinalExamRoomConsumer.REAUTH_INTERVAL
            FinalExamRoomConsumer.REAUTH_INTERVAL = 0.0
            try:
                await communicator.send_json_to({"action": "ping"})
                second = await communicator.receive_json_from()
                closed = await communicator.receive_output()
            finally:
                FinalExamRoomConsumer.REAUTH_INTERVAL = original
            return first, second, closed

        result = async_to_sync(scenario)()
        self.assertIsNotNone(result, "aktiv növbəli nəzarətçi qoşula bilməlidir")
        first, second, closed = result
        self.assertEqual(first, {"event": "pong"})
        self.assertEqual(second, {"event": "access_expired"})
        self.assertEqual(closed["type"], "websocket.close")
