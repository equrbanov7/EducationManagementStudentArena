"""
Final imtahan mərkəzi səhifəsi (/exams/final/) testləri.

* Səhifədə YALNIZ final kateqoriyalı imtahanlar görünür.
* Allowlist boşdursa hamı (login olmuş) girə bilir.
* FINAL_EXAM_ALLOWED_IPS doldurulanda yalnız uyğun IP/CIDR-lər buraxılır.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.exam_center_gate import final_exam_access_allowed, get_client_ip
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class FinalExamCenterPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fep_owner", "fep_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="FEP University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.student = User.objects.create_user("fep_student", "fep_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        cls.final_exam = Exam.objects.create(
            title="FEP Final riyaziyyat",
            author=cls.owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=True,
        )
        cls.quiz_exam = Exam.objects.create(
            title="FEP Quiz tarix",
            author=cls.owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="quiz",
            is_active=True,
            is_public=True,
        )
        cls.url = reverse("exams:final_exam_entry")

    def _client(self):
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _finished_attempt(self, *, exam=None, finished_at=None, status="submitted"):
        exam = exam or self.final_exam
        question = ExamQuestion.objects.create(
            exam=exam,
            order=exam.questions.count() + 1,
            text="Final sualı",
        )
        option = ExamQuestionOption.objects.create(
            question=question,
            label="A",
            text="Doğru cavab",
            is_correct=True,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status=status,
            finished_at=finished_at or timezone.now(),
        )
        answer = ExamAnswer.objects.create(attempt=attempt, question=question, is_correct=True)
        answer.selected_options.add(option)
        return attempt

    def _in_progress_attempt(self):
        question = ExamQuestion.objects.create(
            exam=self.final_exam,
            order=self.final_exam.questions.count() + 1,
            text="Aktiv final sualı",
        )
        option = ExamQuestionOption.objects.create(
            question=question,
            label="A",
            text="Doğru cavab",
            is_correct=True,
        )
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.final_exam, status="in_progress")
        ExamAnswer.objects.create(attempt=attempt, question=question).selected_options.add(option)
        return attempt

    def test_final_page_is_pin_login_not_exam_list(self):
        # /exams/final/ artıq imtahan siyahısı deyil — yalnız PIN giriş səhifəsi.
        response = self._client().get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="pin"', content)
        self.assertNotIn("FEP Final riyaziyyat", content)
        self.assertNotIn("FEP Quiz tarix", content)

    def test_mistyped_exmas_final_redirects_to_final_exam_center(self):
        response = self._client().get("/exmas/final")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/exams/final/")

    def test_open_to_everyone_when_allowlist_empty(self):
        with override_settings(FINAL_EXAM_ALLOWED_IPS=[]):
            response = self._client().get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_blocked_when_client_ip_not_in_allowlist(self):
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["10.20.30.40"]):
            response = self._client().get(self.url)  # test müştərisi 127.0.0.1
        self.assertEqual(response.status_code, 403)

    def test_allowed_when_client_ip_matches(self):
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["127.0.0.1"]):
            response = self._client().get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_allowed_when_client_ip_in_cidr(self):
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["127.0.0.0/8"]):
            response = self._client().get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_final_take_exam_hides_base_header(self):
        attempt = self._in_progress_attempt()
        response = self._client().get(reverse("exams:take_exam", args=[self.final_exam.slug, attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "blog-header", html=False)

    def test_final_result_hides_base_header_and_my_appeals_link(self):
        attempt = self._finished_attempt()
        response = self._client().get(reverse("exams:exam_result", args=[self.final_exam.slug, attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "blog-header", html=False)
        self.assertNotContains(response, "section=my-appeals", html=False)
        self.assertContains(response, "data-final-result-timeout", html=False)
        self.assertContains(response, "exams/js/final_result_timeout.js", html=False)

    def test_final_result_after_five_minutes_logs_out_to_final_login(self):
        attempt = self._finished_attempt(finished_at=timezone.now() - timedelta(minutes=6))
        client = self._client()

        response = client.get(reverse("exams:exam_result", args=[self.final_exam.slug, attempt.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_entry"))
        self.assertNotIn("_auth_user_id", client.session)

    def test_final_result_from_my_results_stays_viewable_after_timeout(self):
        attempt = self._finished_attempt(finished_at=timezone.now() - timedelta(minutes=6))
        client = self._client()
        back_url = reverse("accounts:profile") + "?section=my-results"

        response = client.get(
            reverse("exams:exam_result", args=[self.final_exam.slug, attempt.id]),
            {"from_section": "my-results", "return_to": back_url},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("_auth_user_id", client.session)
        self.assertNotContains(response, "data-final-result-timeout", html=False)

    def test_final_result_from_center_shows_answer_analysis_but_cabinet_hides_it(self):
        attempt = self._finished_attempt()
        client = self._client()
        result_url = reverse("exams:exam_result", args=[self.final_exam.slug, attempt.id])

        center_response = client.get(result_url)
        self.assertEqual(center_response.status_code, 200)
        self.assertContains(center_response, "Final sualı")
        self.assertContains(center_response, "Doğru cavab")
        self.assertContains(center_response, 'class="q-body"', html=False)

        cabinet_response = client.get(
            result_url,
            {
                "from_section": "my-results",
                "return_to": reverse("accounts:profile") + "?section=my-results",
            },
        )
        self.assertEqual(cabinet_response.status_code, 200)
        self.assertContains(cabinet_response, "Final sualı")
        self.assertContains(cabinet_response, "question-card--question-only")
        self.assertNotContains(cabinet_response, "Doğru cavab")
        self.assertNotContains(cabinet_response, 'class="q-body"', html=False)

    def test_midterm_result_from_cabinet_hides_answer_analysis(self):
        midterm_exam = Exam.objects.create(
            title="FEP Midterm fizika",
            author=self.owner,
            organization=self.org,
            exam_type="test",
            exam_type_extended="midterm",
            is_active=True,
            is_public=True,
        )
        attempt = self._finished_attempt(exam=midterm_exam, finished_at=timezone.now() - timedelta(minutes=6))
        response = self._client().get(
            reverse("exams:exam_result", args=[midterm_exam.slug, attempt.id]),
            {
                "from_section": "my-results",
                "return_to": reverse("accounts:profile") + "?section=my-results",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Final sualı")
        self.assertContains(response, "question-card--question-only")
        self.assertNotContains(response, "Doğru cavab")
        self.assertNotContains(response, 'class="q-body"', html=False)


class ExamCenterGateUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_get_client_ip_prefers_xff(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    def test_empty_allowlist_allows_all(self):
        request = self.factory.get("/", REMOTE_ADDR="198.51.100.7")
        with override_settings(FINAL_EXAM_ALLOWED_IPS=[]):
            self.assertTrue(final_exam_access_allowed(request))

    def test_invalid_allowlist_entry_is_skipped_not_fatal(self):
        request = self.factory.get("/", REMOTE_ADDR="192.168.1.5")
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["not-an-ip", "192.168.1.0/24"]):
            self.assertTrue(final_exam_access_allowed(request))

    def test_mismatched_ip_denied(self):
        request = self.factory.get("/", REMOTE_ADDR="192.168.2.5")
        with override_settings(FINAL_EXAM_ALLOWED_IPS=["192.168.1.0/24"]):
            self.assertFalse(final_exam_access_allowed(request))
