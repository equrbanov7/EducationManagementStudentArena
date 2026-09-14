"""W3 `w3sweep` (2026-09-14): PIN axtarışı — vaxt pəncərəsi və status etiketi.

Brauzer süpürgəsi (qa.exam_center_head → PIN axtarışı → tələbə): 14.09→30.10
pəncərəsi «14.09.2026 00:00–23:00» görünürdü (bitmə həmişə yalnız saat idi) və
status nişanı xam «assigned» açarı idi.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.student_pins import provision_exam_student_pins
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class PinLookupWindowAndStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("w3pl_owner", "w3pl_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="W3PL Uni", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.center = User.objects.create_user("w3pl_center", "w3pl_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.student = User.objects.create_user("w3pl_student", "w3pl_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.start = timezone.make_aware(datetime(2026, 9, 14, 0, 0))
        cls.end = timezone.make_aware(datetime(2026, 10, 30, 23, 0))
        cls.exam = Exam.objects.create(
            title="W3PL Wizard Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            start_datetime=cls.start,
            end_datetime=cls.end,
        )
        cls.exam.allowed_users.add(cls.student)
        provision_exam_student_pins(cls.exam)

    def _client(self):
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _detail(self):
        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.student.id})
        with translation.override("az"):
            response = self._client().get(url)
        self.assertEqual(response.status_code, 200)
        return response.json()["tickets"]

    def test_multi_day_window_keeps_end_date(self):
        ticket = self._detail()[0]
        self.assertEqual(ticket["scheduled_start"], "14.09.2026 00:00")
        self.assertEqual(ticket["scheduled_end"], "30.10.2026 23:00")

    def test_same_day_session_end_is_time_only(self):
        room = ExamRoom.objects.create(organization=self.org, name="Zal", code="W3Z1", capacity=20)
        start = timezone.make_aware(datetime(2026, 9, 20, 9, 0))
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            invigilator=self.center,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=2),
        )
        FinalExamTicket.objects.create(organization=self.org, session=session, exam=self.exam, student=self.student)
        tickets = self._detail()
        with_session = next(t for t in tickets if t["room"] == "Zal")
        self.assertEqual(with_session["scheduled_start"], "20.09.2026 09:00")
        self.assertEqual(with_session["scheduled_end"], "11:00")

    def test_status_is_translated_label_with_raw_key_alongside(self):
        ticket = self._detail()[0]
        self.assertEqual(ticket["status_key"], "assigned")
        self.assertEqual(ticket["status"], "Təyin edilib")
