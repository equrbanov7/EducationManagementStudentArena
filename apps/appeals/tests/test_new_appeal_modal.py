"""Part B: "Yeni apellyasiya müraciəti" modalı — uyğun final/midterm cəhdləri.

Modal yalnız 3-günlük pəncərəsi hələ açıq olan bitmiş FINAL/MIDTERM cəhdləri
göstərir; adi test/quiz və pəncərəsi bağlanmış cəhdlər siyahıya düşmür.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.appeals.tests.test_creation import _assign_user_to_org
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class NewAppealEligibleAttemptsTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("na_teacher", "na_t@example.com", "pw")
        self.student = User.objects.create_user("na_student", "na_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="NA Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _exam(self, title, extended):
        return Exam.objects.create(
            title=title,
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended=extended,
            is_active=True,
        )

    def _attempt(self, exam, *, days_ago=0):
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        attempt.finished_at = timezone.now() - timedelta(days=days_ago)
        attempt.save(update_fields=["finished_at"])
        return attempt

    def _section_response(self):
        return self.client.get(reverse("accounts:profile") + "?section=my-appeals")

    def test_modal_lists_final_and_midterm_within_window(self):
        final_exam = self._exam("FINAL_ELIGIBLE_SENTINEL", "final")
        midterm_exam = self._exam("MIDTERM_ELIGIBLE_SENTINEL", "midterm")
        self._attempt(final_exam, days_ago=0)
        self._attempt(midterm_exam, days_ago=1)

        response = self._section_response()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="newAppealModal"')
        self.assertContains(response, "FINAL_ELIGIBLE_SENTINEL")
        self.assertContains(response, "MIDTERM_ELIGIBLE_SENTINEL")

    def test_regular_test_exam_is_not_eligible(self):
        regular = self._exam("REGULAR_TEST_SENTINEL", "quiz")
        self._attempt(regular, days_ago=0)

        response = self._section_response()
        self.assertNotContains(response, "REGULAR_TEST_SENTINEL")

    def test_expired_window_final_is_not_eligible(self):
        expired_final = self._exam("EXPIRED_FINAL_SENTINEL", "final")
        self._attempt(expired_final, days_ago=5)

        response = self._section_response()
        self.assertNotContains(response, "EXPIRED_FINAL_SENTINEL")

    def test_eligible_attempts_expose_appeal_create_url(self):
        final_exam = self._exam("URL_FINAL_SENTINEL", "final")
        attempt = self._attempt(final_exam, days_ago=0)

        response = self._section_response()
        expected_url = reverse("appeals:appeal_create", kwargs={"attempt_id": attempt.id})
        self.assertContains(response, expected_url)
