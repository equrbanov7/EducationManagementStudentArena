"""RİM «Yeni inzibati bölmə» — şöbə/mərkəz yaratma səthi.

Nəyi qoruyur
------------
Operator RİM mərkəzindən hesab yarada bilirdi, inzibati bölmə üçün isə ayrı
ekran (Universitet strukturu) axtarmalı idi. Yeni səth həmin boşluğu bağlayır,
LAKİN yazı yolu təkrarlanmır — bölməni MÖVCUD ``structure_tree_action``
(``action=create_child``) yaradır. Bu fayl həmin müqaviləni sabitləyir:

* qapı ``unit.tree_manage``-dir və hesab açarından (``user.import``) AYRIDIR:
  idxal edə bilən HR bölmə yarada BİLMİR, RİM rəhbəri (ikt_rehber) hər ikisini
  edir, RİM əməkdaşı isə heç birini;
* seçim yalnız İNZİBATİ tiplərə açıqdır — fakültə/kafedra/ixtisas/qrup akademik
  ağacın həlqələridir və bu səthdən yaradılmır;
* valideyn seçicisi ``admin_parent`` kataloqundadır, öz açarı ilə qorunur və
  qrup/ixtisas qaytarmır;
* yaradılış mövcud endpoint-dən keçir → audit sətri və görünürlük qapısı ağac
  ekranı ilə eynidir.
"""

from django.test import override_settings
from django.urls import reverse

from apps.accounts.services.rim import create_unit as rim_unit
from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.organizations.structure_views.tree import TREE_TYPE_ORDER
from core.constants import OrgUnitType

from .test_rim_account_create import RimCreateBase


@override_settings(RATELIMIT_ENABLE=False)
class RimUnitPermissionTest(RimCreateBase):
    """Qapı: `unit.tree_manage` — hesab açarı bölmə yaratmağa icazə VERMİR."""

    def test_gate_key_is_the_structure_tree_key(self):
        self.assertEqual(rim_unit.PERM_UNIT_TREE, "unit.tree_manage")

    def test_tree_manager_can_create_units(self):
        self.assertTrue(rim_unit.can_create_unit(self.actor_for(self.rim)))

    def test_importer_without_the_tree_key_cannot(self):
        # HR `user.import` daşıyır (hesab yarada bilir), `unit.tree_manage` YOX.
        actor = self.actor_for(self.hr)
        self.assertNotIn("unit.tree_manage", self.org.roles.get(name="hr").permissions)
        self.assertFalse(rim_unit.can_create_unit(actor))
        with self.assertRaises(Exception) as caught:
            rim_unit.require_create_unit(actor)
        self.assertEqual(caught.exception.reason_code, "permission_denied")
        self.assertEqual(caught.exception.status, 403)

    def test_account_operators_and_students_cannot(self):
        for user in (self.rim_staff, self.teacher, self.student):
            self.assertFalse(rim_unit.can_create_unit(self.actor_for(user)), user.username)


class RimUnitTypeCatalogTest(RimCreateBase):
    """Tip siyahısı — inzibati dörd tip, akademik həlqələr YOX."""

    def test_choices_are_the_administrative_types(self):
        choices = rim_unit.admin_unit_type_choices(self.org)
        self.assertEqual(
            [row["value"] for row in choices],
            [OrgUnitType.DEPARTMENT, OrgUnitType.CENTER, OrgUnitType.INSTITUTE, OrgUnitType.LAB],
        )
        self.assertTrue(all(str(row["label"]) for row in choices))

    def test_academic_types_are_excluded(self):
        values = {row["value"] for row in rim_unit.admin_unit_type_choices(self.org)}
        for excluded in (OrgUnitType.FACULTY, OrgUnitType.CHAIR, OrgUnitType.SPECIALTY, OrgUnitType.GROUP):
            self.assertNotIn(excluded, values)

    def test_every_offered_type_is_accepted_by_the_server(self):
        # Server `TREE_TYPE_ORDER`-dan kənar tipi rədd edir — siyahı sürüşməsin.
        for code in rim_unit.ADMIN_UNIT_TYPES:
            self.assertIn(code, TREE_TYPE_ORDER, code)


@override_settings(RATELIMIT_ENABLE=False)
class RimUnitParentCatalogTest(RimCreateBase):
    """Valideyn seçicisi — öz açarı, öz əhatəsi."""

    def _catalog(self, user, **params):
        return self.client_for(user).get(reverse("accounts:rim_create_catalog"), {"catalog": "admin_parent", **params})

    def test_catalog_requires_the_tree_key(self):
        self.assertEqual(self._catalog(self.hr).status_code, 403)
        self.assertEqual(self._catalog(self.rim_staff).status_code, 403)
        self.assertEqual(self._catalog(self.hr).json()["error"], "permission_denied")

    def test_catalog_returns_parent_candidates_with_type_hints(self):
        response = self._catalog(self.rim)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        names = {row["text"] for row in payload["results"]}
        self.assertIn("Mühəndislik", names)
        self.assertIn("Kompüter kafedrası", names)
        faculty_row = next(row for row in payload["results"] if row["text"] == "Mühəndislik")
        self.assertTrue(faculty_row["hint"], "valideyn sətri tip etiketi daşımalıdır")

    def test_groups_and_specialities_are_not_offered_as_parents(self):
        names = {row["text"] for row in self._catalog(self.rim).json()["results"]}
        self.assertNotIn("SI-101", names)
        self.assertNotIn("Kompüter mühəndisliyi", names)

    def test_catalog_is_searchable(self):
        payload = self._catalog(self.rim, q="Kompüter kafed").json()
        self.assertEqual([row["text"] for row in payload["results"]], ["Kompüter kafedrası"])


