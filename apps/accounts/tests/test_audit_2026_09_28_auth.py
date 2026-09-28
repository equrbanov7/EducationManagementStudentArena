"""Audit 2026-09-28 — autentifikasiya/avtorizasiya reqressiya testləri.

SA-03  hesab səviyyəli (yalnız istifadəçi adı) login vedrəsi: 80 fərqli İP-dən
       səhv parol → hesab 429; uğurlu login başqa hesabın vedrəsinə toxunmur;
       çox İP-dən uğursuzluq WARNING yazır.
SA-04  profil rolu ``superadmin`` (``is_superuser=False``) — 2FA tələb olunur,
       view-as hədəfi ola bilməz (tam yoxlama + sürətli yol), şəbəkə zonasında staff.
T-01   ``org_<id>`` bildiriş hədəfi: adi müəllim (N01) və başqa org-da üzvlüyü
       olan admin (N02) göndərə bilmir; UI yalnız aktiv org-u göstərir.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.network_zone import account_kind
from apps.accounts.services.profile_actions import publish_system_notification, resolve_notification_recipients
from apps.accounts.services.view_as import (
    VIEW_AS_SESSION_KEY,
    build_target_queryset,
    resolve_actor_access,
    validate_target,
)
from apps.accounts.views.profile.context_builder._helpers import _get_publish_notification_targets
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization
from core import rate_limit as rate_limit_module
from core.admin_auth import admin_2fa_required_for_user
from core.permissions import is_superadmin_user
from core.rls import bypass_rls

from .test_view_as import PASSWORD, ViewAsTestBase, _add_member

User = get_user_model()
PW = "AuditPass123!"
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "audit2809"}}


def _reset_rate_limits():
    from django.core.cache import cache

    cache.clear()
    rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()


# ── SA-03 ───────────────────────────────────────────────────────────────────


@override_settings(
    CACHES=LOCMEM_CACHE,
    LOGIN_RATE_LIMIT="5/10m",
    LOGIN_IP_RATE_LIMIT="60/10m",
    LOGIN_ACCOUNT_RATE_LIMIT="20/1h",
    LOGIN_ACCOUNT_DISTINCT_IP_ALERT=10,
)
class AccountLoginBucketTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner = User.objects.create_user("sa3_owner", "sa3_owner@audit.az", PW)
            cls.org = Organization.objects.create(
                name="SA3 Univ",
                slug="sa3-univ",
                org_type="university",
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.victim = User.objects.create_user("sa3_victim", "sa3_victim@audit.az", PW)
            cls.other = User.objects.create_user("sa3_other", "sa3_other@audit.az", PW)
            for user in (cls.victim, cls.other):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )

    def setUp(self):
        _reset_rate_limits()

    def _login(self, username, password, ip):
        return Client().post(
            reverse("accounts:staff_login"), {"username": username, "password": password}, REMOTE_ADDR=ip
        )

    def test_distributed_failures_from_80_ips_lock_the_account(self):
        with self.assertLogs("apps.accounts.views.auth._shared", level="WARNING") as logs:
            statuses = [
                self._login("sa3_victim", f"wrong{i}", f"10.9.{i // 250}.{i % 250 + 1}").status_code for i in range(80)
            ]

        # Auditor zondu P4: əvvəl 80 cəhdin hamısı 200 idi, sonra düzgün parol 302.
        self.assertEqual(statuses[:20], [200] * 20)
        self.assertEqual(set(statuses[20:]), {429})
        correct = self._login("sa3_victim", PW, "10.8.0.1")
        self.assertEqual(correct.status_code, 429)
        self.assertContains(correct, "Çox sayda cəhd edildi", status_code=429)
        self.assertTrue(any("distinct IPs" in line for line in logs.output), logs.output)

    def test_other_account_is_not_affected_and_success_resets_only_own_bucket(self):
        for i in range(20):
            self._login("sa3_victim", f"wrong{i}", f"10.7.0.{i + 1}")
        self.assertEqual(self._login("sa3_victim", PW, "10.7.1.1").status_code, 429)

        other = self._login("sa3_other", PW, "10.7.1.2")
        self.assertEqual(other.status_code, 302)
        # Başqa hesabın uğurlu girişi qurbanın vedrəsini sıfırlamır.
        self.assertEqual(self._login("sa3_victim", PW, "10.7.1.3").status_code, 429)

    def test_success_below_threshold_clears_the_account_bucket(self):
        for i in range(19):
            self._login("sa3_victim", f"wrong{i}", f"10.6.0.{i + 1}")
        self.assertEqual(self._login("sa3_victim", PW, "10.6.1.1").status_code, 302)
        self.assertEqual(self._login("sa3_victim", "wrong-again", "10.6.1.2").status_code, 200)


# ── SA-04 ───────────────────────────────────────────────────────────────────


class ProfileRoleSuperadminTest(ViewAsTestBase):
    def setUp(self):
        super().setUp()
        self.psa = User.objects.create_user("psa_user", "psa@example.com", PASSWORD)
        UserProfile.objects.filter(user=self.psa).update(role=ProfileRole.SUPERADMIN)
        _add_member(self.psa, self.org, self.teacher_role)
        self.psa = User.objects.get(pk=self.psa.pk)

    def test_single_predicate_covers_profile_role(self):
        self.assertFalse(self.psa.is_superuser)
        self.assertFalse(self.psa.is_staff)
        self.assertTrue(is_superadmin_user(self.psa))
        self.assertFalse(is_superadmin_user(self.teacher))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_2fa_required_for_profile_role_superadmin(self):
        self.assertTrue(admin_2fa_required_for_user(self.psa))
        self.assertFalse(admin_2fa_required_for_user(self.teacher))

        client = Client()
        client.force_login(self.psa)
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("admin:verify-otp"))

    def test_view_as_cannot_target_profile_role_superadmin(self):
        mode, level, memberships = resolve_actor_access(self.admin, self.org)
        targets = build_target_queryset(self.admin, self.org, mode=mode, actor_level=level, memberships=memberships)
        self.assertNotIn(self.psa.pk, set(targets.values_list("pk", flat=True)))
        self.assertEqual(validate_target(self.admin, self.org, self.psa.pk), (None, None))

        self._login(self.admin)
        self._start(self.psa)
        self.assertFalse(self.client.session.get(VIEW_AS_SESSION_KEY))

    def test_view_as_fast_path_stops_when_target_becomes_superadmin(self):
        self._login(self.admin)
        self._start(self.teacher)
        self.assertTrue(self.client.session.get(VIEW_AS_SESSION_KEY))

        # Sürətli yol (checked_at təzədir) — hədəf sonradan profil-superadmin olur.
        UserProfile.objects.filter(user=self.teacher).update(role=ProfileRole.SUPERADMIN)
        self.client.get(reverse("accounts:profile"))

        self.assertFalse(self.client.session.get(VIEW_AS_SESSION_KEY))

    def test_network_zone_classifies_profile_role_superadmin_as_staff(self):
        request = RequestFactory().get("/")
        request.user = self.psa
        request.organization = self.org
        request.org_memberships = list(self.psa.memberships.filter(is_active=True).select_related("role"))
        self.assertEqual(account_kind(request), "staff")


# ── T-01 ────────────────────────────────────────────────────────────────────


class NotificationOrgTargetTest(ViewAsTestBase):
    CAPS_TEACHER = {"is_superadmin": False, "is_org_admin": False, "is_teacher": True}
    CAPS_ADMIN = {"is_superadmin": False, "is_org_admin": True, "is_teacher": False}

    def _publish(self, user, capabilities, targets, organization):
        request = RequestFactory().post(
            "/accounts/profile/",
            {
                "profile_form": "publish-notification",
                "notif_title": "T01 yoxlama",
                "notif_message": "salam",
                "notif_targets": targets,
            },
        )
        request.user = user
        request.organization = organization
        return publish_system_notification(request=request, capabilities=capabilities)

    def test_N01_plain_teacher_cannot_broadcast_to_active_org(self):
        ok, _key = self._publish(self.teacher, self.CAPS_TEACHER, [f"org_{self.org.pk}"], self.org)

        self.assertFalse(ok)
        self.assertFalse(InAppNotification.objects.filter(title="T01 yoxlama").exists())
        self.assertIsNone(
            resolve_notification_recipients(
                self.teacher, self.CAPS_TEACHER, f"org_{self.org.pk}", organization=self.org
            )
        )

    def test_N02_org_admin_cannot_target_another_org_via_foreign_membership(self):
        # Admin A-nın admini, B-də isə yalnız tələbə üzvlüyü var.
        other_student_role = self.other_org.roles.filter(name=ProfileRole.STUDENT).first()
        Membership.objects.create(
            user=self.admin, organization=self.other_org, role=other_student_role, is_active=True, is_primary=False
        )

        ok, _key = self._publish(self.admin, self.CAPS_ADMIN, [f"org_{self.other_org.pk}"], self.org)

        self.assertFalse(ok)
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_student).exists())

    def test_org_admin_can_broadcast_to_active_org(self):
        mail.outbox.clear()
        ok, _key = self._publish(self.admin, self.CAPS_ADMIN, [f"org_{self.org.pk}"], self.org)

        self.assertTrue(ok)
        self.assertTrue(InAppNotification.objects.filter(recipient=self.teacher, title="T01 yoxlama").exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_student).exists())

    def test_target_list_offers_only_the_active_org(self):
        Membership.objects.create(
            user=self.admin,
            organization=self.other_org,
            role=self.other_org.roles.filter(name=ProfileRole.STUDENT).first(),
            is_active=True,
            is_primary=False,
        )
        values = {t["value"] for t in _get_publish_notification_targets(self.admin, self.CAPS_ADMIN, self.org)}
        self.assertIn(f"org_{self.org.pk}", values)
        self.assertNotIn(f"org_{self.other_org.pk}", values)

        teacher_values = {
            t["value"] for t in _get_publish_notification_targets(self.teacher, self.CAPS_TEACHER, self.org)
        }
        self.assertFalse(any(value.startswith("org_") for value in teacher_values))
