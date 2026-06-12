"""
Fakültə / Kafedra ayrı idarəetmə səhifələrinin testləri (structure_views).

Yoxlanılır:
- icazə: owner/superadmin idarə edir, adi üzv görmür, başqa org-un istifadəçisi girə bilmir
- CRUD: yaratma, redaktə, silmə (qoruma qaydaları ilə birlikdə)
- müəllim təyinatı: assign_teacher / remove_teacher (Membership.scope_unit)
- rəhbər təyinatı: assign_head
- axtarış / fakültə filtri
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.constants import OrganizationType, OrgUnitType

from ..models import Membership, Organization, OrgUnit

User = get_user_model()


class StructureViewsTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="structure_owner",
            email="structure_owner@example.com",
            password="testpass123",
        )
        self.teacher_user = User.objects.create_user(
            username="structure_teacher",
            email="structure_teacher@example.com",
            password="testpass123",
        )
        self.student_user = User.objects.create_user(
            username="structure_student",
            email="structure_student@example.com",
            password="testpass123",
        )
        self.outsider = User.objects.create_user(
            username="structure_outsider",
            email="structure_outsider@example.com",
            password="testpass123",
        )
        self.organization = Organization.objects.create(
            name="Structure Test University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.other_org = Organization.objects.create(
            name="Other University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.outsider,
            status="active",
            is_active=True,
        )
        self.teacher_membership = Membership.objects.create(
            user=self.teacher_user,
            organization=self.organization,
            role=self.organization.roles.get(name="teacher"),
            is_primary=True,
            is_active=True,
        )
        self.student_membership = Membership.objects.create(
            user=self.student_user,
            organization=self.organization,
            role=self.organization.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        self.faculty = OrgUnit.objects.create(
            organization=self.organization,
            unit_type=OrgUnitType.FACULTY,
            name="Test Fakültəsi",
            slug="test-fakultesi",
            code="TF",
        )
        self.kafedra = OrgUnit.objects.create(
            organization=self.organization,
            parent=self.faculty,
            unit_type=OrgUnitType.CHAIR,
            name="Test Kafedrası",
            slug="test-kafedrasi",
            code="TK",
        )
        self.faculties_url = reverse("organizations:structure_faculties", kwargs={"slug": self.organization.slug})
        self.kafedras_url = reverse("organizations:structure_kafedras", kwargs={"slug": self.organization.slug})


class StructureAccessTests(StructureViewsTestBase):
    def test_owner_can_open_both_pages(self):
        self.client.force_login(self.owner)
        for url in (self.faculties_url, self.kafedras_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, msg=url)

    def test_student_cannot_open_structure_pages(self):
        self.client.force_login(self.student_user)
        for url in (self.faculties_url, self.kafedras_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, msg=url)

    def test_outsider_cannot_open_other_org_structure(self):
        self.client.force_login(self.outsider)
        for url in (self.faculties_url, self.kafedras_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, msg=url)

    def test_search_and_faculty_filter(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.faculties_url, {"faculty_search": "Tapilmayan"})
        self.assertContains(response, "Nəticə tapılmadı")

        response = self.client.get(
            self.kafedras_url,
            {"kafedra_search": "Test", "kafedra_faculty": str(self.faculty.id)},
        )
        self.assertContains(response, "Test Kafedrası")


class FacultyCrudTests(StructureViewsTestBase):
    def test_owner_creates_faculty(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.faculties_url,
            {"action": "create", "name": "Yeni Fakültə", "code": "YF"},
        )
        self.assertRedirects(response, self.faculties_url)
        self.assertTrue(
            OrgUnit.objects.filter(
                organization=self.organization,
                unit_type=OrgUnitType.FACULTY,
                name="Yeni Fakültə",
                is_active=True,
            ).exists()
        )

    def test_update_faculty(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.faculties_url,
            {"action": "update", "unit_id": str(self.faculty.id), "name": "Yenilənmiş Fakültə", "code": "YF2"},
        )
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.name, "Yenilənmiş Fakültə")
        self.assertEqual(self.faculty.code, "YF2")

    def test_delete_faculty_blocked_when_it_has_active_kafedra(self):
        self.client.force_login(self.owner)
        self.client.post(self.faculties_url, {"action": "delete", "unit_id": str(self.faculty.id)})
        self.faculty.refresh_from_db()
        self.assertTrue(self.faculty.is_active)

    def test_delete_empty_faculty_soft_deletes(self):
        empty_faculty = OrgUnit.objects.create(
            organization=self.organization,
            unit_type=OrgUnitType.FACULTY,
            name="Boş Fakültə",
            slug="bos-fakulte",
        )
        self.client.force_login(self.owner)
        self.client.post(self.faculties_url, {"action": "delete", "unit_id": str(empty_faculty.id)})
        empty_faculty.refresh_from_db()
        self.assertFalse(empty_faculty.is_active)

    def test_student_cannot_create_faculty(self):
        self.client.force_login(self.student_user)
        self.client.post(self.faculties_url, {"action": "create", "name": "Icazəsiz Fakültə"})
        self.assertFalse(OrgUnit.objects.filter(organization=self.organization, name="Icazəsiz Fakültə").exists())

    def test_assign_faculty_head(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.faculties_url,
            {"action": "assign_head", "unit_id": str(self.faculty.id), "head_user": str(self.teacher_user.id)},
        )
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.head_id, self.teacher_user.id)

        # Boş dəyər təyinatı silir.
        self.client.post(
            self.faculties_url,
            {"action": "assign_head", "unit_id": str(self.faculty.id), "head_user": ""},
        )
        self.faculty.refresh_from_db()
        self.assertIsNone(self.faculty.head_id)


class KafedraCrudTests(StructureViewsTestBase):
    def test_create_kafedra_requires_faculty(self):
        self.client.force_login(self.owner)
        self.client.post(self.kafedras_url, {"action": "create", "name": "Fakültəsiz Kafedra", "parent": ""})
        self.assertFalse(OrgUnit.objects.filter(organization=self.organization, name="Fakültəsiz Kafedra").exists())

        response = self.client.post(
            self.kafedras_url,
            {"action": "create", "name": "Yeni Kafedra", "code": "YK", "parent": str(self.faculty.id)},
        )
        self.assertRedirects(response, self.kafedras_url)
        created = OrgUnit.objects.get(organization=self.organization, name="Yeni Kafedra")
        self.assertEqual(created.parent_id, self.faculty.id)
        self.assertEqual(created.unit_type, OrgUnitType.CHAIR)

    def test_cannot_create_kafedra_under_other_org_faculty(self):
        other_faculty = OrgUnit.objects.create(
            organization=self.other_org,
            unit_type=OrgUnitType.FACULTY,
            name="Yad Fakültə",
            slug="yad-fakulte",
        )
        self.client.force_login(self.owner)
        self.client.post(
            self.kafedras_url,
            {"action": "create", "name": "Sızma Kafedra", "parent": str(other_faculty.id)},
        )
        self.assertFalse(OrgUnit.objects.filter(name="Sızma Kafedra").exists())

    def test_update_kafedra_can_move_to_another_faculty(self):
        second_faculty = OrgUnit.objects.create(
            organization=self.organization,
            unit_type=OrgUnitType.FACULTY,
            name="İkinci Fakültə",
            slug="ikinci-fakulte",
        )
        self.client.force_login(self.owner)
        self.client.post(
            self.kafedras_url,
            {
                "action": "update",
                "unit_id": str(self.kafedra.id),
                "name": "Köçürülmüş Kafedra",
                "code": "KK",
                "parent": str(second_faculty.id),
            },
        )
        self.kafedra.refresh_from_db()
        self.assertEqual(self.kafedra.parent_id, second_faculty.id)
        self.assertEqual(self.kafedra.name, "Köçürülmüş Kafedra")
        # Materialized path yeni valideynə görə yenilənməlidir.
        self.assertTrue(self.kafedra.path.startswith(second_faculty.path))

    def test_delete_kafedra_blocked_when_members_assigned(self):
        self.teacher_membership.scope_unit = self.kafedra
        self.teacher_membership.save(update_fields=["scope_unit"])
        self.client.force_login(self.owner)
        self.client.post(self.kafedras_url, {"action": "delete", "unit_id": str(self.kafedra.id)})
        self.kafedra.refresh_from_db()
        self.assertTrue(self.kafedra.is_active)

    def test_delete_empty_kafedra_soft_deletes(self):
        self.client.force_login(self.owner)
        self.client.post(self.kafedras_url, {"action": "delete", "unit_id": str(self.kafedra.id)})
        self.kafedra.refresh_from_db()
        self.assertFalse(self.kafedra.is_active)


class KafedraTeacherAssignmentTests(StructureViewsTestBase):
    def test_assign_and_remove_teacher(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.kafedras_url,
            {
                "action": "assign_teacher",
                "unit_id": str(self.kafedra.id),
                "membership_id": str(self.teacher_membership.id),
            },
        )
        self.teacher_membership.refresh_from_db()
        self.assertEqual(self.teacher_membership.scope_unit_id, self.kafedra.id)

        self.client.post(
            self.kafedras_url,
            {
                "action": "remove_teacher",
                "unit_id": str(self.kafedra.id),
                "membership_id": str(self.teacher_membership.id),
            },
        )
        self.teacher_membership.refresh_from_db()
        self.assertIsNone(self.teacher_membership.scope_unit_id)

    def test_student_membership_cannot_be_assigned_as_teacher(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.kafedras_url,
            {
                "action": "assign_teacher",
                "unit_id": str(self.kafedra.id),
                "membership_id": str(self.student_membership.id),
            },
        )
        self.student_membership.refresh_from_db()
        self.assertIsNone(self.student_membership.scope_unit_id)

    def test_assign_kafedra_head(self):
        self.client.force_login(self.owner)
        self.client.post(
            self.kafedras_url,
            {"action": "assign_head", "unit_id": str(self.kafedra.id), "head_user": str(self.teacher_user.id)},
        )
        self.kafedra.refresh_from_db()
        self.assertEqual(self.kafedra.head_id, self.teacher_user.id)