@override_settings(RATELIMIT_ENABLE=False)
class RimUnitSectionTest(RimCreateBase):
    """Bölmə konteksti + şablon — seçim yalnız açarı olanda görünür."""

    def _section(self, user):
        return self.client_for(user).get(reverse("accounts:profile"), {"section": "rim-center"})

    def test_tree_manager_sees_the_choice(self):
        response = self._section(self.rim)
        section = response.context["rim_center_section"]
        self.assertTrue(section["can_create_unit"])
        self.assertEqual(
            section["unit_action_url"],
            reverse("organizations:structure_tree_action", kwargs={"slug": self.org.slug}),
        )
        self.assertContains(response, 'data-rimc-open="unit"')
        self.assertContains(response, 'id="rimc-admin-unit"')

    def test_importer_without_the_tree_key_does_not_see_it(self):
        response = self._section(self.hr)
        section = response.context["rim_center_section"]
        self.assertFalse(section["can_create_unit"])
        self.assertTrue(section["can_create"])
        self.assertEqual(section["unit_type_choices"], [])
        self.assertNotContains(response, 'data-rimc-open="unit"')
        self.assertNotContains(response, 'id="rimc-admin-unit"')
        # Hesab axını toxunulmaz qalır.
        self.assertContains(response, 'data-rimc-open="student"')

    def test_account_only_operator_keeps_the_account_flow(self):
        response = self._section(self.rim_staff)
        self.assertNotContains(response, "data-rimc-root")


@override_settings(RATELIMIT_ENABLE=False)
class RimUnitCreateTest(RimCreateBase):
    """Uğurlu yol — MÖVCUD struktur-ağac endpoint-i, audit sətri ilə."""

    def _url(self):
        return reverse("organizations:structure_tree_action", kwargs={"slug": self.org.slug})

    def _create(self, user, **overrides):
        payload = {
            "action": "create_child",
            "parent": str(self.faculty.pk),
            "name": "Beynəlxalq əlaqələr şöbəsi",
            "unit_type": OrgUnitType.DEPARTMENT,
            "code": "BES",
        }
        payload.update(overrides)
        return self.client_for(user).post(self._url(), payload)

    def test_department_is_created_under_the_chosen_parent(self):
        response = self._create(self.rim)
        self.assertEqual(response.status_code, 200)
        created = OrgUnit.objects.get(organization=self.org, name="Beynəlxalq əlaqələr şöbəsi")
        self.assertEqual(str(created.pk), response.json()["unit_id"])
        self.assertEqual(created.parent_id, self.faculty.pk)
        self.assertEqual(created.unit_type, OrgUnitType.DEPARTMENT)
        self.assertEqual(created.code, "BES")
        self.assertTrue(created.is_active)

    def test_center_is_created_too(self):
        response = self._create(self.rim, name="Karyera mərkəzi", unit_type=OrgUnitType.CENTER, code="")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrgUnit.objects.filter(organization=self.org, name="Karyera mərkəzi", unit_type=OrgUnitType.CENTER).exists()
        )

    def test_creation_writes_an_audit_row(self):
        self._create(self.rim, name="Audit şöbəsi")
        # Sətri ağac əməlinin ÖZÜ yazır (`structure_actions._create_child`) — RİM
        # səthi ayrıca audit qatı əlavə etmir, ona görə mətn də oradakı mətndir.
        rows = AuditLog.objects.filter(organization=self.org, reason__startswith="structure tree: child unit created")
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.user_id, self.rim.pk)
        self.assertEqual(row.new_values["name"], "Audit şöbəsi")
        # Hədəf `obj=` ilə yazılır → `content_type` + `object_id` (bax core.audit.log_action).
        created = OrgUnit.objects.get(organization=self.org, name="Audit şöbəsi")
        self.assertEqual(row.object_id, str(created.pk))

    def test_importer_without_the_tree_key_is_refused_server_side(self):
        response = self._create(self.hr, name="İcazəsiz şöbə")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(OrgUnit.objects.filter(organization=self.org, name="İcazəsiz şöbə").exists())

    def test_missing_name_is_a_field_error(self):
        response = self._create(self.rim, name="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "name_required")

    def test_unknown_parent_is_not_found(self):
        response = self._create(self.rim, parent=str(self.org.pk))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not_found")
