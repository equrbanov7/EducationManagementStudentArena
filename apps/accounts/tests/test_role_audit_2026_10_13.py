"""Rol auditi 2026-10-13 — «hər rol öz norması qədər» (sahib 2026-10-11 qaydasının davamı).

* «Apellyasiyalarım» (`my-appeals`) heyət roluna fraqment URL-i ilə açılmır — menyu ilə eyni şərt
  (`can_view_student_assignments`); əvvəl inkar-qayda HR/tyutora bölməni verirdi.
* Qəyyumlar Şurasının sədri (`board_chair`) TƏK üzvlüklə də view-as FULL alır — əvvəl
  `ROLE_MODE_MAP`-da yox idi (yalnız əlavə rektor üzvlüyü ilə işləyirdi).
* Struktur reyestrində rəhbər/rol təyinatı yalnız REAL `member.edit` / `unit.assign_head` ilə:
  `org_admin` ALİASI (kafedra müdiri → `department_head`) kafedra müdirinə öz kafedrasına
  müdir təyin etməyə imkan verirdi.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.services.view_as import MODE_FULL, resolve_actor_access
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, RoleScopeType

from .test_org_units_sections import _OrgUnitsBase

User = get_user_model()
PASSWORD = "StrongPass123!"


class _TinyOrg(TestCase):
    ROLES: dict = {}

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ra_owner", "ra_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Rol auditi Univ",
            slug="rol-audit-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.users = {}
        for name, (level, permissions) in cls.ROLES.items():
            # Universitet yaradılanda default rollar əkilir — sətir yenilənir, təkrar yaradılmır.
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": permissions,
                    "is_active": True,
                },
            )
            user = User.objects.create_user(f"ra_{name}", f"ra_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.users[name] = user


class MyAppealsGateTest(_TinyOrg):
    ROLES = {
        "student": (10, []),
        "hr": (65, ["member.view"]),
        "tutor": (40, ["member.view"]),
        "student_services": (60, ["member.view"]),
    }

    def _sections(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    def test_student_keeps_my_appeals(self):
        self.assertIn("my-appeals", self._sections("student"))

    def test_staff_roles_do_not_get_my_appeals(self):
        for role in ("hr", "tutor", "student_services"):
            with self.subTest(role=role):
                self.assertNotIn("my-appeals", self._sections(role))


class BoardChairViewAsTest(_TinyOrg):
    ROLES = {"board_chair": (110, ["*"])}

    def test_board_chair_alone_gets_full_view_as(self):
        mode, level, _memberships = resolve_actor_access(self.users["board_chair"], self.org)
        self.assertEqual(mode, MODE_FULL)
        self.assertEqual(level, 110)


class HeadAssignmentNeedsRealKeyTest(_OrgUnitsBase):
    def test_chair_head_without_member_edit_cannot_assign_head(self):
        target = self.users["teacher"]
        response = self._action(
            "chair_head", {"action": "assign_head", "id": str(self.chair.id), "head": str(target.id)}
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org, user=target, role=self.roles["chair_head"], is_active=True
            ).exists()
        )

    def test_member_edit_key_still_assigns_head(self):
        """Açar verilərsə (icazə redaktoru) təyinat işləyir — qapı rol adına yox, açara baxır.

        2026-10-13 (rol auditi B9): rəhbər təyinatının açarı artıq `member.edit` deyil, `role.assign`
        (və ya `unit.assign_head`) — `member.edit` tək açmır (bax `test_role_audit_b_struct_2026_10_13`).
        """
        role = self.roles["chair_head"]
        role.permissions = list(role.permissions) + ["role.assign"]
        role.save(update_fields=["permissions"])
        specialty = OrgUnit.objects.get(pk=self.specialty.pk)
        response = self._action(
            "chair_head", {"action": "assign_head", "id": str(specialty.id), "head": str(self.users["teacher"].id)}
        )
        self.assertNotEqual(response.status_code, 403, response.content)


class DeanNotificationReachTest(_OrgUnitsBase):
    """Dekan real istifadədə `is_org_admin=True` alır (alias) — buna baxmayaraq yalnız öz fakültəsi."""

    DEAN_CAPS = {"is_superadmin": False, "is_org_admin": True, "is_teacher": False}

    def test_dean_alias_does_not_unlock_whole_org_or_role_targets(self):
        from apps.accounts.services.notification_scopes import can_target_whole_organization
        from apps.accounts.services.profile_actions import resolve_notification_recipients
        from apps.accounts.views.profile.context_builder._helpers import _get_publish_notification_targets

        dean = self.users["dean"]
        values = {t["value"] for t in _get_publish_notification_targets(dean, self.DEAN_CAPS, organization=self.org)}
        self.assertNotIn(f"org_{self.org.pk}", values)
        self.assertFalse(any(v.startswith("role_") for v in values), values)
        self.assertIn(f"unit_{self.faculty.pk}", values)
        self.assertNotIn(f"unit_{self.other_faculty.pk}", values)
        self.assertFalse(can_target_whole_organization(dean, self.DEAN_CAPS, self.org))
        self.assertIsNone(
            resolve_notification_recipients(dean, self.DEAN_CAPS, f"org_{self.org.pk}", organization=self.org)
        )

    def test_org_wide_admin_keeps_whole_org_target(self):
        from apps.accounts.services.notification_scopes import can_target_whole_organization

        self.assertTrue(can_target_whole_organization(self.owner, self.DEAN_CAPS, self.org))


class HrRoleMenusFollowKeyTest(_TinyOrg):
    ROLES = {"hr": (65, ["member.view", "member.edit", "role.view", "role.assign"])}

    def _sections(self):
        client = Client()
        client.force_login(self.users["hr"])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return set(client.get(reverse("accounts:profile")).context["allowed_sections"])

    def test_hr_with_role_assign_sees_role_menus(self):
        sections = self._sections()
        self.assertIn("role-assignment", sections)
        self.assertIn("manage-roles", sections)
        self.assertNotIn("permission-editor", sections)

    def test_hr_without_role_assign_loses_role_menus(self):
        Role.objects.filter(organization=self.org, name="hr").update(permissions=["member.view", "member.edit"])
        sections = self._sections()
        self.assertNotIn("role-assignment", sections)
        self.assertNotIn("manage-roles", sections)
        self.assertIn("publish-notification", sections)
