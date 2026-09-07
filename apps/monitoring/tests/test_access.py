"""Sistem Monitorinqi — giriş nəzarəti matrisi.

Tələb: BÜTÜN monitorinq API-ları yalnız platforma superadmininə açıqdır.
Rector/vice-rector/exam-center/HR/dean/chair-head/teacher/student/owner —
hamısı 403 alır; anonim 401; icazəsiz cəhd SecurityEvent-ə yazılır;
``is_staff`` bayrağı TƏK BAŞINA giriş vermir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.monitoring.models import SecurityEvent
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

#: (istifadəçi adı, membership rol adı, profil rolu)
ROLE_MATRIX = [
    ("mon_rector", "rector", ProfileRole.MEMBER),
    ("mon_vice", "vice_rector", ProfileRole.MEMBER),
    ("mon_center", "exam_center_head", ProfileRole.MEMBER),
    ("mon_hr", "hr", ProfileRole.MEMBER),
    ("mon_dean", "dean", ProfileRole.MEMBER),
    ("mon_chair", "chair_head", ProfileRole.MEMBER),
    ("mon_teacher", "teacher", ProfileRole.TEACHER),
    ("mon_student", "student", ProfileRole.STUDENT),
]

API_NAMES = [
    "monitoring:overview",
    "monitoring:server",
    "monitoring:containers",
    "monitoring:application",
    "monitoring:database",
    "monitoring:redis_celery",
    "monitoring:exams",
    "monitoring:alerts",
    "monitoring:logs",
    "monitoring:incidents",
    "monitoring:security_events",
]


class MonitoringAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mon_owner", "mon_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Monitoring University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.role_users = {}
        for username, role_name, profile_role in ROLE_MATRIX:
            user = User.objects.create_user(username, f"{username}@test.az", PASSWORD)
            _assign_user_to_org(user, cls.org, profile_role, role_name)
            cls.role_users[role_name] = user

        cls.superadmin = User.objects.create_superuser("mon_super", "mon_super@test.az", PASSWORD)
        # is_staff bayrağı olan, amma superadmin OLMAYAN istifadəçi.
        cls.staff_only = User.objects.create_user("mon_staff", "mon_staff@test.az", PASSWORD, is_staff=True)

    def _get(self, user, url_name):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client.get(reverse(url_name))

    def test_superadmin_can_access_every_endpoint(self):
        for name in API_NAMES:
            response = self._get(self.superadmin, name)
            # Prometheus/Loki test mühitində yoxdur → degraded JSON, amma 200.
            self.assertEqual(response.status_code, 200, name)

    def test_all_org_roles_get_403(self):
        for role_name, user in self.role_users.items():
            response = self._get(user, "monitoring:overview")
            self.assertEqual(response.status_code, 403, f"{role_name} 403 almalı idi")

    def test_org_owner_gets_403(self):
        response = self._get(self.owner, "monitoring:overview")
        self.assertEqual(response.status_code, 403)

    def test_is_staff_alone_is_not_enough(self):
        response = self._get(self.staff_only, "monitoring:overview")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_401(self):
        response = self._get(None, "monitoring:overview")
        self.assertEqual(response.status_code, 401)

    def test_unauthorized_attempt_is_recorded(self):
        before = SecurityEvent.objects.filter(event_type="unauthorized_monitoring").count()
        self._get(self.role_users["student"], "monitoring:overview")
        after = SecurityEvent.objects.filter(event_type="unauthorized_monitoring").count()
        self.assertGreater(after, before)

    def test_incident_action_requires_superadmin(self):
        client = Client()
        client.force_login(self.role_users["rector"])
        response = client.post(reverse("monitoring:incident_action", args=[1]), {"action": "acknowledge"})
        self.assertEqual(response.status_code, 403)

    def test_section_not_in_allowed_sections_for_regular_user(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        user = self.role_users["teacher"]
        capabilities = _role_capabilities(user, user.profile)
        self.assertNotIn("system-monitoring", capabilities["allowed_sections"])

    def test_section_allowed_for_superadmin(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        capabilities = _role_capabilities(self.superadmin, getattr(self.superadmin, "profile", None))
        self.assertIn("system-monitoring", capabilities["allowed_sections"])
