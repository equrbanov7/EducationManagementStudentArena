"""
Final imtahan mərkəzi səhifəsi (/exams/final/) testləri.

* Səhifədə YALNIZ final kateqoriyalı imtahanlar görünür.
* Allowlist boşdursa hamı (login olmuş) girə bilir.
* FINAL_EXAM_ALLOWED_IPS doldurulanda yalnız uyğun IP/CIDR-lər buraxılır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
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
        cls.url = reverse("exams:final_exam_list")

    def _client(self):
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_shows_only_final_exams(self):
        response = self._client().get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("FEP Final riyaziyyat", content)
        self.assertNotIn("FEP Quiz tarix", content)

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
