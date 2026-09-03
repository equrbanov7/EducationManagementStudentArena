"""Tədris şöbəsi bölmələri (ekran 01–04) — icazə, əhatə, CRUD, arxiv, audit.

Nəyi qoruyur
------------
1. **Rol qapısı.** `teaching_office_head` və RİM dörd bölməni GÖRÜR; müəllim və
   tələbə fraqment API-sindən 403 alır (`unit.view` / `catalog.view` açarları
   onlarda QƏSDƏN yoxdur).
2. **Alias muafiyyəti.** `teaching_office_head` səviyyəsi 85 ≥ 80 olsa da
   implicit `org_admin` aliası ALMIR — əks halda bütün tenant idarəetmə səthi
   ona açılardı (`core.roles.ADMIN_ALIAS_EXEMPT_ROLE_NAMES`).
3. **Əhatə.** Kafedra müdiri «Kafedra profili»ndə YALNIZ öz kafedrasını görür.
4. **Silmə yoxdur — arxivləmə var** + səbəb ≥20 simvol + `AuditLog` yazısı.
5. **Server tərəfli filtr/sıralama/səhifələmə** parametrləri işləyir.
6. **İcazə kataloqu** — yeni açarlar kataloqda və etiket cədvəlindədir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Program, Subject
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.roles import ProfileRole

User = get_user_model()

PASSWORD = "StrongPass123!"

TEACHING_OFFICE_SECTIONS = ("org-structure-tree", "chair-profile", "programs-registry", "subject-catalog")

#: Rol → (səviyyə, icazələr). `default_roles_teaching_office` ilə eyni dəst.
ROLE_SPECS = {
    "teaching_office_head": (
        85,
        [
            "org.view",
            "unit.view",
            "unit.create",
            "unit.edit",
            "unit.tree_manage",
            "unit.assign_head",
            "catalog.view",
            "catalog.manage",
            "member.view",
        ],
    ),
    "teaching_office_staff": (
        60,
        ["org.view", "unit.view", "unit.create", "unit.edit", "unit.tree_manage", "catalog.view", "catalog.manage"],
    ),
    "ikt_rehber": (88, ["unit.*", "catalog.view", "catalog.manage", "member.view"]),
    "chair_head": (70, ["unit.view", "catalog.view", "member.view"]),
    "teacher": (50, ["course.view", "syllabus.edit"]),
    "student": (10, ["course.view"]),
}


class TeachingOfficeSectionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tof_owner", "tof_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Tədris Univ",
            slug="tof-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Mühəndislik fakültəsi", slug="muh-fak"
        )
        cls.chair_a = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.faculty,
            unit_type=OrgUnitType.CHAIR,
            name="İnformatika kafedrası",
            slug="inf-kaf",
        )
        cls.chair_b = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.faculty,
            unit_type=OrgUnitType.CHAIR,
            name="Riyaziyyat kafedrası",
            slug="riy-kaf",
        )

        cls.users = {}
        cls.roles = {}
        for name, (level, permissions) in ROLE_SPECS.items():
            # Kafedra müdiri REAL seed-də UNIT scope-ludur (öz kafedrası) —
            # əhatə testinin mənası buradan gəlir.
            scope_type = RoleScopeType.UNIT if name == "chair_head" else RoleScopeType.ORGANIZATION
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": scope_type,
                    "permissions": permissions,
                    "is_system": True,
                    "is_active": True,
                },
            )
            cls.roles[name] = role
            user = User.objects.create_user(f"tof_{name}", f"tof_{name}@qku.edu.az", PASSWORD)
            scope_unit = cls.chair_a if name == "chair_head" else None
            Membership.objects.create(
                user=user,
                organization=cls.org,
                role=role,
                scope_unit=scope_unit,
                is_primary=True,
                is_active=True,
            )
            cls.users[name] = user

        cls.program = Program.objects.create(
            organization=cls.org,
            code="QA-DS1-PRG",
            official_code="6050100",
            name="QA-DS1 Kompüter elmləri",
            specialty_unit=cls.chair_a,
        )
        cls.subject = Subject.objects.create(
            organization=cls.org, code="QA-DS1-SBJ", name="QA-DS1 Alqoritmlər", ects=6, chair_unit=cls.chair_a
        )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _client(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _sections(self, role_name):
        response = self._client(role_name).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    def _fragment(self, role_name, section, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": section})
        return self._client(role_name).get(url, params)

    # ── 1. Rol qapısı ───────────────────────────────────────────────────────

    def test_teaching_office_head_sees_all_four_sections(self):
        sections = self._sections("teaching_office_head")
        for key in TEACHING_OFFICE_SECTIONS:
            self.assertIn(key, sections, key)

    def test_rim_sees_all_four_sections(self):
        sections = self._sections("ikt_rehber")
        for key in TEACHING_OFFICE_SECTIONS:
            self.assertIn(key, sections, key)

    def test_fragment_returns_200_for_teaching_office_head(self):
        for section in TEACHING_OFFICE_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(self._fragment("teaching_office_head", section).status_code, 200)

    def test_fragment_returns_403_for_teacher_and_student(self):
        for role in ("teacher", "student"):
            for section in TEACHING_OFFICE_SECTIONS:
                with self.subTest(role=role, section=section):
                    self.assertEqual(self._fragment(role, section).status_code, 403)

    def test_teacher_and_student_do_not_see_sections_in_menu(self):
        for role in ("teacher", "student"):
            leaked = self._sections(role) & set(TEACHING_OFFICE_SECTIONS)
            self.assertEqual(leaked, set(), f"{role}: {sorted(leaked)}")

    def test_staff_role_has_no_head_assignment_button(self):
        """Əməkdaş bölmələri görür, RƏHBƏR TƏYİN ETMİR (`unit.assign_head` yoxdur)."""
        response = self._fragment("teaching_office_staff", "org-structure-tree")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-tof-open="tofHeadDialog"')

    # ── 2. Alias muafiyyəti ─────────────────────────────────────────────────

    def test_teaching_office_head_is_alias_exempt(self):
        self.assertIn("teaching_office_head", ProfileRole.ADMIN_ALIAS_EXEMPT_ROLE_NAMES)
        aliases = ProfileRole.aliases_for_membership_role("teaching_office_head", level=85)
        self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)

    def test_teaching_office_head_does_not_get_org_admin_surfaces(self):
        sections = self._sections("teaching_office_head")
        for forbidden in ("permission-editor", "manage-roles", "role-assignment", "org-roles"):
            self.assertNotIn(forbidden, sections, forbidden)

    # ── 3. Əhatə ────────────────────────────────────────────────────────────

    def test_chair_head_sees_only_own_chair(self):
        response = self._fragment("chair_head", "chair-profile")
        self.assertEqual(response.status_code, 200)
        section = response.context["chair_profile_section"]
        names = {chair["name"] for chair in section["chairs"]}
        self.assertEqual(names, {self.chair_a.name})

    def test_teaching_office_head_sees_every_chair(self):
        response = self._fragment("teaching_office_head", "chair-profile")
        section = response.context["chair_profile_section"]
        names = {chair["name"] for chair in section["chairs"]}
        self.assertEqual(names, {self.chair_a.name, self.chair_b.name})

    # ── 4. Filtr / sıralama / səhifələmə (server tərəfdə) ───────────────────

    def test_program_registry_applies_filters_and_sort(self):
        Program.objects.create(
            organization=self.org,
            code="QA-DS1-PRG2",
            official_code="7050100",
            name="QA-DS1 Magistr",
            specialty_unit=None,
        )
        response = self._fragment("teaching_office_head", "programs-registry", pg_q="Magistr", pg_sort="-code")
        section = response.context["programs_registry_section"]
        self.assertEqual(section["filters"]["search"], "Magistr")
        self.assertEqual(section["filters"]["sort"], "-code")
        self.assertEqual([row["name"] for row in section["rows"]], ["QA-DS1 Magistr"])

    def test_subject_catalog_flags_duplicate_names(self):
        Subject.objects.create(
            organization=self.org, code="QA-DS1-SBJ2", name="QA-DS1 Alqoritmlər", ects=6, chair_unit=self.chair_b
        )
        response = self._fragment("teaching_office_head", "subject-catalog")
        section = response.context["subject_catalog_section"]
        self.assertEqual(section["duplicate_name_total"], 1)
        self.assertTrue(all(row["is_duplicate"] for row in section["rows"]))

    def test_program_no_plan_flag_is_computed(self):
        response = self._fragment("teaching_office_head", "programs-registry")
        section = response.context["programs_registry_section"]
        self.assertEqual(section["no_plan_total"], 1)
        self.assertFalse(section["rows"][0]["has_plan"])

    def test_pagination_parameter_is_server_side(self):
        for index in range(30):
            Subject.objects.create(organization=self.org, code=f"QA-DS1-P{index:03d}", name=f"Fənn {index}", ects=3)
        first = self._fragment("teaching_office_head", "subject-catalog")
        second = self._fragment("teaching_office_head", "subject-catalog", sb_page="2")
        self.assertEqual(first.context["subject_catalog_section"]["page_obj"].number, 1)
        self.assertEqual(second.context["subject_catalog_section"]["page_obj"].number, 2)

    # ── 5. CRUD + arxiv + səbəb + audit ─────────────────────────────────────

    def test_catalog_create_and_edit_subject(self):
        client = self._client("teaching_office_head")
        url = reverse("registrar:catalog_action")
        created = client.post(
            url,
            {"action": "save_subject", "code": "QA-DS1-NEW", "name": "QA-DS1 Yeni fənn", "kind": "core", "ects": "4"},
        )
        self.assertEqual(created.status_code, 200)
        subject = Subject.objects.get(organization=self.org, code="QA-DS1-NEW")
        self.assertEqual(subject.ects, 4)

        edited = client.post(
            url,
            {
                "action": "save_subject",
                "id": str(subject.id),
                "code": "QA-DS1-NEW",
                "name": "QA-DS1 Dəyişdirilmiş",
                "kind": "elective",
                "ects": "5",
            },
        )
        self.assertEqual(edited.status_code, 200)
        subject.refresh_from_db()
        self.assertEqual(subject.name, "QA-DS1 Dəyişdirilmiş")
        self.assertEqual(subject.kind, "elective")

    def test_catalog_rejects_duplicate_subject_code(self):
        client = self._client("teaching_office_head")
        response = client.post(
            reverse("registrar:catalog_action"),
            {"action": "save_subject", "code": self.subject.code, "name": "Başqa", "kind": "core", "ects": "3"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "code")

    def test_archive_requires_reason_of_20_chars(self):
        client = self._client("teaching_office_head")
        short = client.post(
            reverse("registrar:catalog_action"),
            {"action": "archive", "kind": "subject", "id": str(self.subject.id), "reason": "qısa"},
        )
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["error"], "reason_too_short")
        self.subject.refresh_from_db()
        self.assertFalse(self.subject.is_archived)

    def test_archive_writes_reason_and_audit_and_keeps_the_row(self):
        client = self._client("teaching_office_head")
        reason = "Fənn 2025/2026 tədris ilindən istifadədən çıxarılır."
        response = client.post(
            reverse("registrar:catalog_action"),
            {"action": "archive", "kind": "subject", "id": str(self.subject.id), "reason": reason},
        )
        self.assertEqual(response.status_code, 200)
        self.subject.refresh_from_db()
        # Silmə YOXDUR — sətir qalır, yalnız bayraq dəyişir.
        self.assertTrue(Subject.objects.filter(pk=self.subject.pk).exists())
        self.assertTrue(self.subject.is_archived)
        self.assertEqual(self.subject.archived_reason, reason)
        self.assertIsNotNone(self.subject.archived_at)
        self.assertTrue(
            AuditLog.objects.filter(organization=self.org, reason__icontains="catalog: archived").exists(),
            "arxivləmə audit jurnalına yazılmayıb",
        )

    def test_archived_row_is_filtered_out_by_default(self):
        self.subject.is_archived = True
        self.subject.save(update_fields=["is_archived"])
        default_view = self._fragment("teaching_office_head", "subject-catalog")
        archived_view = self._fragment("teaching_office_head", "subject-catalog", sb_arch="1")
        default_codes = {row["code"] for row in default_view.context["subject_catalog_section"]["rows"]}
        archived_codes = {row["code"] for row in archived_view.context["subject_catalog_section"]["rows"]}
        self.assertNotIn(self.subject.code, default_codes)
        self.assertIn(self.subject.code, archived_codes)

    def test_catalog_action_is_forbidden_for_teacher(self):
        response = self._client("teacher").post(
            reverse("registrar:catalog_action"),
            {"action": "save_subject", "code": "QA-DS1-X", "name": "X", "kind": "core", "ects": "3"},
        )
        self.assertEqual(response.status_code, 403)

    # ── 6. Struktur ağacı əməlləri ──────────────────────────────────────────

    def _tree_url(self):
        return reverse("organizations:structure_tree_action", kwargs={"slug": self.org.slug})

    def test_tree_create_child_unit(self):
        response = self._client("teaching_office_head").post(
            self._tree_url(),
            {
                "action": "create_child",
                "parent": str(self.chair_a.id),
                "name": "QA-DS1 İxtisas",
                "unit_type": "specialty",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrgUnit.objects.filter(organization=self.org, parent=self.chair_a, name="QA-DS1 İxtisas").exists()
        )

    def test_tree_assign_head_requires_permission_and_reason(self):
        target = self.users["teacher"]
        # Əməkdaşda `unit.assign_head` YOXDUR → 403.
        denied = self._client("teaching_office_staff").post(
            self._tree_url(),
            {
                "action": "assign_head",
                "unit": str(self.chair_b.id),
                "head": str(target.id),
                "reason": "Kafedra müdiri vəzifəsinə təyinat sənədi əsasında.",
            },
        )
        self.assertEqual(denied.status_code, 403)

        short_reason = self._client("teaching_office_head").post(
            self._tree_url(),
            {"action": "assign_head", "unit": str(self.chair_b.id), "head": str(target.id), "reason": "qısa"},
        )
        self.assertEqual(short_reason.status_code, 400)

        ok = self._client("teaching_office_head").post(
            self._tree_url(),
            {
                "action": "assign_head",
                "unit": str(self.chair_b.id),
                "head": str(target.id),
                "reason": "Kafedra müdiri vəzifəsinə təyinat sənədi əsasında.",
            },
        )
        self.assertEqual(ok.status_code, 200)
        self.chair_b.refresh_from_db()
        self.assertEqual(self.chair_b.head_id, target.id)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="head assigned").exists())

    def test_tree_archive_is_soft_and_blocks_units_with_children(self):
        client = self._client("teaching_office_head")
        reason = "Fakültə birləşdirilir, struktur yenidən qurulur."
        blocked = client.post(self._tree_url(), {"action": "archive", "unit": str(self.faculty.id), "reason": reason})
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["error"], "has_children")

        ok = client.post(self._tree_url(), {"action": "archive", "unit": str(self.chair_b.id), "reason": reason})
        self.assertEqual(ok.status_code, 200)
        self.chair_b.refresh_from_db()
        # Silmə YOXDUR — sətir qalır.
        self.assertTrue(OrgUnit.objects.filter(pk=self.chair_b.pk).exists())
        self.assertFalse(self.chair_b.is_active)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="unit archived").exists())

    def test_tree_action_is_forbidden_for_student(self):
        response = self._client("student").post(
            self._tree_url(), {"action": "rename", "unit": str(self.chair_a.id), "name": "Yeni ad"}
        )
        self.assertEqual(response.status_code, 403)

    # ── 7. Struktur ağacı kontekstinin özü ──────────────────────────────────

    def test_tree_context_flags_units_without_head(self):
        response = self._fragment("teaching_office_head", "org-structure-tree")
        section = response.context["structure_tree_section"]
        self.assertEqual(section["head_missing_count"], 3)  # fakültə + 2 kafedra
        self.assertTrue(section["tree_nodes"])
        self.assertEqual(section["tree_nodes"][0]["label"], self.faculty.name)

    def test_tree_search_filter_keeps_parent_chain(self):
        response = self._fragment("teaching_office_head", "org-structure-tree", st_q="İnformatika")
        section = response.context["structure_tree_section"]
        labels = {node["label"] for node in section["tree_nodes"]}
        self.assertEqual(labels, {self.faculty.name})
        self.assertEqual([child["label"] for child in section["tree_nodes"][0]["children"]], [self.chair_a.name])


class TeachingOfficePermissionCatalogTest(TestCase):
    """Yeni açarlar kataloqda, etiketdə və rol şablonundadır."""

    def test_new_keys_are_in_the_permission_catalog(self):
        from apps.organizations.permissions import PERMISSION_CATEGORIES, PERMISSION_LABELS, get_all_permissions

        keys = ("unit.tree_manage", "unit.assign_head", "catalog.view", "catalog.manage")
        available = set(get_all_permissions())
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, available)
                self.assertIn(key, PERMISSION_LABELS)
        self.assertIn("catalog", PERMISSION_CATEGORIES)

    def test_role_templates_carry_the_new_keys(self):
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        by_name = {role["name"]: role for role in UNIVERSITY_ROLES}
        self.assertIn("teaching_office_head", by_name)
        self.assertIn("teaching_office_staff", by_name)
        self.assertEqual(by_name["teaching_office_head"]["level"], 85)
        self.assertEqual(by_name["teaching_office_staff"]["level"], 60)
        self.assertIn("unit.assign_head", by_name["teaching_office_head"]["permissions"])
        # Əməkdaşda rəhbər təyini QƏSDƏN yoxdur.
        self.assertNotIn("unit.assign_head", by_name["teaching_office_staff"]["permissions"])
        for role_name in ("dean", "chair_head", "program_coordinator"):
            self.assertIn("catalog.view", by_name[role_name]["permissions"], role_name)
            self.assertNotIn("catalog.manage", by_name[role_name]["permissions"], role_name)

    def test_section_registry_is_consistent(self):
        from apps.accounts.views.profile._sections.labels import (
            DIRECT_PROFILE_SECTION_TEMPLATES,
            build_section_titles,
        )
        from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

        titles = build_section_titles()
        for key in TEACHING_OFFICE_SECTIONS:
            with self.subTest(key=key):
                self.assertIn(key, SECTION_PARTIALS)
                self.assertIn(key, AJAX_SAFE_SECTIONS)
                self.assertIn(key, DIRECT_PROFILE_SECTION_TEMPLATES)
                self.assertIn(key, titles)
