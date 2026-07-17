"""Zal monitoru — bir cəhdin pozuntu detalları endpoint-i.

`exam_center_attempt_violations`: zal nəzarətçisi tələbə xanasına / "Bax"a
klik edəndə hansı qaydaların pozulduğunu (SupervisionIncident) qaytarır.
Skop: yalnız həmin zala möhürlənmiş cəhdlər (tenant + zal).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamRoom, SupervisionIncident
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class RoomAttemptViolationsApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("rvio_owner", "rvio_owner@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="RVIO University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.staff = User.objects.create_user("rvio_staff", "rvio_staff@test.az", PASSWORD)
        _assign_user_to_org(self.staff, self.org, ProfileRole.TEACHER, "teacher")
        self.student = User.objects.create_user("rvio_student", "rvio_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")

        self.room = ExamRoom.objects.create(organization=self.org, name="Zal V", code="ZV", capacity=20)
        self.room.invigilators.add(self.staff)  # zala təyin olunmuş nəzarətçi

        self.exam = Exam.objects.create(
            title="RVIO Exam", author=self.owner, organization=self.org, exam_type="test", is_active=True
        )
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        self.attempt.room = self.room
        self.attempt.save(update_fields=["room"])
        SupervisionIncident.objects.create(
            organization=self.org,
            exam=self.exam,
            attempt=self.attempt,
            student=self.student,
            event_type="tab_switched",
            severity="high",
        )

        self.client = Client()
        self.client.force_login(self.staff)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _url(self, attempt_id):
        return reverse(
            "exams:exam_center_attempt_violations",
            kwargs={"room_id": self.room.pk, "attempt_id": attempt_id},
        )

    def test_supervisor_sees_violation_incidents(self):
        resp = self.client.get(self._url(self.attempt.pk))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["incidents"]), 1)
        self.assertEqual(data["incidents"][0]["code"], "tab_switched")
        self.assertTrue(data["incidents"][0]["event"])  # tərcümə olunmuş etiket
        self.assertEqual(data["exam_title"], "RVIO Exam")

    def test_attempt_outside_room_is_404(self):
        other_exam = Exam.objects.create(
            title="RVIO Other", author=self.owner, organization=self.org, exam_type="test", is_active=True
        )
        other = ExamAttempt.objects.create(user=self.student, exam=other_exam, status="in_progress")  # zalsız
        resp = self.client.get(self._url(other.pk))
        self.assertEqual(resp.status_code, 404)
