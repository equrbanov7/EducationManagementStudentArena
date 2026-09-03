"""
Fakültə / Kafedra ayrı idarəetmə səhifələrinin testləri (structure_views).

Yoxlanılır:
- icazə: owner/superadmin idarə edir, adi üzv görmür, başqa org-un istifadəçisi girə bilmir
- CRUD: yaratma, redaktə, silmə (qoruma qaydaları ilə birlikdə)
- müəllim təyinatı: assign_teacher / remove_teacher (Membership.scope_unit)
- rəhbər təyinatı: assign_head
- axtarış / fakültə filtri
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar.models import CourseOffering, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType

from ..models import AcademicPeriod, Membership, Organization, OrgUnit

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


class TeacherCountTests(StructureViewsTestBase):
    """Aktiv (cari tədris ili) / indiyə kimi müəllim sayı ayrımı.

    Bax apps/organizations/structure_views/_shared.py
    (``_current_academic_year_period_ids`` / ``_active_teacher_user_ids``).
    """

    def setUp(self):
        super().setUp()
        self.current_period = AcademicPeriod.objects.create(
            organization=self.organization,
            name="2025/2026 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2026-01-31",
            is_current=True,
        )
        self.past_period = AcademicPeriod.objects.create(
            organization=self.organization,
            name="2021/2022 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2021/2022",
            start_date="2021-09-01",
            end_date="2022-01-31",
        )
        self.subject = Subject.objects.create(organization=self.organization, code="TST101", name="Test fənni", ects=5)

        # teacher_user: kafedraya təyin olunub VƏ cari ildə dərs deyir → aktiv.
        self.teacher_membership.scope_unit = self.kafedra
        self.teacher_membership.save(update_fields=["scope_unit"])
        CourseOffering.objects.create(
            organization=self.organization,
            subject=self.subject,
            period=self.current_period,
            instructor=self.teacher_user,
        )

        # İkinci müəllim: eyni kafedraya təyin olunub, AMMA yalnız köhnə ildə
        # dərs deyib → "indiyə kimi"yə düşür, "aktiv"ə YOX.
        self.past_teacher = User.objects.create_user(
            username="structure_past_teacher",
            email="structure_past_teacher@example.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=self.past_teacher,
            organization=self.organization,
            role=self.organization.roles.get(name="teacher"),
            is_active=True,
            scope_unit=self.kafedra,
        )
        CourseOffering.objects.create(
            organization=self.organization,
            subject=self.subject,
            period=self.past_period,
            instructor=self.past_teacher,
        )

    def test_kafedra_list_shows_active_and_total_counts_separately(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.kafedras_url)
        self.assertEqual(response.status_code, 200)
        kafedra_row = response.context["org_kafedras_section"]["kafedras"][0]
        self.assertEqual(kafedra_row.active_teacher_count, 1)
        self.assertEqual(kafedra_row.teacher_count, 2)

    def test_faculty_list_aggregates_teacher_counts_from_children(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.faculties_url)
        self.assertEqual(response.status_code, 200)
        faculty_row = response.context["org_faculties_section"]["faculties"][0]
        self.assertEqual(faculty_row.active_teacher_count, 1)
        self.assertEqual(faculty_row.teacher_count, 2)

    def test_teacher_who_never_taught_counts_only_toward_total(self):
        idle_teacher = User.objects.create_user(
            username="structure_idle_teacher",
            email="structure_idle_teacher@example.com",
            password="testpass123",
        )
        Membership.objects.create(
            user=idle_teacher,
            organization=self.organization,
            role=self.organization.roles.get(name="teacher"),
            is_active=True,
            scope_unit=self.kafedra,
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.kafedras_url)
        kafedra_row = response.context["org_kafedras_section"]["kafedras"][0]
        self.assertEqual(kafedra_row.teacher_count, 3)
        self.assertEqual(kafedra_row.active_teacher_count, 1)

    def test_deactivated_user_membership_excluded_from_both_counts(self):
        """Deaktiv istifadəçinin köhnə üzvlüyü nə "aktiv", nə "indiyə kimi"
        sayılmamalıdır — sayğac və siyahı eyni mənbədən gəlməlidir (əvvəlki
        annotate-based sayğac bunu nəzərə almırdı, siyahı isə nəzərə alırdı)."""
        self.teacher_user.is_active = False
        self.teacher_user.save(update_fields=["is_active"])
        self.client.force_login(self.owner)
        response = self.client.get(self.kafedras_url)
        kafedra_row = response.context["org_kafedras_section"]["kafedras"][0]
        # Yalnız past_teacher qalır (indiyə kimi=1, aktiv=0).
        self.assertEqual(kafedra_row.teacher_count, 1)
        self.assertEqual(kafedra_row.active_teacher_count, 0)


class TeacherCountQueryBudgetTests(StructureViewsTestBase):
    """Sorğu sayı səhifədəki vahid sayı ilə ARTMAMALIDIR (bax tapşırıq şərti)."""

    def setUp(self):
        super().setUp()
        self.current_period = AcademicPeriod.objects.create(
            organization=self.organization,
            name="2025/2026 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2026-01-31",
            is_current=True,
        )
        self.subject = Subject.objects.create(organization=self.organization, code="QB101", name="Query Budget", ects=5)
        self.client.force_login(self.owner)

    def _add_kafedra_with_teacher(self, index):
        kafedra = OrgUnit.objects.create(
            organization=self.organization,
            parent=self.faculty,
            unit_type=OrgUnitType.CHAIR,
            name=f"Sorğu Kafedrası {index}",
            slug=f"sorgu-kafedrasi-{index}",
        )
        teacher = User.objects.create_user(
            username=f"qb_teacher_{index}", email=f"qb_teacher_{index}@example.com", password="testpass123"
        )
        Membership.objects.create(
            user=teacher,
            organization=self.organization,
            role=self.organization.roles.get(name="teacher"),
            is_active=True,
            scope_unit=kafedra,
        )
        CourseOffering.objects.create(
            organization=self.organization, subject=self.subject, period=self.current_period, instructor=teacher
        )
        return kafedra

    def test_kafedra_list_query_count_is_independent_of_unit_count(self):
        for i in range(2):
            self._add_kafedra_with_teacher(i)
        # İsti-tur: ilk giriş sonrası sessiya sətri bir dəfəlik UPDATE olunur
        # (Django session engine) — bu, ölçüyə aidiyyatı olmayan "gizli" sorğu
        # sayı fərqi yaradırdı. Ölçümdən ƏVVƏL bir dəfə çağırıb sabitləşdiririk.
        self.client.get(self.kafedras_url)
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(self.kafedras_url)
        self.assertEqual(response.status_code, 200)

        for i in range(2, 15):
            self._add_kafedra_with_teacher(i)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.kafedras_url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "Kafedra siyahısının sorğu sayı kafedra/müəllim sayı ilə artmamalıdır",
        )

    def test_faculty_list_query_count_is_independent_of_unit_count(self):
        for i in range(2):
            self._add_kafedra_with_teacher(i)
        self.client.get(self.faculties_url)  # isti-tur — bax yuxarıdakı şərh
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(self.faculties_url)
        self.assertEqual(response.status_code, 200)

        for i in range(2, 15):
            self._add_kafedra_with_teacher(i)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.faculties_url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "Fakültə siyahısının sorğu sayı kafedra/müəllim sayı ilə artmamalıdır",
        )


class UnitDetailViewTests(StructureViewsTestBase):
    """ "Ətraflı bax" AJAX endpoint-i (organizations:structure_unit_detail)."""

    def setUp(self):
        super().setUp()
        self.teacher_membership.scope_unit = self.kafedra
        self.teacher_membership.save(update_fields=["scope_unit"])
        self.detail_url = reverse(
            "organizations:structure_unit_detail", kwargs={"slug": self.organization.slug, "unit_id": self.kafedra.id}
        )
        self.faculty_detail_url = reverse(
            "organizations:structure_unit_detail", kwargs={"slug": self.organization.slug, "unit_id": self.faculty.id}
        )

    def test_owner_can_fetch_kafedra_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.detail_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("Test Kafedrası", payload["html"])

    def test_owner_can_fetch_faculty_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.faculty_detail_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("Test Fakültəsi", payload["html"])

    def test_student_forbidden(self):
        self.client.force_login(self.student_user)
        response = self.client.get(self.detail_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)

    def test_outsider_forbidden(self):
        self.client.force_login(self.outsider)
        response = self.client.get(self.detail_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)

    def test_unknown_unit_returns_404(self):
        self.client.force_login(self.owner)
        missing_url = reverse(
            "organizations:structure_unit_detail",
            kwargs={"slug": self.organization.slug, "unit_id": uuid.uuid4()},
        )
        response = self.client.get(missing_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 404)

    def test_dean_scoped_to_own_faculty_cannot_open_other_faculty(self):
        """Scope-suz sızma bloker tapıntısı (bax CLAUDE.md) — dekan yalnız öz
        fakültəsini (və onun kafedralarını) aça bilməlidir."""
        other_faculty = OrgUnit.objects.create(
            organization=self.organization,
            unit_type=OrgUnitType.FACULTY,
            name="Yad Fakültə",
            slug="yad-fakulte-detail",
        )
        dean_role = self.organization.roles.get(name="dean")
        dean = User.objects.create_user(
            username="structure_dean", email="structure_dean@example.com", password="testpass123"
        )
        Membership.objects.create(
            user=dean,
            organization=self.organization,
            role=dean_role,
            scope_unit=self.faculty,
            is_primary=True,
            is_active=True,
        )
        self.client.force_login(dean)

        own_response = self.client.get(self.detail_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(own_response.status_code, 200)

        other_url = reverse(
            "organizations:structure_unit_detail",
            kwargs={"slug": self.organization.slug, "unit_id": other_faculty.id},
        )
        other_response = self.client.get(other_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(other_response.status_code, 404)
