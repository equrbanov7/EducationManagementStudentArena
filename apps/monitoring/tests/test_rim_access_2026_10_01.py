"""RİM rəhbərinin Sistem Monitorinqinə girişi (sahib 2026-10-01).

Yoxlanır:
* `system.monitoring.view` icazəsi bölməni (menyu + bölmə şablonu) və BÜTÜN oxu
  API-larını açır — RİM rəhbəri bəli, superadmin bəli, müəllim/tələbə yox;
* qapı ROL ADINA deyil, İCAZƏYƏ baxır (daraldılmış rol açarsız → 403, açarlı → 200);
* insident əməlləri superadmin-only qalır, RİM rəhbəri oxu-only görür;
* tenant sətirləri (təhlükəsizlik hadisələri) RİM rəhbərinə yalnız öz təşkilatı + org-suz;
* miqrasiya 0056 daraldılmış `ikt_rehber` roluna açarı əlavə edir (idempotent);
* log sətirlərindəki sirlər UI-a getməzdən əvvəl gizlədilir.
"""

import importlib
import json
import re
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import translation

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.monitoring.models import Incident, SecurityEvent
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

READ_APIS = [
    "monitoring:summary",
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


def _reset_rate_limits():
    from core import rate_limit

    rate_limit._RATE_LIMIT_FALLBACK_CACHE.clear()


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rimmon_owner", "rimmon_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="RIM Monitoring University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.other_owner = User.objects.create_user("rimmon_owner2", "rimmon_owner2@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="Other Monitoring University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.rim = User.objects.create_user("rimmon_head", "rimmon_head@test.az", PASSWORD)
        _assign_user_to_org(cls.rim, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.teacher = User.objects.create_user("rimmon_teacher", "rimmon_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("rimmon_student", "rimmon_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.superadmin = User.objects.create_superuser("rimmon_super", "rimmon_super@test.az", PASSWORD)

    def setUp(self):
        _reset_rate_limits()
        patcher = mock.patch("apps.monitoring.clients._get_json", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client


class RimMonitoringAccessTests(_Base):
    def test_rim_head_has_section_and_flag(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        self.rim.set_active_organization_context(self.org)  # middleware-in bağladığı kontekst
        capabilities = _role_capabilities(self.rim, self.rim.profile)
        self.assertIn("system-monitoring", capabilities["allowed_sections"])
        self.assertTrue(capabilities["can_view_monitoring"])

    def test_teacher_and_student_have_no_section(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        for user in (self.teacher, self.student):
            user.set_active_organization_context(self.org)
            capabilities = _role_capabilities(user, user.profile)
            self.assertNotIn("system-monitoring", capabilities["allowed_sections"], user.username)

    def test_rim_head_reads_every_endpoint(self):
        client = self.client_for(self.rim)
        for name in READ_APIS:
            response = client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_superadmin_reads_summary_with_platform_scope(self):
        response = self.client_for(self.superadmin).get(reverse("monitoring:summary"))
        self.assertEqual(response.status_code, 200)
        scope = response.json()["data"]["scope"]
        self.assertEqual(scope, {"platform": True, "can_manage": True})

    def test_rim_summary_is_org_scoped_and_read_only(self):
        response = self.client_for(self.rim).get(reverse("monitoring:summary"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["data"]["scope"], {"platform": False, "can_manage": False})

    def test_teacher_and_student_get_403_everywhere(self):
        for user in (self.teacher, self.student):
            client = self.client_for(user)
            for name in READ_APIS:
                self.assertEqual(client.get(reverse(name)).status_code, 403, f"{user.username} {name}")
            self.assertEqual(client.post(reverse("monitoring:ai_analysis")).status_code, 403)

    def test_denied_attempt_is_recorded(self):
        before = SecurityEvent.objects.filter(event_type="unauthorized_monitoring").count()
        self.client_for(self.teacher).get(reverse("monitoring:summary"))
        self.assertGreater(SecurityEvent.objects.filter(event_type="unauthorized_monitoring").count(), before)

    def test_anonymous_gets_401(self):
        self.assertEqual(Client().get(reverse("monitoring:summary")).status_code, 401)
        self.assertEqual(Client().post(reverse("monitoring:ai_analysis")).status_code, 401)

    def test_gate_is_permission_not_role_name(self):
        role = self.org.roles.get(name="ikt_rehber")
        original = list(role.permissions)
        try:
            role.permissions = ["user.search"]
            role.save(update_fields=["permissions"])
            self.assertEqual(self.client_for(self.rim).get(reverse("monitoring:summary")).status_code, 403)

            role.permissions = ["user.search", "system.monitoring.view"]
            role.save(update_fields=["permissions"])
            self.assertEqual(self.client_for(self.rim).get(reverse("monitoring:summary")).status_code, 200)
        finally:
            role.permissions = original
            role.save(update_fields=["permissions"])

    def test_teacher_with_explicit_key_can_read_but_not_act(self):
        role = self.org.roles.get(name="teacher")
        original = list(role.permissions)
        try:
            role.permissions = original + ["system.monitoring.view"]
            role.save(update_fields=["permissions"])
            client = self.client_for(self.teacher)
            self.assertEqual(client.get(reverse("monitoring:summary")).status_code, 200)
            response = client.post(reverse("monitoring:incident_action", args=[1]), {"action": "acknowledge"})
            self.assertEqual(response.status_code, 403)
        finally:
            role.permissions = original
            role.save(update_fields=["permissions"])

    def test_incident_actions_stay_superadmin_only(self):
        incident = Incident.objects.create(title="Disk", fingerprint="fp-rim-1", severity="high")
        client = self.client_for(self.rim)
        response = client.post(reverse("monitoring:incident_action", args=[incident.pk]), {"action": "acknowledge"})
        self.assertEqual(response.status_code, 403)
        incident.refresh_from_db()
        self.assertEqual(incident.status, "open")

        payload = client.get(reverse("monitoring:incidents") + "?status=open").json()["data"]
        self.assertFalse(payload["can_manage"])
        self.assertTrue(all(row["assigned_to"] is None for row in payload["items"]))

        superadmin_payload = self.client_for(self.superadmin).get(reverse("monitoring:incidents")).json()["data"]
        self.assertTrue(superadmin_payload["can_manage"])

    def test_security_events_are_scoped_to_own_org(self):
        SecurityEvent.objects.create(event_type="login_failed", organization=self.org, message="own")
        SecurityEvent.objects.create(event_type="login_failed", organization=None, message="platform")
        SecurityEvent.objects.create(event_type="login_failed", organization=self.other_org, message="foreign")

        ours = {"own", "platform", "foreign"}
        rim_rows = self.client_for(self.rim).get(reverse("monitoring:security_events")).json()["data"]["items"]
        self.assertEqual(sorted(row["message"] for row in rim_rows if row["message"] in ours), ["own", "platform"])

        super_rows = self.client_for(self.superadmin).get(reverse("monitoring:security_events")).json()["data"]["items"]
        self.assertEqual(
            sorted(row["message"] for row in super_rows if row["message"] in ours), ["foreign", "own", "platform"]
        )

    def test_log_lines_are_redacted(self):
        stream = [
            {
                "stream": {"container": "emsarena-app-1"},
                "values": [["1700000000000000000", "db=postgres://ems:TopSecret1@db/ems token=abcDEF123 ok"]],
            }
        ]
        with (
            mock.patch("apps.monitoring.views.LokiClient.query_range", return_value=stream),
            mock.patch("apps.monitoring.views.LokiClient.labels_values", return_value=["emsarena-app-1"]),
        ):
            response = self.client_for(self.rim).get(reverse("monitoring:logs"))
        line = response.json()["data"]["items"][0]["line"]
        self.assertNotIn("TopSecret1", line)
        self.assertNotIn("abcDEF123", line)
        self.assertIn("***", line)


class RimMonitoringShellTests(_Base):
    def test_sidebar_shows_monitoring_link_for_rim_head(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-section="system-monitoring"')

    def test_sidebar_hides_monitoring_link_for_teacher(self):
        response = self.client_for(self.teacher).get(reverse("accounts:profile"))
        self.assertNotContains(response, 'data-section="system-monitoring"')

    def test_section_renders_for_rim_head(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile") + "?section=system-monitoring")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-profile-section-panel="system-monitoring"')
        self.assertContains(response, 'id="smx-i18n"')
        self.assertContains(response, "system_monitoring_summary.js")
        self.assertContains(response, "system_monitoring_ai.js")

    def test_i18n_island_is_valid_json_in_every_language(self):
        # 2026-10-02 prod: son elementdən sonrakı vergül JSON-u sındırırdı — JS bütün lüğəti atır,
        # ekranda «whatToDo», «state_ok» kimi xam açarlar görünürdü.
        for lang in ("az", "en", "ru", "tr"):
            with translation.override(lang):
                response = self.client_for(self.rim).get(
                    reverse("accounts:profile") + "?section=system-monitoring", HTTP_ACCEPT_LANGUAGE=lang
                )
            match = re.search(
                r'<script id="smx-i18n" type="application/json">(.*?)</script>', response.content.decode(), re.S
            )
            self.assertIsNotNone(match, lang)
            strings = json.loads(match.group(1))
            self.assertGreater(len(strings), 50, lang)
            self.assertTrue(all(isinstance(v, str) and v for v in strings.values()), lang)


class MonitoringPermissionCatalogueTests(TestCase):
    def test_key_is_in_catalogue_with_label(self):
        from apps.monitoring.permissions import MONITORING_VIEW_PERMISSION
        from apps.organizations.permissions import PERMISSION_LABELS, get_all_permissions
        from apps.organizations.permissions_system import PERM_SYSTEM_MONITORING_VIEW

        self.assertEqual(MONITORING_VIEW_PERMISSION, PERM_SYSTEM_MONITORING_VIEW)
        self.assertIn(PERM_SYSTEM_MONITORING_VIEW, get_all_permissions())
        self.assertTrue(str(PERMISSION_LABELS[PERM_SYSTEM_MONITORING_VIEW]).strip())

    def test_migration_seeds_narrowed_rim_role_idempotently(self):
        migration = importlib.import_module("apps.organizations.migrations.0056_system_monitoring_view_permission")
        owner = User.objects.create_user("rimmig_owner", "rimmig_owner@test.az", PASSWORD)
        org = Organization.objects.create(
            name="Migration University",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        rim_role = org.roles.get(name="ikt_rehber")
        rector = org.roles.get(name="rector")
        teacher = org.roles.get(name="teacher")
        rim_role.permissions = ["user.search"]
        rim_role.save(update_fields=["permissions"])
        teacher_before = list(teacher.permissions)

        migration.forward(django_apps, None)
        migration.forward(django_apps, None)

        rim_role.refresh_from_db()
        rector.refresh_from_db()
        teacher.refresh_from_db()
        self.assertEqual(rim_role.permissions.count("system.monitoring.view"), 1)
        self.assertEqual(rector.permissions, ["*"])
        self.assertEqual(teacher.permissions, teacher_before)

        migration.backward(django_apps, None)
        rim_role.refresh_from_db()
        self.assertNotIn("system.monitoring.view", rim_role.permissions)
