"""«Struktur üzvləri» kabinet reyestri (2026-09-08 yenidən qurulub).

* org-səviyyəli aktor (HR — `member.view`, səviyyə 65) BÜTÜN üzvləri görür və
  rəhbərlik etiketləri (`OrgUnit.head` → «Dekan · <fakültə>») sətirdədir;
* dekan / kafedra müdiri yalnız öz alt-ağacını görür; `scope_unit`-i olmayan
  unit-rolu HEÇ NƏ görmür (QA B-2, fail-closed);
* tələbə və müəllimdə bölmə yoxdur (fraqment 403);
* filtrlər (rol · bölmə · növ · axtarış) və KPI-lər;
* «Üzv kartı» JSON-u qapılı və əhatəlidir (başqa fakültənin adamı 404, kənar
  rol sətirləri sızmır);
* ikinci `<h1>` yoxdur, köhnə «Filtrlə» düyməsi yoxdur.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.organizations.models import Membership, OrgUnit, Role
from core.constants import OrgUnitType, RoleScopeType

from .test_teaching_office_stage2 import PASSWORD, Stage2BaseTest

User = get_user_model()

FIXTURE_USERNAMES = {
    "ds2_teaching_office_head",
    "ds2_chair_head",
    "ds2_dean",
    "ds2_teacher",
    "ds2_student",
    "ds2_hr",
    "ds2_program_coordinator",
    "ds2_vice_dean",
    "ds2_other_teacher",
}
SUBTREE_OF_FACULTY = {"ds2_dean", "ds2_chair_head", "ds2_teacher", "ds2_student", "ds2_program_coordinator"}
LEADERS = {"ds2_dean", "ds2_chair_head", "ds2_teaching_office_head", "ds2_program_coordinator", "ds2_vice_dean"}


class _OrgMembersBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # P1-11 (2026-09-12): üzv reyestrinin əhatəsi artıq `member.view` daşıyan
        # üzvlükdən çıxır (`get_permission_scope`; köhnə ümumi `get_unit_scope`
        # silinib). Real kataloqda dekan və kafedra müdiri bu açarı daşıyır;
        # Mərhələ 2 fiksturu (plan testləri üçün qısaldılmış dəst) onu vermirdi —
        # burada kataloqla uyğunlaşdırılır, əks halda dekan «əhatəsiz» sayılır.
        for name in ("dean", "chair_head"):
            unit_manager_role = cls.roles[name]
            unit_manager_role.permissions = [*unit_manager_role.permissions, "member.view"]
            unit_manager_role.save(update_fields=["permissions"])

        def role(name, level, scope_type, permissions):
            obj, _ = Role.objects.update_or_create(
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
            cls.roles[name] = obj
            return obj

        def user(name):
            obj = User.objects.create_user(name, f"{name}@qku.edu.az", PASSWORD)
            cls.users[name.replace("ds2_", "", 1)] = obj
            return obj

        # Org-səviyyəli baxan: HR — `member.view`, səviyyə 65, ORGANIZATION əhatə, bölməsiz.
        hr = role("hr", 65, RoleScopeType.ORGANIZATION, ["member.view", "unit.view"])
        Membership.objects.create(
            user=user("ds2_hr"),
            organization=cls.org,
            role=hr,
            is_primary=True,
            is_active=True,
            title="Kadrlar şöbəsinin müdiri",
            employee_id="T-0042",
        )
        # Proqram koordinatoru — ixtisasa bağlı unit-rolu (alt-ağacda görünür).
        coordinator = role("program_coordinator", 45, RoleScopeType.UNIT, ["unit.view"])
        Membership.objects.create(
            user=user("ds2_program_coordinator"),
            organization=cls.org,
            role=coordinator,
            scope_unit=cls.specialty,
            is_primary=True,
            is_active=True,
        )
        # Dekan müavini — unit-rolu, amma `scope_unit` TƏYİN EDİLMƏYİB («bölməsiz» siqnalı).
        vice_dean = role("vice_dean", 65, RoleScopeType.UNIT, ["unit.view"])
        Membership.objects.create(
            user=user("ds2_vice_dean"), organization=cls.org, role=vice_dean, is_primary=True, is_active=True
        )
        # Başqa fakültənin müəllimi — dekanın əhatəsindən KƏNAR.
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Hüquq fakültəsi", slug="om-huquq", code="HF"
        )
        cls.other_teacher = user("ds2_other_teacher")
        Membership.objects.create(
            user=cls.other_teacher,
            organization=cls.org,
            role=cls.roles["teacher"],
            scope_unit=cls.other_faculty,
            is_primary=True,
            is_active=True,
        )
        # Rəsmi rəhbərlər (`OrgUnit.head`): fakültə → dekan, kafedra → müdir.
        cls.faculty.head = cls.users["dean"]
        cls.faculty.save(update_fields=["head"])
        cls.chair.head = cls.users["chair_head"]
        cls.chair.save(update_fields=["head"])
        # Tələbə qrupa, müəllim kafedraya bağlanır (bölmə zənciri üçün).
        Membership.objects.filter(organization=cls.org, user=cls.users["student"], role=cls.roles["student"]).update(
            scope_unit=cls.group
        )
        Membership.objects.filter(organization=cls.org, user=cls.users["teacher"], role=cls.roles["teacher"]).update(
            scope_unit=cls.chair
        )

    def _section(self, role_name, **params):
        response = self._fragment(role_name, "org-members", **params)
        self.assertEqual(response.status_code, 200, role_name)
        return response.context["org_members_section"]

    def _detail(self, role_name, user):
        return self._client(role_name).get(
            reverse("organizations:structure_member_detail", kwargs={"slug": self.org.slug, "user_id": user.id})
        )

    @staticmethod
    def _row(section, username):
        return next(row for row in section["rows"] if row["username"] == username)


class MembersFragmentTest(_OrgMembersBase):
    def test_hr_sees_everyone_with_leadership_labels(self):
        response = self._fragment("hr", "org-members")
        self.assertEqual(response.status_code, 200)
        section = response.context["org_members_section"]
        self.assertTrue(section["has_access"])
        self.assertTrue(section["is_org_wide"])
        self.assertEqual({row["username"] for row in section["rows"]}, FIXTURE_USERNAMES)

        dean = self._row(section, "ds2_dean")
        self.assertTrue(dean["is_leader"])
        self.assertEqual([(line["label"], line["unit"]) for line in dean["head_lines"]], [("Dekan", self.faculty.name)])
        self.assertEqual(dean["unit_name"], self.faculty.name)

        chair_head = self._row(section, "ds2_chair_head")
        self.assertEqual(chair_head["head_lines"][0]["label"], "Kafedra müdiri")
        self.assertEqual(chair_head["unit_name"], self.chair.name)
        self.assertEqual(chair_head["unit_trail"], self.faculty.name)

        teacher = self._row(section, "ds2_teacher")
        self.assertFalse(teacher["is_leader"])
        self.assertEqual(teacher["head_lines"], [])

        student = self._row(section, "ds2_student")
        self.assertTrue(student["is_student"])
        self.assertEqual(student["unit_name"], self.group.name)
        self.assertIn(self.specialty.name, student["unit_trail"])

        hr = self._row(section, "ds2_hr")
        self.assertTrue(hr["scope_all"])
        self.assertEqual(hr["title"], "Kadrlar şöbəsinin müdiri")
        self.assertEqual(hr["employee_id"], "T-0042")

        vice_dean = self._row(section, "ds2_vice_dean")
        self.assertTrue(vice_dean["scope_missing"])
        self.assertTrue(vice_dean["is_leader"])

        # Defolt sıralama: rol səviyyəsi yuxarıdan aşağı — tədris şöbəsi rəhbəri (85) birinci.
        self.assertEqual(section["rows"][0]["username"], "ds2_teaching_office_head")

        html = response.json()["html"]
        self.assertNotIn("<h1", html)
        self.assertIn("data-om-root", html)
        self.assertIn('data-ems-filters-auto="1"', html)
        self.assertIn("fa-crown", html)
        self.assertIn("Dekan · " + self.faculty.name, html)
        self.assertIn("omMemberDrawer", html)
        self.assertIn("data-om-detail-open", html)
        self.assertIn('data-ems-kpi-filter="leaders"', html)
        self.assertNotIn("Filtrlə", html)

    def test_kpis_count_distinct_people(self):
        section = self._section("hr")
        kpis = {tile["label"]: tile["value"] for tile in section["kpi_tiles"]}
        self.assertEqual(kpis["Üzv"], len(FIXTURE_USERNAMES))
        self.assertEqual(kpis["Tələbə"], 1)
        self.assertEqual(kpis["Müəllim"], 2)
        self.assertEqual(kpis["Heyət"], len(FIXTURE_USERNAMES) - 1)
        self.assertEqual(kpis["Rəhbərlik"], len(LEADERS))
        self.assertEqual(kpis["Bölməsiz"], 1)
        self.assertEqual(section["total_count"], len(FIXTURE_USERNAMES))

    def test_dean_sees_only_own_subtree(self):
        section = self._section("dean")
        self.assertTrue(section["has_access"])
        self.assertFalse(section["is_org_wide"])
        self.assertEqual({row["username"] for row in section["rows"]}, SUBTREE_OF_FACULTY)
        # Bölmə filtri yalnız əhatədəki vahidləri təklif edir.
        unit_field = next(field for field in section["filter_fields"] if field["name"] == "om_unit")
        labels = [option["label"] for option in unit_field["options"]]
        self.assertIn(self.faculty.name, labels)
        self.assertNotIn(self.other_faculty.name, labels)
        kpis = {tile["label"]: tile["value"] for tile in section["kpi_tiles"]}
        self.assertEqual(kpis["Üzv"], len(SUBTREE_OF_FACULTY))

    def test_chair_head_sees_only_chair_subtree(self):
        section = self._section("chair_head")
        self.assertEqual(
            {row["username"] for row in section["rows"]},
            {"ds2_chair_head", "ds2_teacher", "ds2_student", "ds2_program_coordinator"},
        )

    def test_unit_role_without_scope_unit_sees_nobody(self):
        """QA B-2: bölməsi təyin edilməmiş dekan müavini üzv siyahısı görmür (fail-closed)."""
        section = self._section("vice_dean")
        self.assertTrue(section["has_access"])
        self.assertTrue(section["scope_unset"])
        self.assertEqual(section["rows"], [])
        self.assertEqual(section["table_state"], "empty")
        self.assertEqual(section["state_title"], "Əhatəniz təyin edilməyib")

    def test_student_and_teacher_have_no_section(self):
        self.assertNotIn("org-members", self._sections("student"))
        self.assertNotIn("org-members", self._sections("teacher"))
        self.assertEqual(self._fragment("student", "org-members").status_code, 403)
        self.assertEqual(self._fragment("teacher", "org-members").status_code, 403)


class MembersFilterTest(_OrgMembersBase):
    def test_role_filter(self):
        section = self._section("hr", om_role="teacher")
        self.assertEqual({row["username"] for row in section["rows"]}, {"ds2_teacher", "ds2_other_teacher"})
        self.assertIn("om_role=teacher", section["pagination_query"])
        self.assertIn("section=org-members", section["pagination_query"])
        self.assertEqual(section["filter_count_label"], "Nəticə: 2 üzvlük")

    def test_kind_filters(self):
        leaders = self._section("hr", om_kind="leaders")
        self.assertEqual({row["username"] for row in leaders["rows"]}, LEADERS)
        self.assertTrue(all(row["is_leader"] for row in leaders["rows"]))
        pressed = next(tile for tile in leaders["kpi_tiles"] if tile.get("filter") == "leaders")
        self.assertTrue(pressed["pressed"])

        unscoped = self._section("hr", om_kind="unscoped")
        self.assertEqual({row["username"] for row in unscoped["rows"]}, {"ds2_vice_dean"})

        students = self._section("hr", om_kind="students")
        self.assertEqual({row["username"] for row in students["rows"]}, {"ds2_student"})

        staff = self._section("hr", om_kind="staff")
        self.assertEqual({row["username"] for row in staff["rows"]}, FIXTURE_USERNAMES - {"ds2_student"})

        bogus = self._section("hr", om_kind="whatever")
        self.assertEqual({row["username"] for row in bogus["rows"]}, FIXTURE_USERNAMES)

    def test_unit_filter_covers_subtree(self):
        section = self._section("hr", om_unit=str(self.chair.id))
        self.assertEqual(
            {row["username"] for row in section["rows"]},
            {"ds2_chair_head", "ds2_teacher", "ds2_student", "ds2_program_coordinator"},
        )
        self.assertIn(f"om_unit={self.chair.id}", section["pagination_query"])
        # Səhv UUID sakitcə atılır — bütün siyahı.
        bad = self._section("hr", om_unit="not-a-uuid")
        self.assertEqual({row["username"] for row in bad["rows"]}, FIXTURE_USERNAMES)
        self.assertNotIn("om_unit", bad["pagination_query"])

    def test_search_matches_name_username_and_title(self):
        by_username = self._section("hr", om_q="ds2_hr")
        self.assertEqual({row["username"] for row in by_username["rows"]}, {"ds2_hr"})
        by_title = self._section("hr", om_q="Kadrlar")
        self.assertEqual({row["username"] for row in by_title["rows"]}, {"ds2_hr"})
        none = self._section("hr", om_q="belə adam yoxdur")
        self.assertEqual(none["rows"], [])
        self.assertEqual(none["table_state"], "empty")
        self.assertEqual(none["state_title"], "Filtrə uyğun üzv yoxdur")

    def test_sort_by_name(self):
        section = self._section("hr", om_sort="name")
        names = [row["username"] for row in section["rows"]]
        self.assertEqual(names, sorted(names))
        self.assertIn("om_sort=name", section["pagination_query"])


class MemberDetailTest(_OrgMembersBase):
    def test_hr_gets_full_card(self):
        response = self._detail("hr", self.users["dean"])
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["person"]["username"], "ds2_dean")
        self.assertTrue(payload["person"]["is_leader"])
        self.assertEqual(
            payload["person"]["profile_url"], reverse("accounts:public_profile", kwargs={"username": "ds2_dean"})
        )
        self.assertEqual([row["role"] for row in payload["memberships"]], ["dean"])
        self.assertEqual(payload["memberships"][0]["scope_unit"], self.faculty.name)
        self.assertTrue(payload["memberships"][0]["is_leader"])
        self.assertEqual(
            [(unit["label"], unit["unit"]) for unit in payload["headed_units"]], [("Dekan", self.faculty.name)]
        )

        hr = self._detail("hr", self.users["hr"]).json()
        self.assertTrue(hr["memberships"][0]["scope_all"])
        self.assertEqual(hr["memberships"][0]["title"], "Kadrlar şöbəsinin müdiri")
        self.assertEqual(hr["headed_units"], [])

    def test_detail_is_scoped_and_gated(self):
        # Dekan: öz alt-ağacındakı şəxs → 200; başqa fakültənin müəllimi → 404.
        self.assertEqual(self._detail("dean", self.users["chair_head"]).status_code, 200)
        self.assertEqual(self._detail("dean", self.other_teacher).status_code, 404)
        # Tələbə / müəllim → 403 (giriş yoxdur).
        self.assertEqual(self._detail("student", self.users["dean"]).status_code, 403)
        self.assertEqual(self._detail("teacher", self.users["dean"]).status_code, 403)
        # Bölməsiz dekan müavini heç kimi görmür → 404.
        self.assertEqual(self._detail("vice_dean", self.users["dean"]).status_code, 404)

    def test_out_of_scope_roles_do_not_leak_to_unit_scoped_viewer(self):
        Membership.objects.create(
            user=self.users["chair_head"],
            organization=self.org,
            role=self.roles["program_coordinator"],
            scope_unit=self.other_faculty,
            is_active=True,
        )
        scoped = self._detail("dean", self.users["chair_head"]).json()
        self.assertEqual([row["role"] for row in scoped["memberships"]], ["chair_head"])
        full = self._detail("hr", self.users["chair_head"]).json()
        self.assertEqual(sorted(row["role"] for row in full["memberships"]), ["chair_head", "program_coordinator"])


class MembersQueryBudgetTest(_OrgMembersBase):
    """Sorğu sayı səhifədəki sətir sayından ASILI DEYİL (bölmə zənciri / rəhbərlik
    sətirləri `UnitIndex`-dən, sətirlər `select_related` ilə tək sorğudan gəlir)."""

    def _add_members(self, count, *, start):
        for index in range(start, start + count):
            member = User.objects.create_user(f"ds2_bulk_{index}", f"bulk{index}@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=member,
                organization=self.org,
                role=self.roles["teacher"],
                scope_unit=self.chair if index % 2 else self.group,
                is_primary=True,
                is_active=True,
            )

    def _count_queries(self, role_name):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = self._client(role_name)
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "org-members"})
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url, {"om_sort": "name"})
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries), len(response.context["org_members_section"]["rows"])

    def test_fragment_query_count_does_not_grow_with_rows(self):
        self._add_members(4, start=0)
        few_queries, few_rows = self._count_queries("hr")
        self._add_members(12, start=100)
        many_queries, many_rows = self._count_queries("hr")
        self.assertGreater(many_rows, few_rows)
        self.assertEqual(many_queries, few_queries)
        # Bölməyə bağlı aktor (dekan) üçün də eyni.
        dean_queries, dean_rows = self._count_queries("dean")
        self._add_members(10, start=200)
        dean_queries_more, dean_rows_more = self._count_queries("dean")
        self.assertGreater(dean_rows_more, dean_rows)
        self.assertEqual(dean_queries_more, dean_queries)
