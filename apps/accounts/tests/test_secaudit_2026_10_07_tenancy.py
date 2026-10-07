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
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

import pytest

from apps.accounts.services.rim.lifecycle import block_user, soft_delete_user, unblock_user
from apps.accounts.services.rim.policy import RimAccessError, RimActor, assert_no_foreign_authority
from apps.accounts.services.rim.profile_edit import update_user_fields
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

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
