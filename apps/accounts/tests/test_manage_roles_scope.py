"""Legacy «manage-roles» səthi — QA 2026-09-05 PEOPLE-RBAC-08/09 reqressiya qapısı.

1. Vahid-əhatəli aktor (dekan) başqa fakültənin müəlliminə rol verə bilməz; heç bir aktor
   (superadmin/owner xaric) `role.assign`/`org.manage_members` olmadan bu səthə yazmır.
2. Rol adı təşkilat roluna DƏQİQ adla həll olunur: «exam_center_staff» seçəndə əvvəl
   ən aşağı rol (alumni) yaranırdı.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.policies.roles import resolve_membership_role
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ManageRolesScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mr_owner", "mr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MR Univ",
                slug="mr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty_a = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="mr-fak-a", unit_type=OrgUnitType.FACULTY
            )
            cls.faculty_b = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="mr-fak-b", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_b = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra B1",
                slug="mr-kaf-b1",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty_b,
            )
            cls.dean_a = User.objects.create_user("mr_dean_a", "mr_dean_a@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean_a,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                scope_unit=cls.faculty_a,
                is_primary=True,
                is_active=True,
            )
            cls.teacher_b = User.objects.create_user("mr_teacher_b", "mr_teacher_b@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher_b,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                scope_unit=cls.chair_b,
                is_primary=True,
                is_active=True,
            )
            cls.superuser = User.objects.create_superuser("mr_super", "mr_super@qku.edu.az", "pw")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _roles_of(self, user):
        with bypass_rls():
            return set(
                Membership.objects.filter(user=user, organization=self.org, is_active=True).values_list(
                    "role__name", flat=True
                )
            )

    def test_dean_cannot_grant_roles_to_teacher_of_another_faculty(self):
        client = self._client(self.dean_a)
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "assign", "role_names": ["teacher", "hr"]},
            follow=True,
        )
        self.assertEqual(self._roles_of(self.teacher_b), {"teacher"})

    def test_exact_role_name_resolves_to_the_matching_org_role(self):
        with bypass_rls():
            role = resolve_membership_role(self.org, "exam_center_staff")
            self.assertIsNotNone(role)
            self.assertEqual(role.name, "exam_center_staff")
            self.assertIsNone(resolve_membership_role(self.org, "no_such_role_xyz"))

    def test_superadmin_assigning_exam_center_staff_creates_that_role_not_alumni(self):
        client = self._client(self.superuser)
        client.post(
            reverse("accounts:manage_roles"),
            {"user_id": self.teacher_b.id, "action": "assign", "role_names": ["teacher", "exam_center_staff"]},
            follow=True,
        )
        roles = self._roles_of(self.teacher_b)
        self.assertIn("exam_center_staff", roles)
        self.assertNotIn("alumni", roles)
