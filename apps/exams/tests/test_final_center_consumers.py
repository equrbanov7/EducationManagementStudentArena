"""
Final imtahan mərkəzi — WebSocket autorizasiya testləri.

* Tələbə heyət (monitor) kanalına qoşula BİLMƏZ.
* Yalnız biletin sahibi öz gözləmə kanalına qoşula bilər.
* Nəzarətçi/imtahan mərkəzi otaq kanalına qoşulur; başqa org-un mərkəzi yox.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import TICKET_STATUS_WAITING
from apps.exams.models import Exam, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import open_entry
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from config.asgi import application
from core.constants import OrganizationType

User = get_user_model()

_WS_ORIGIN_HEADER = (b"origin", b"http://testserver")

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class FinalCenterConsumerAuthTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("fcc_owner", "fcc_owner@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="FCC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.center = User.objects.create_user("fcc_center", "fcc_center@test.az", PASSWORD)
        _assign_user_to_org(self.center, self.org, ProfileRole.MEMBER, "exam_center_head")
        self.student = User.objects.create_user("fcc_student", "fcc_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        self.student2 = User.objects.create_user("fcc_student2", "fcc_student2@test.az", PASSWORD)
        _assign_user_to_org(self.student2, self.org, ProfileRole.STUDENT, "student")

        self.other_owner = User.objects.create_user("fcc_owner2", "fcc_owner2@test.az", PASSWORD)
        self.other_org = Organization.objects.create(
            name="FCC Other",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.other_owner,
            status="active",
            is_active=True,
        )
        self.other_center = User.objects.create_user("fcc_center2", "fcc_center2@test.az", PASSWORD)
        _assign_user_to_org(self.other_center, self.other_org, ProfileRole.MEMBER, "exam_center_head")

        self.exam = Exam.objects.create(
            title="FCC Final",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
        )
        self.room = ExamRoom.objects.create(organization=self.org, name="Zal WS", code="ZWS", capacity=10)
        now = timezone.now()
        self.session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.center,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
        )
        open_entry(self.session, self.center)
        self.ticket = FinalExamTicket.objects.create(
            organization=self.org,
            session=self.session,
            exam=self.exam,
            student=self.student,
            status=TICKET_STATUS_WAITING,
        )

    def _session_headers(self, username):
        client = Client()
        client.login(username=username, password=PASSWORD)
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        return [_WS_ORIGIN_HEADER, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode())]

    def _try_connect(self, path, headers):
        async def scenario():
            communicator = WebsocketCommunicator(application, path, headers=headers)
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            else:
                await communicator.wait()
            return connected

        return async_to_sync(scenario)()

    def test_room_channel_rejects_student(self):
        connected = self._try_connect(
            f"/ws/exams/final/room/{self.session.pk}/",
            self._session_headers("fcc_student"),
        )
        self.assertFalse(connected)

    def test_room_channel_rejects_unauthenticated(self):
        connected = self._try_connect(f"/ws/exams/final/room/{self.session.pk}/", [_WS_ORIGIN_HEADER])
        self.assertFalse(connected)

    def test_room_channel_accepts_exam_center_of_same_org(self):
        connected = self._try_connect(
            f"/ws/exams/final/room/{self.session.pk}/",
            self._session_headers("fcc_center"),
        )
        self.assertTrue(connected)

    def test_room_channel_rejects_exam_center_of_other_org(self):
        """Tenant izolyasiyası: qlobal exam_center rolu başqa org-a keçmir."""
        connected = self._try_connect(
            f"/ws/exams/final/room/{self.session.pk}/",
            self._session_headers("fcc_center2"),
        )
        self.assertFalse(connected)

    def test_wait_channel_accepts_ticket_owner(self):
        connected = self._try_connect(
            f"/ws/exams/final/wait/{self.ticket.pk}/",
            self._session_headers("fcc_student"),
        )
        self.assertTrue(connected)

    def test_wait_channel_rejects_other_student(self):
        connected = self._try_connect(
            f"/ws/exams/final/wait/{self.ticket.pk}/",
            self._session_headers("fcc_student2"),
        )
        self.assertFalse(connected)

    def test_wait_channel_rejects_removed_ticket(self):
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(status="removed")
        connected = self._try_connect(
            f"/ws/exams/final/wait/{self.ticket.pk}/",
            self._session_headers("fcc_student"),
        )
        self.assertFalse(connected)
