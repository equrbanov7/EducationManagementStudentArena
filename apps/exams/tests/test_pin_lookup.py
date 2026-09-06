"""
İmtahan mərkəzi — istifadəçi adı üzrə PIN axtarışı (exam_center_pin_lookup).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import set_ticket_pin
from apps.exams.services.student_pins import provision_exam_student_pins, student_visible_pin
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class PinLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pl_owner", "pl_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PL Uni",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("pl_center", "pl_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.student = User.objects.create_user("pl_student", "pl_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.pin_student = User.objects.create_user("pl_pin_student", "pl_pin_student@test.az", PASSWORD)
        _assign_user_to_org(cls.pin_student, cls.org, ProfileRole.STUDENT, "student")
        cls.teacher = User.objects.create_user("pl_teacher", "pl_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

        cls.exam = Exam.objects.create(
            title="PL Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
        )
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal", code="Z1", capacity=20)
        now = timezone.now()
        cls.session = ExamRoomSession.objects.create(
            organization=cls.org,
            room=cls.room,
            invigilator=cls.center,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=3),
        )
        cls.ticket = FinalExamTicket.objects.create(
            organization=cls.org, session=cls.session, exam=cls.exam, student=cls.student
        )
        cls.raw_pin = set_ticket_pin(cls.ticket, cls.center)
        cls.pin_exam = Exam.objects.create(
            title="Wizard Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
        )
        cls.pin_exam.allowed_users.add(cls.pin_student, cls.teacher)
        provision_exam_student_pins(cls.pin_exam)
        cls.raw_student_pin = student_visible_pin(cls.pin_exam, cls.pin_student)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_page_shell_renders(self):
        # Səhifə qabığı (data AJAX ilə gəlir — PIN səhifədə birbaşa YOX).
        response = self._client(self.center).get(reverse("exams:exam_center_pin_lookup"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.raw_pin)

    def test_search_finds_student(self):
        response = self._client(self.center).get(reverse("exams:exam_center_pin_search"), {"q": "pl_student"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = [r["id"] for r in data["results"]]
        self.assertIn(self.student.id, ids)

    def test_student_detail_reveals_pin(self):
        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.student.id})
        response = self._client(self.center).get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        pins = [t["pin"] for t in data["tickets"]]
        self.assertIn(self.raw_pin, pins)
        self.assertEqual(data["tickets"][0]["exam_title"], "PL Final")

    def test_search_and_detail_include_wizard_student_pin(self):
        response = self._client(self.center).get(reverse("exams:exam_center_pin_search"), {"q": "pl_pin_student"})
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.json()["results"]]
        self.assertIn(self.pin_student.id, ids)

        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.pin_student.id})
        detail_response = self._client(self.center).get(url)
        self.assertEqual(detail_response.status_code, 200)
        data = detail_response.json()
        pins = [t["pin"] for t in data["tickets"]]
        self.assertIn(self.raw_student_pin, pins)
        self.assertEqual(data["tickets"][0]["exam_title"], "Wizard Final")

    def test_search_and_detail_exclude_non_student_pin_holders(self):
        response = self._client(self.center).get(reverse("exams:exam_center_pin_search"), {"q": "pl_teacher"})
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.json()["results"]]
        self.assertNotIn(self.teacher.id, ids)

        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.teacher.id})
        detail_response = self._client(self.center).get(url)
        self.assertEqual(detail_response.status_code, 404)

    def test_revoked_pin_not_revealed(self):
        from apps.exams.services.final_center import revoke_ticket_pin

        revoke_ticket_pin(self.ticket)
        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.student.id})
        response = self._client(self.center).get(url)
        self.assertEqual(response.status_code, 200)
        pins = [t["pin"] for t in response.json()["tickets"]]
        self.assertNotIn(self.raw_pin, pins)

    def test_non_center_forbidden(self):
        # Müəllim imtahan mərkəzi deyil → 403 (səhifə + AJAX).
        self.assertEqual(self._client(self.teacher).get(reverse("exams:exam_center_pin_lookup")).status_code, 403)
        self.assertEqual(
            self._client(self.teacher).get(reverse("exams:exam_center_pin_search"), {"q": "pl"}).status_code, 403
        )
