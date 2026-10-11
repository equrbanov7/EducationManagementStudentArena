"""Sahib 2026-10-11: «Dekan rol verə bilir — olmaz; hər rol öz səlahiyyəti qədər; superadmin görünməsin».

* `org_admin` aliası (səviyyə ≥ 80: dekan, prorektor …) rol idarəsi bölmələrini AÇMIR — yalnız REAL
  `role.assign` / `org.manage_members` (rektor `*`, sədr `*`, HR) və ya təşkilat sahibi;
* «Rolları idarə et» / «Rol təyin et» siyahılarında superadmin yoxdur.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
ROLE_SECTIONS = ("manage-roles", "role-assignment", "permission-editor")


class RoleSectionsGateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("rs_owner", "rs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RS Univ", slug="rs-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="rs-f", unit_type=OrgUnitType.FACULTY
            )
            cls.users = {}
            for name, role, unit in (
                ("dean", "dean", faculty),
                ("vice_rector", "vice_rector", None),
                ("rector", "rector", None),
                ("hr", "hr", None),
                ("chair", "board_chair", None),
            ):
                user = User.objects.create_user(f"rs_{name}", f"rs_{name}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
                cls.users[name] = user
            cls.superadmin = User.objects.create_superuser("rs_su", "rs_su@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.superadmin, organization=cls.org, role=cls.org.roles.get(name="rector"), is_active=True
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _sections(self, user):
        response = self._client(user).get(reverse("accounts:profile"))
        return set(response.context["allowed_sections"])

    def test_dean_and_vice_rector_do_not_get_role_management(self):
        for key in ("dean", "vice_rector"):
            with self.subTest(role=key):
                self.assertFalse(set(ROLE_SECTIONS) & self._sections(self.users[key]))

    def test_rector_board_chair_and_hr_keep_role_management(self):
        for key in ("rector", "chair"):
            with self.subTest(role=key):
                self.assertTrue(set(ROLE_SECTIONS) <= self._sections(self.users[key]))
        self.assertIn("manage-roles", self._sections(self.users["hr"]))

    def test_dean_cannot_open_manage_roles_by_url(self):
        response = self._client(self.users["dean"]).get(reverse("accounts:profile"), {"section": "manage-roles"})
        self.assertNotIn("manage-roles", set(response.context["allowed_sections"]))

    def test_superadmin_is_not_listed_in_role_sections(self):
        client = self._client(self.users["rector"])
        for section in ("manage-roles", "role-assignment"):
            with self.subTest(section=section):
                html = client.get(reverse("accounts:profile"), {"section": section}).content.decode()
                self.assertNotIn("rs_su@qku.edu.az", html)
                self.assertIn("rs_vice_rector", html)
