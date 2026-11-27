from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType


class RegistryNameTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("registry_head")
        self.org = Organization.objects.create(
            name="Test Universiteti",
            slug="registry-test",
            owner=self.user,
            org_type=OrganizationType.UNIVERSITY,
            status="active",
        )
        role, _ = Role.objects.update_or_create(
            organization=self.org,
            name="teaching_office_head",
            defaults={
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["unit.view", "unit.create", "unit.edit"],
            },
        )
        Membership.objects.create(user=self.user, role=role, organization=self.org, is_active=True, is_primary=True)
        self.url = reverse("organizations:structure_unit_action", args=[self.org.slug])

    def office_client(self):
        client = Client()
        client.force_login(self.user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_concurrent_faculty_creation(self):
        names = ["Yeni fakültə", "yeni FAKÜLTƏ"]
        clients = [self.office_client() for _ in names]
        barrier = Barrier(2)

        def create(item):
            client, name = item
            try:
                barrier.wait(timeout=10)
                response = client.post(self.url, {"action": "save_unit", "kind": "faculty", "name": name})
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = dict(pool.map(create, zip(clients, names)))
        self.assertEqual(set(results), {200, 400}, results)
        self.assertEqual((results[400]["error"], results[400]["field"]), ("name_taken", "name"))
        self.assertEqual(OrgUnit.objects.filter(organization=self.org, name__in=names).count(), 1)

    def test_structure_and_legacy_forms_report_duplicate_names(self):
        faculty = OrgUnit.objects.create(
            organization=self.org, name="İqlim", slug="iqlim", unit_type=OrgUnitType.FACULTY
        )
        other = OrgUnit.objects.create(
            organization=self.org, name="Ədəbiyyat", slug="edeb", unit_type=OrgUnitType.FACULTY
        )
        OrgUnit.objects.create(
            organization=self.org, name="İqlim", slug="chair", parent=faculty, unit_type=OrgUnitType.CHAIR
        )
        client = self.office_client()
        cases = (
            ("structure_tree_action", {"action": "rename", "unit": other.pk}),
            ("structure_tree_action", {"action": "create_child", "parent": faculty.pk, "unit_type": "chair"}),
            ("structure_faculties", {"action": "create"}),
            ("structure_kafedras", {"action": "create", "parent": faculty.pk}),
            ("structure", {"unit_kind": "faculty"}),
            ("structure_unit_action", {"action": "save_unit", "kind": "faculty", "id": other.pk}),
        )
        for route, data in cases:
            with self.subTest(route=route, action=data.get("action")):
                response = client.post(
                    reverse(f"organizations:{route}", args=[self.org.slug]),
                    {**data, "name": "iqlim"},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(response.status_code, 400, response.content[:200])
                self.assertFalse(response.json()["ok"])
                if route.endswith("action"):
                    self.assertEqual(response.json()["error"], "name_taken")
        other.refresh_from_db()
        self.assertEqual(other.name, "Ədəbiyyat")
        self.assertEqual(self.org.units.count(), 3)

    def test_azerbaijani_case_nfc_archive_and_scope(self):
        def unit(name, slug, kind=OrgUnitType.FACULTY, **kwargs):
            return OrgUnit.objects.create(organization=self.org, name=name, slug=slug, unit_type=kind, **kwargs)

        main = unit("İŞIĞ ƏÖÜ", "original")
        for alias in ("işığ əöü", "I\u0307ŞIĞ ƏO\u0308Ü", "  işığ əöü  ", "\tİŞIĞ ƏÖÜ\u00a0"):
            with self.subTest(alias=alias), self.assertRaises(IntegrityError), transaction.atomic():
                unit(alias, "clash")
        distinct = unit("ışığ əöü", "distinct")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrgUnit.objects.filter(pk=distinct.pk).update(name="işığ əöü")
        unit("işığ əöü", "archived", is_active=False)
        unit("işığ əöü", "chair", OrgUnitType.CHAIR)
        with self.assertRaises(IntegrityError), transaction.atomic():
            unit("İŞIĞ ƏÖÜ", "old-dept-kind", OrgUnitType.DEPARTMENT)
        other = Organization.objects.create(name="Başqa universitet", slug="registry-other", owner=self.user)
        OrgUnit.objects.create(organization=other, unit_type=OrgUnitType.FACULTY, name=main.name, slug="other")
        main.is_active = False
        main.save(update_fields=["is_active"])
        unit("işığ əöü", "replacement")
