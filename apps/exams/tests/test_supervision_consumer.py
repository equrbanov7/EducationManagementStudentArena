"""
EXAM-SEC-001 — ExamSupervisionConsumer autorizasiya reqressiya testləri.

Cəhdin real-time supervision kanalı (lock/resume/stop hadisələri) yalnız
cəhdin SAHİBİ tələbəyə (və müşahidə üçün imtahan müəllifi / superadmin)
açıqdır. Əvvəllər istənilən autentifikasiyalı istifadəçi ardıcıl attempt id-ni
təxmin edib başqasının kanalına qoşula bilirdi.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
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


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS, EXAM_SUPERVISION_ENABLED=True)
class ExamSupervisionConsumerAuthTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("sup_owner", "sup_owner@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="SUP University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.teacher = User.objects.create_user("sup_teacher", "sup_teacher@test.az", PASSWORD)
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.student = User.objects.create_user("sup_student", "sup_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        self.other_student = User.objects.create_user("sup_other", "sup_other@test.az", PASSWORD)
        _assign_user_to_org(self.other_student, self.org, ProfileRole.STUDENT, "student")

        self.exam = Exam.objects.create(
            title="SUP Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")

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

    def _path(self, attempt_id):
        return f"/ws/exams/supervision/{attempt_id}/"

    def test_accepts_attempt_owner(self):
        connected = self._try_connect(self._path(self.attempt.pk), self._session_headers("sup_student"))
        self.assertTrue(connected)

    def test_rejects_other_student(self):
        """EXAM-SEC-001: başqa tələbə cəhdin supervision kanalına qoşula bilməz."""
        connected = self._try_connect(self._path(self.attempt.pk), self._session_headers("sup_other"))
        self.assertFalse(connected)

    def test_accepts_exam_author(self):
        connected = self._try_connect(self._path(self.attempt.pk), self._session_headers("sup_teacher"))
        self.assertTrue(connected)

    def test_rejects_unauthenticated(self):
        connected = self._try_connect(self._path(self.attempt.pk), [_WS_ORIGIN_HEADER])
        self.assertFalse(connected)

    def test_rejects_unknown_attempt(self):
        connected = self._try_connect(self._path(999999), self._session_headers("sup_student"))
        self.assertFalse(connected)
