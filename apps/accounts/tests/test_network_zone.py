"""Şəbəkə zonası qapısı (sahib 2026-09-21): tələbə kənardan ✓, müəllim kənardan ✓
amma /jurnal/ ✗, inzibati kənardan ✗ (çıxış açıq), daxildən hamı ✓; başlığa yalnız
NETWORK_ZONE_TRUST_HEADER ilə inanılır; enforce söndürüləndə heç nə dəyişmir."""

from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.accounts.network_zone import account_kind, zone_for_ip

from .test_view_as import PASSWORD, User, ViewAsTestBase, _add_member, _make_role

ZONE = {"NETWORK_ZONE_ENFORCED": True, "INTERNAL_NETWORKS": ["10.0.0.0/8", "127.0.0.0/8"]}


class ZoneHelpersTest(ViewAsTestBase):
    @override_settings(**ZONE)
    def test_zone_for_ip_and_account_kind(self):
        self.assertEqual(zone_for_ip("10.0.2.120"), "internal")
        self.assertEqual(zone_for_ip("127.0.0.1"), "internal")
        self.assertEqual(zone_for_ip("85.132.1.1"), "external")
        self.assertEqual(zone_for_ip("zibil"), "external")
        rf = RequestFactory()

        def kind(user):
            request = rf.get("/")
            request.user = user
            request.organization = self.org
            request.org_memberships = list(user.memberships.filter(is_active=True).select_related("role"))
            return account_kind(request)

        self.assertEqual(kind(self.student), "student")
        self.assertEqual(kind(self.teacher), "teacher")
        self.assertEqual(kind(self.admin), "staff")
        self.assertEqual(kind(self.tutor), "staff")
        self.assertEqual(kind(self.superadmin), "staff")
        # müəllim + kafedra müdiri = inzibati (sərt qayda üstündür)
        chair = _make_role(self.org, "chair_head", 70)
        both = User.objects.create_user("both1", "both@example.com", PASSWORD)
        _add_member(both, self.org, self.teacher_role)
        from apps.organizations.models import Membership

        Membership.objects.create(user=both, organization=self.org, role=chair, is_active=True, is_primary=False)
        self.assertEqual(kind(both), "staff")


class ZoneMiddlewareTest(ViewAsTestBase):
    EXT = "85.132.1.1"
    INT = "10.0.2.50"

    def _get(self, user, path, ip):
        self._login(user)
        return self.client.get(path, REMOTE_ADDR=ip, HTTP_HOST="testserver")

    @override_settings(**ZONE)
    def test_student_and_teacher_work_from_outside_but_journal_is_internal(self):
        profile = reverse("accounts:profile")
        self.assertEqual(self._get(self.student, profile, self.EXT).status_code, 200)
        self.assertEqual(self._get(self.teacher, profile, self.EXT).status_code, 200)
        response = self._get(self.teacher, "/jurnal/", self.EXT)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "errors/network_zone.html")
        self.assertIn("Elektron jurnal yalnız universitet", response.content.decode())
        self.assertNotEqual(self._get(self.teacher, "/jurnal/", self.INT).status_code, 403)

    @override_settings(**ZONE)
    def test_staff_is_blocked_outside_except_logout_and_allowed_inside(self):
        profile = reverse("accounts:profile")
        response = self._get(self.admin, profile, self.EXT)
        self.assertEqual(response.status_code, 403)
        self.assertIn("yalnız universitet şəbəkəsindən", response.content.decode())
        self.assertEqual(self._get(self.admin, profile, self.INT).status_code, 200)
        self.assertNotEqual(self._get(self.admin, reverse("accounts:logout"), self.EXT).status_code, 403)
        response = self.client.get(profile, REMOTE_ADDR=self.EXT, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["reason"], "staff_internal_only")

    @override_settings(**ZONE, NETWORK_ZONE_TRUST_HEADER=False)
    def test_client_zone_header_is_ignored_unless_trusted(self):
        profile = reverse("accounts:profile")
        self._login(self.admin)
        response = self.client.get(profile, REMOTE_ADDR=self.EXT, HTTP_X_EMS_ZONE="internal")
        self.assertEqual(response.status_code, 403)
        with override_settings(NETWORK_ZONE_TRUST_HEADER=True):
            response = self.client.get(profile, REMOTE_ADDR=self.EXT, HTTP_X_EMS_ZONE="internal")
            self.assertEqual(response.status_code, 200)

    @override_settings(NETWORK_ZONE_ENFORCED=False, INTERNAL_NETWORKS=["10.0.0.0/8"])
    def test_disabled_gate_changes_nothing(self):
        self.assertEqual(self._get(self.admin, reverse("accounts:profile"), self.EXT).status_code, 200)
        self.assertNotEqual(self._get(self.teacher, "/jurnal/", self.EXT).status_code, 403)
