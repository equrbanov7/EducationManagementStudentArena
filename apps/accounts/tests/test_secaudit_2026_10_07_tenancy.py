"""Təhlükəsizlik auditi 2026-10-07 — hesab/rol axınlarında tenant sərhədi.

SEC-01  «Rolları idarə et» → ``grant_role`` hədəfin aktiv təşkilatda ÜZV olduğunu
        yoxlamırdı: təşkilat-əhatəli aktor (rektor, org admin) istənilən
        platforma istifadəçisinə (başqa tenantın üzvünə, üzvlüyü olmayan
        hesaba) öz təşkilatında üzvlük YARADIRDI («hesabın ilhaqı»). Köhnə
        checkbox axını və «Rol təyin et» axını bunu rədd edir.
SEC-02  ``assert_no_foreign_authority`` başqa təşkilatdakı rütbəni RLS altında
        GÖRMÜRDÜ (``organizations_membership`` tenant siyasəti yalnız aktiv
        org-un sətirlərini qaytarır) — prod rolunda (NOBYPASSRLS) yoxlama boş
        keçirdi; RİM-in qlobal hesab əməlləri (blok, silmə, bərpa, şəxsi
        məlumat/e-poçt redaktəsi) isə onu ümumiyyətlə çağırmırdı. A-nın RİM-i
        A-da tələbə, B-də rektor olan hesabı bloklaya / e-poçtunu dəyişə bilirdi.
SEC-03  «Bildiriş göndər» bölmə (``unit_``) və şöbə (``role_``) hədəfləri aktiv
        təşkilatla məhdudlaşmırdı (2026-09-28 T-01-in qardaşı).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

import pytest

from apps.accounts.models import ProfileRole
from apps.accounts.services.profile_actions import publish_system_notification, resolve_notification_recipients
from apps.accounts.services.rim.lifecycle import block_user, soft_delete_user, unblock_user
from apps.accounts.services.rim.policy import RimAccessError, RimActor, assert_no_foreign_authority
from apps.accounts.services.rim.profile_edit import update_user_fields
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

from .test_view_as import ViewAsTestBase

User = get_user_model()


def _org(name, slug, owner):
    return Organization.objects.create(
        name=name,
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


class _TwoTenantBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner_a = User.objects.create_user("sec07_owner_a", "sec07_owner_a@a.az", "pw")
            cls.owner_b = User.objects.create_user("sec07_owner_b", "sec07_owner_b@b.az", "pw")
            cls.org_a = _org("Sec07 Univ A", "sec07-univ-a", cls.owner_a)
            cls.org_b = _org("Sec07 Univ B", "sec07-univ-b", cls.owner_b)

            cls.rector_a = User.objects.create_user("sec07_rector_a", "sec07_rector_a@a.az", "pw")
            Membership.objects.create(
                user=cls.rector_a,
                organization=cls.org_a,
                role=cls.org_a.roles.get(name="rector"),
                is_primary=True,
                is_active=True,
            )
            # Yalnız B-nin üzvü — A ilə heç bir əlaqəsi yoxdur.
            cls.foreign = User.objects.create_user("sec07_foreign", "sec07_foreign@b.az", "pw")
            Membership.objects.create(
                user=cls.foreign,
                organization=cls.org_b,
                role=cls.org_b.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            # A-da tələbə, B-də rektor.
            cls.dual = User.objects.create_user("sec07_dual", "sec07_dual@a.az", "pw")
            Membership.objects.create(
                user=cls.dual,
                organization=cls.org_a,
                role=cls.org_a.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.dual,
                organization=cls.org_b,
                role=cls.org_b.roles.get(name="rector"),
                is_primary=False,
                is_active=True,
            )

    def _client(self, user, organization):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = organization.slug
        session.save()
        return client

    def _memberships(self, user, organization):
        with bypass_rls():
            return list(Membership.objects.filter(user=user, organization=organization, is_active=True))


class GrantRoleRequiresExistingMemberTest(_TwoTenantBase):
    """SEC-01."""

    def _grant(self, target):
        return self._client(self.rector_a, self.org_a).post(
            reverse("accounts:manage_roles"),
            {
                "action": "grant_role",
                "user_id": str(target.id),
                "role_id": str(self.org_a.roles.get(name="teacher").id),
                "reason": "sec07",
                "next": reverse("accounts:manage_roles"),
            },
        )

    def test_org_wide_actor_cannot_annex_a_member_of_another_tenant(self):
        response = self._grant(self.foreign)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._memberships(self.foreign, self.org_a), [])

    def test_org_wide_actor_cannot_annex_an_account_without_any_membership(self):
        loose = User.objects.create_user("sec07_loose", "sec07_loose@x.az", "pw")

        self._grant(loose)

        self.assertEqual(self._memberships(loose, self.org_a), [])

    def test_existing_member_still_gets_an_additional_role(self):
        self._grant(self.dual)

        roles = {membership.role.name for membership in self._memberships(self.dual, self.org_a)}
        self.assertEqual(roles, {"student", "teacher"})


def _rim_actor(user, organization):
    return RimActor(user=user, organization=organization, level=95, is_superadmin=False, permissions={"*"})


class RimGlobalAccountActionsRespectForeignAuthorityTest(_TwoTenantBase):
    """SEC-02 (tətbiq qatı): qlobal hesab əməlləri hədəfin B-dəki rütbəsini sayır."""

    def _assert_rank_denied(self, call):
        with self.assertRaises(RimAccessError) as ctx:
            call()
        self.assertEqual(ctx.exception.reason_code, "target_rank_too_high")

    def test_block_of_a_foreign_rector_is_denied(self):
        actor = _rim_actor(self.rector_a, self.org_a)
        self._assert_rank_denied(lambda: block_user(actor, self.dual, reason="Səbəb mətni sec07"))
        self.dual.refresh_from_db()
        self.assertTrue(self.dual.is_active)

    def test_soft_delete_of_a_foreign_rector_is_denied(self):
        actor = _rim_actor(self.rector_a, self.org_a)
        self._assert_rank_denied(lambda: soft_delete_user(actor, self.dual, reason="Səbəb mətni sec07"))

    def test_unblock_of_a_foreign_rector_is_denied(self):
        User.objects.filter(pk=self.dual.pk).update(is_active=False)
        self.dual.refresh_from_db()
        actor = _rim_actor(self.rector_a, self.org_a)
        self._assert_rank_denied(lambda: unblock_user(actor, self.dual, reason="Səbəb mətni sec07"))

    def test_email_edit_of_a_foreign_rector_is_denied(self):
        actor = _rim_actor(self.rector_a, self.org_a)
        self._assert_rank_denied(
            lambda: update_user_fields(actor, self.dual, data={"email": "attacker@evil.example"}, reason="sec07")
        )
        self.dual.refresh_from_db()
        self.assertEqual(self.dual.email, "sec07_dual@a.az")


@pytest.mark.postgres
@pytest.mark.django_db
def test_foreign_authority_is_visible_under_tenant_rls(django_user_model):
    """SEC-02 (DB qatı): NOBYPASSRLS rolu + tenant=A altında B-dəki rektorluq görünməlidir."""
    if connection.vendor != "postgresql":
        pytest.skip("RLS PostgreSQL tələb edir")
    with bypass_rls():
        owner_a = django_user_model.objects.create_user("sec07r_owner_a", "o_a@a.az", "pw")
        owner_b = django_user_model.objects.create_user("sec07r_owner_b", "o_b@b.az", "pw")
        org_a = _org("Sec07 RLS A", "sec07-rls-a", owner_a)
        org_b = _org("Sec07 RLS B", "sec07-rls-b", owner_b)
        actor_user = django_user_model.objects.create_user("sec07r_actor", "act@a.az", "pw")
        target = django_user_model.objects.create_user("sec07r_dual", "dual@a.az", "pw")
        Membership.objects.create(
            user=target, organization=org_a, role=org_a.roles.get(name="student"), is_active=True, is_primary=True
        )
        Membership.objects.create(
            user=target, organization=org_b, role=org_b.roles.get(name="rector"), is_active=True, is_primary=False
        )

    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', false)")
        cursor.execute("SELECT set_config('app.current_org_id', %s, false)", [str(org_a.pk)])
        cursor.execute("SET LOCAL ROLE rls_app_role")
    try:
        with pytest.raises(RimAccessError) as excinfo:
            assert_no_foreign_authority(_rim_actor(actor_user, org_a), target)
        assert excinfo.value.reason_code == "target_rank_too_high"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config('app.current_org_id', '', false)")


# ── SEC-03 ──────────────────────────────────────────────────────────────────


class NotificationStructureTargetsStayInActiveOrgTest(ViewAsTestBase):
    """SEC-03: ``unit_<uuid>`` / ``role_<key>_<org>`` hədəfləri aktiv təşkilatdan kənara çıxmır.

    T-01 (2026-09-28) yalnız ``org_<id>`` hədəfini bağlamışdı. Bölmə/şöbə hədəfləri
    hədəfin ÖZ təşkilatını tapıb ``capabilities`` (AKTİV org-un admin bayrağı) ilə
    yoxlayırdı — A-nın admini B-də istənilən üzvlüyü olanda B-nin bölməsinə / bütün
    tələbələrinə bildiriş göndərirdi (yalnız DB-nin RLS qatı dayandırırdı).
    """

    CAPS_ADMIN = {"is_superadmin": False, "is_org_admin": True, "is_teacher": False}

    def setUp(self):
        super().setUp()
        self.other_unit = OrgUnit.objects.create(
            organization=self.other_org,
            unit_type=OrgUnitType.FACULTY,
            name="Other Faculty",
            slug="sec07-other-faculty",
            is_active=True,
        )
        Membership.objects.filter(user=self.other_student, organization=self.other_org).update(
            scope_unit=self.other_unit
        )
        # A-nın admini B-də adi tələbədir.
        Membership.objects.create(
            user=self.admin,
            organization=self.other_org,
            role=self.other_org.roles.filter(name=ProfileRole.STUDENT).first(),
            is_active=True,
            is_primary=False,
        )

    def _publish(self, targets):
        request = RequestFactory().post(
            "/accounts/profile/",
            {
                "profile_form": "publish-notification",
                "notif_title": "SEC03 yoxlama",
                "notif_message": "salam",
                "notif_targets": targets,
            },
        )
        request.user = self.admin
        request.organization = self.org
        return publish_system_notification(request=request, capabilities=self.CAPS_ADMIN)

    def test_unit_target_of_another_org_is_refused(self):
        target = f"unit_{self.other_unit.pk}"
        self.assertIsNone(resolve_notification_recipients(self.admin, self.CAPS_ADMIN, target, organization=self.org))
        ok, _key = self._publish([target])
        self.assertFalse(ok)
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_student).exists())

    def test_role_target_of_another_org_is_refused(self):
        target = f"role_students_{self.other_org.pk}"
        self.assertIsNone(resolve_notification_recipients(self.admin, self.CAPS_ADMIN, target, organization=self.org))
        ok, _key = self._publish([target])
        self.assertFalse(ok)
        self.assertFalse(InAppNotification.objects.filter(recipient=self.other_student).exists())

    def test_targets_of_the_active_org_still_work(self):
        ok, _key = self._publish([f"unit_{self.unit.pk}", f"role_students_{self.org.pk}"])
        self.assertTrue(ok)
        self.assertTrue(InAppNotification.objects.filter(recipient=self.student, title="SEC03 yoxlama").exists())
