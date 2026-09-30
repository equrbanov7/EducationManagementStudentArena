"""«Parol sıfırlama» (`account.password_reset`, sahib 2026-09-30) — icazə və qadağa qaydaları.

Siyasət sənədidir: hər qadağa ayrıca testdir (tenant, superuser, profil-superadmin,
iyerarxiya, özü, sahibi, silinmiş/bloklanmış/arxiv, rate-limit, yalnız POST + CSRF,
view-as). Uçdan-uca axın `test_account_password_reset_flow.py`-dadır.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core import rate_limit as rate_limit_module
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls
from core.roles import ProfileRole

User = get_user_model()
PASSWORD = "PwdResetPass123!"
PERM = "account.password_reset"
_MIGRATION = import_module("apps.organizations.migrations.0055_account_password_reset_permission")


def make_role(organization, name, level, permissions=None):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": list(permissions or []),
            "is_system": False,
            "is_active": True,
        },
    )
    return role


def make_user(username, organization=None, role=None, *, first="", last=""):
    user = User.objects.create_user(username, f"{username}@pwd.example.com", PASSWORD)
    user.first_name, user.last_name = first, last
    user.save(update_fields=["first_name", "last_name"])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.organization = organization
    profile.save()
    if organization is not None and role is not None:
        Membership.objects.create(user=user, organization=organization, role=role, is_active=True, is_primary=True)
    return user


def make_org(tag):
    owner = User.objects.create_user(f"pwd_owner_{tag}", f"pwd_owner_{tag}@pwd.example.com", PASSWORD)
    org = Organization.objects.create(
        name=f"PWD Univ {tag}",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    return org, owner


@override_settings(RATELIMIT_ENABLE=False)
class PasswordResetTestBase(TestCase):
    """Org A: RİM rəhbəri (95, yalnız `account.password_reset`), müxtəlif səviyyəli hədəflər; Org B: yad tenant."""

    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.org, self.owner = make_org("a")
        self.rim_role = make_role(self.org, "ikt_rehber", 95, [PERM])
        self.teacher_role = make_role(self.org, ProfileRole.TEACHER, 50)
        self.student_role = make_role(self.org, ProfileRole.STUDENT, 10)
        self.rector_role = make_role(self.org, "rector", 100, ["*"])

        self.operator = make_user("rim.rehber", self.org, self.rim_role, first="Rəşad", last="Məmmədov")
        self.student = make_user("aysel.quliyeva", self.org, self.student_role, first="Aysel", last="Quliyeva")
        self.teacher = make_user("elvin.aliyev", self.org, self.teacher_role, first="Elvin", last="Əliyev")
        self.peer = make_user("rim.peer", self.org, self.rim_role, first="Peer", last="Rehber")
        self.rector = make_user("rektor.user", self.org, self.rector_role, first="Rektor", last="User")

        self.org_b, _ = make_org("b")
        self.foreign = make_user("yad.telebe", self.org_b, make_role(self.org_b, ProfileRole.STUDENT, 10))

        self.superuser = User.objects.create_superuser("root_pwd", "root_pwd@pwd.example.com", PASSWORD)

    def login(self, user, organization=None, client=None):
        client = client or self.client
        client.force_login(user)
        session = client.session
        session["active_organization"] = (organization or self.org).slug
        session.save()
        return client

    def lookup(self, query, client=None):
        return (client or self.client).post(
            reverse("accounts:account_password_reset_lookup"), {"q": query}, content_type="application/json"
        )

    def reset(self, target, client=None, **extra):
        return (client or self.client).post(
            reverse("accounts:account_password_reset_perform"),
            {"user_id": getattr(target, "pk", target)},
            content_type="application/json",
            **extra,
        )

    def assert_unchanged(self, user):
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD), user.username)


class CatalogTest(SimpleTestCase):
    def test_key_in_catalog_with_label_and_users_category(self):
        from apps.organizations.permissions import (
            PERMISSION_CATEGORIES,
            get_all_permissions,
            get_permission_label,
            validate_permissions,
        )

        self.assertIn(PERM, get_all_permissions())
        self.assertIn(PERM, PERMISSION_CATEGORIES["users"])
        self.assertTrue(get_permission_label(PERM).strip())
        self.assertTrue(validate_permissions([PERM, f"grant:{PERM}"]))


class MigrationTest(TestCase):
    def test_forward_adds_key_to_narrowed_rim_head_only_and_is_idempotent(self):
        org, _ = make_org("mig")
        with bypass_rls():
            narrowed = make_role(org, "ikt_rehber", 95, ["user.search"])
            wildcard_org, _ = make_org("mig2")
            wildcard = make_role(wildcard_org, "ikt_rehber", 95, ["*"])
            dean = make_role(org, "dean", 85, ["org.view"])
            _MIGRATION.forward(django_apps, None)
            _MIGRATION.forward(django_apps, None)
            narrowed.refresh_from_db()
            wildcard.refresh_from_db()
            dean.refresh_from_db()
            self.assertEqual(narrowed.permissions, ["user.search", PERM])
            self.assertEqual(wildcard.permissions, ["*"])
            self.assertEqual(dean.permissions, ["org.view"])

            _MIGRATION.backward(django_apps, None)
            narrowed.refresh_from_db()
            wildcard.refresh_from_db()
            self.assertEqual(narrowed.permissions, ["user.search"])
            self.assertEqual(wildcard.permissions, ["*"])


class AccessGateTest(PasswordResetTestBase):
    def test_user_without_permission_gets_403_on_both_endpoints(self):
        self.login(self.teacher)
        for response in (self.lookup("aysel.quliyeva"), self.reset(self.student)):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"], "permission_denied")
        self.assert_unchanged(self.student)

    def test_get_is_not_allowed(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("accounts:account_password_reset_perform")).status_code, 405)
        self.assertEqual(self.client.get(reverse("accounts:account_password_reset_lookup")).status_code, 405)

    def test_csrf_is_enforced(self):
        client = self.login(self.operator, client=Client(enforce_csrf_checks=True))
        response = self.reset(self.student, client=client)
        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.student)

    def test_anonymous_is_redirected_to_login(self):
        response = self.reset(self.student)
        self.assertEqual(response.status_code, 302)
        self.assert_unchanged(self.student)

    def test_permission_granted_to_another_role_works(self):
        """Açar redaktordan istənilən rola verilə bilir — kod rol adına baxmır."""
        office_role = make_role(self.org, "dean_office_staff", 60, [PERM])
        clerk = make_user("dekanliq.isci", self.org, office_role)
        self.login(clerk)
        self.assertEqual(self.reset(self.student).status_code, 200)
        # …amma öz səviyyəsindən yuxarı (rektor) və ya bərabər olanı YOX.
        self.assertEqual(self.reset(self.rector).status_code, 403)


class ForbiddenTargetTest(PasswordResetTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.operator)

    def assert_denied(self, target, code, status=403):
        response = self.reset(target)
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["error"], code)
        self.assertNotIn("password", response.json())
        self.assert_unchanged(target)

    def test_cross_tenant_target_is_not_found(self):
        self.assert_denied(self.foreign, "target_not_found", status=404)

    def test_superuser_target_is_refused(self):
        Membership.objects.create(user=self.superuser, organization=self.org, role=self.student_role, is_active=True)
        self.assert_denied(self.superuser, "target_is_superadmin")

    def test_profile_role_superadmin_target_is_refused(self):
        profile = self.student.profile
        profile.role = ProfileRole.SUPERADMIN
        profile.save(update_fields=["role"])
        self.assert_denied(self.student, "target_is_superadmin")

    def test_higher_level_target_is_refused(self):
        self.assert_denied(self.rector, "target_rank_too_high")

    def test_equal_level_target_is_refused(self):
        self.assert_denied(self.peer, "target_rank_too_high")

    def test_self_is_refused(self):
        self.assert_denied(self.operator, "target_is_self")

    def test_org_owner_is_refused(self):
        Membership.objects.create(user=self.owner, organization=self.org, role=self.student_role, is_active=True)
        self.assert_denied(self.owner, "target_is_owner")

    def test_blocked_account_is_refused(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        self.assert_denied(self.student, "target_blocked", status=409)

    def test_deleted_account_is_refused(self):
        profile = self.student.profile
        profile.is_deleted = True
        profile.save(update_fields=["is_deleted"])
        self.assert_denied(self.student, "target_deleted", status=409)

    def test_archived_account_is_refused(self):
        profile = self.student.profile
        profile.access_state = UserProfile.AccessState.ARCHIVED
        profile.save(update_fields=["access_state"])
        self.assert_denied(self.student, "target_login_closed", status=409)

    def test_unknown_or_missing_target(self):
        response = self.reset(987654321)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("accounts:account_password_reset_perform"), {}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_denied_attempt_is_audited_without_password(self):
        self.reset(self.rector)
        row = AuditLog.objects.filter(action="deny", user=self.operator).latest("created_at")
        self.assertEqual(row.changes["code"], "target_rank_too_high")
        self.assertEqual(row.changes["target_user_id"], str(self.rector.pk))


class SuperuserOperatorTest(PasswordResetTestBase):
    def test_superuser_resets_within_active_org_only(self):
        self.login(self.superuser)
        self.assertEqual(self.reset(self.rector).status_code, 200)
        response = self.reset(self.foreign)
        self.assertEqual(response.status_code, 404)
        self.assert_unchanged(self.foreign)

    def test_superuser_cannot_reset_another_superuser(self):
        other_root = User.objects.create_superuser("root_two", "root_two@pwd.example.com", PASSWORD)
        Membership.objects.create(user=other_root, organization=self.org, role=self.student_role, is_active=True)
        self.login(self.superuser)
        response = self.reset(other_root)
        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(other_root)


class RateLimitTest(PasswordResetTestBase):
    @override_settings(RATELIMIT_ENABLE=True, ACCOUNT_PASSWORD_RESET_RATE_LIMIT="2/1h")
    def test_reset_endpoint_is_rate_limited_per_operator(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.login(self.operator)
        self.assertEqual(self.reset(self.student).status_code, 200)
        self.assertEqual(self.reset(self.teacher).status_code, 200)
        response = self.reset(self.student)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"], "rate_limited")
        # Başqa operatorun vedrəsi ayrıdır.
        other = make_user("rim.second", self.org, make_role(self.org, "rim_second", 90, [PERM]))
        self.login(other)
        self.assertEqual(self.reset(self.student).status_code, 200)

    @override_settings(RATELIMIT_ENABLE=True, ACCOUNT_PASSWORD_RESET_RATE_LIMIT="2/1h")
    def test_unauthorized_spam_is_limited_and_audit_stays_bounded(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.login(self.teacher)
        self.assertEqual(self.reset(self.student).status_code, 403)
        self.assertEqual(self.reset(self.student).status_code, 403)
        for _ in range(3):
            self.assertEqual(self.reset(self.student).status_code, 429)
        self.assertEqual(AuditLog.objects.filter(action="deny", user=self.teacher).count(), 2)

    @override_settings(RATELIMIT_ENABLE=True, ACCOUNT_PASSWORD_RESET_LOOKUP_RATE_LIMIT="1/10m")
    def test_lookup_endpoint_is_rate_limited(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.login(self.operator)
        self.assertEqual(self.lookup("aysel").status_code, 200)
        self.assertEqual(self.lookup("aysel").status_code, 429)


class ViewAsTest(PasswordResetTestBase):
    """View-as sessiyası HEÇ BİR rejimdə (FULL daxil) parol sıfırlaya bilməz."""

    def test_full_mode_view_as_cannot_reset_or_lookup(self):
        admin_role = make_role(self.org, ProfileRole.ORG_ADMIN, 80, [PERM])
        admin = make_user("org.admin", self.org, admin_role)
        # Hədəfin özündə də açar var — yəni qadağa hədəfin icazəsindən ASILI DEYİL.
        self.teacher_role.permissions = [PERM]
        self.teacher_role.save(update_fields=["permissions"])
        self.login(admin)
        start = self.client.post(reverse("accounts:view_as_start"), {"user_id": self.teacher.pk})
        self.assertEqual(start.status_code, 302)

        response = self.reset(self.student)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "view_as_forbidden")
        self.assertEqual(self.lookup("aysel.quliyeva").status_code, 403)
        self.assert_unchanged(self.student)

    def test_service_rejects_view_as_request_flag(self):
        from django.test import RequestFactory

        from apps.accounts.services.password_reset_admin import PasswordResetError, operator_for

        request = RequestFactory().post("/")
        request.user = self.operator
        request.is_view_as = True
        with self.assertRaises(PasswordResetError) as caught:
            operator_for(request)
        self.assertEqual(caught.exception.code, "view_as_forbidden")
