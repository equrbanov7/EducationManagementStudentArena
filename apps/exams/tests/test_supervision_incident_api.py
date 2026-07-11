"""
EXAM-P1-10 — supervision incident POST endpoint sərtləşdirmə testləri.

Tələbə brauzerindən gələn incident payload-u etibarsızdır: event_type
allowlist-inə görə yoxlanır, metadata sanitizasiya olunur (nested/böyük
dict saxlanmır) və per-attempt rate limit tətbiq edilir.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamAttempt, SupervisionIncident
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


@override_settings(EXAM_SUPERVISION_ENABLED=True, RATELIMIT_ENABLE=True)
class SupervisionIncidentApiHardeningTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("supi_owner", "supi_owner@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="SUPI University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.teacher = User.objects.create_user("supi_teacher", "supi_teacher@test.az", PASSWORD)
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.student = User.objects.create_user("supi_student", "supi_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")

        from apps.exams.models import Exam, ExamSupervisionConfig

        self.exam = Exam.objects.create(
            title="SUPI Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )
        ExamSupervisionConfig.objects.create(exam=self.exam, enabled=True)
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")

        # Rate-limit cache test metodları arasında paylaşılır (attempt.id hər
        # rollback-dan sonra təkrarlana bilər) — təmiz vəziyyətdən başla.
        # DummyCache olduqda rate-limit process-local fallback cache-dən
        # istifadə edir, ona görə birbaşa onu təmizləyirik.
        from core.rate_limit import _rate_limit_cache

        _rate_limit_cache().clear()

        self.client = Client()
        self.client.login(username="supi_student", password=PASSWORD)
        self.url = reverse("exams:supervision_log_incident", args=[self.attempt.id])

    def _post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def test_rejects_invalid_event_type(self):
        response = self._post({"event_type": "definitely_not_a_real_event", "metadata": {}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupervisionIncident.objects.count(), 0)

    def test_sanitizes_nested_and_oversized_metadata(self):
        big_value = "x" * 5000
        response = self._post(
            {
                "event_type": "tab_switched",
                "metadata": {
                    "nested": {"deep": {"deeper": [1, 2, 3]}},
                    "huge": big_value,
                    "num": 5,
                    "flag": True,
                },
            }
        )
        self.assertEqual(response.status_code, 200)
        incident = SupervisionIncident.objects.latest("id")
        md = incident.metadata
        # Nested dict string-ə endirilib, primitivlər qalıb.
        self.assertIsInstance(md["nested"], str)
        self.assertLessEqual(len(md["huge"]), 500)
        self.assertEqual(md["num"], 5)
        self.assertTrue(md["flag"])

    def test_caps_number_of_metadata_keys(self):
        metadata = {f"k{i}": i for i in range(50)}
        response = self._post({"event_type": "tab_switched", "metadata": metadata})
        self.assertEqual(response.status_code, 200)
        incident = SupervisionIncident.objects.latest("id")
        self.assertLessEqual(len(incident.metadata), 20)

    def test_per_attempt_rate_limit(self):
        # Rate _SUPERVISION_INCIDENT_RATE = 60/1m; 60-dan sonrakı sorğu 429.
        last_status = 200
        for _ in range(65):
            last_status = self._post({"event_type": "tab_switched", "metadata": {}}).status_code
            if last_status == 429:
                break
        self.assertEqual(last_status, 429)

    def test_non_dict_metadata_is_rejected(self):
        response = self._post({"event_type": "tab_switched", "metadata": "not-a-dict"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupervisionIncident.objects.count(), 0)

    def test_json_root_must_be_object(self):
        response = self.client.post(self.url, data="[]", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupervisionIncident.objects.count(), 0)

    def test_unknown_root_field_is_rejected(self):
        response = self._post({"event_type": "tab_switched", "metadata": {}, "unexpected": True})
        self.assertEqual(response.status_code, 400)

    def test_oversized_body_is_rejected_before_json_processing(self):
        response = self._post({"event_type": "tab_switched", "metadata": {"blob": "x" * 20000}})
        self.assertEqual(response.status_code, 413)

    def test_violation_count_increments_without_lost_updates(self):
        self.assertEqual(self._post({"event_type": "tab_switched", "metadata": {}}).status_code, 200)
        self.assertEqual(self._post({"event_type": "tab_switched", "metadata": {}}).status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.supervision_violation_count, 2)
