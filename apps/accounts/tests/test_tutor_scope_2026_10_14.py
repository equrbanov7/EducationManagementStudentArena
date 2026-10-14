"""Tyutor / proqram koordinatoru — OXU əhatəsi FAKÜLTƏ, «Semestr açılışı» yox (sahib 2026-10-14 axşam).

Sahib (tyutor kimi baxış): «tyutor olaraq ancaq özünün aid olduğu fakültəni görsün gərək və o fakültəyə aid
ixtisas və s.»; «Semestr açılışını yığışdır buradan — ancaq dekan və kafedra müdiri görə bilsin»; «Tyutor və
proqram koordinatoru eyni vəzifədir … adətən fakültə dekanlığı tərkibində olur»; «Fakültəyə aid olan
ixtisaslar görünsün».

Kilidlənən müqavilə (REAL rol şablonları, struktur real universitet kimi:
``Fakültə → {Kafedra, İxtisas → Qrup}``):
* (a) fakültəyə və (b) kafedraya təyin olunmuş tyutor / koordinator: «Tələbə reyestri» (sətir, KPI, BÜTÜN
  süzgəc seçimləri), «İxtisaslar», «Fənn kataloqu», «Qruplar», tələbə kataloqu, struktur ağacı — yalnız ÖZ
  fakültəsi; başqa fakültə nə sətirdə, nə seçicidə;
* yazı əhatəsi dar qalır: kafedra tyutoru fakültənin qrupunu görür, amma sətir idarə / starosta düymələri
  yoxdur (server də 404); fakültə tyutorunda düymələr var;
* «Semestr açılışı» — dekan, kafedra müdiri, Tədris şöbəsi görür; tyutor / koordinator görmür.
"""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.people.permissions import PeopleActor
from apps.accounts.services.people.students import scoped_student_records
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.organizations.public import faculty_read_scope, get_permission_scope
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

MIGRATION = importlib.import_module("apps.organizations.migrations.0065_semester_view_dean_chair_only")


@override_settings(UNIVERSITY_MODE=True)
class TutorFacultyScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tfs_owner", "tfs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="TFS Univ",
                slug="tfs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.fac_a, cls.chair_a, cls.spec_a, cls.group_a = cls._branch("A", "Alfa məktəbi", "ALFA-11", "AZ")
            cls.fac_b, cls.chair_b, cls.spec_b, cls.group_b = cls._branch("B", "Beta məktəbi", "BETA-22", "EN")
            cls.program_a = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec_a, code="TFSA", name="Proqram Alfa"
            )
            cls.program_b = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec_b, code="TFSB", name="Proqram Beta"
            )
            cls.cur_a = Curriculum.objects.create(organization=cls.org, program=cls.program_a, admission_year=2026)
            cls.cur_b = Curriculum.objects.create(organization=cls.org, program=cls.program_b, admission_year=2026)
            Subject.objects.create(organization=cls.org, code="TFS-A1", name="Alfa fənni", chair_unit=cls.chair_a)
            cls.subj_b = Subject.objects.create(
                organization=cls.org, code="TFS-B1", name="Beta fənni", chair_unit=cls.chair_b
            )
            cls.subj_shared = Subject.objects.create(
                organization=cls.org, code="TFS-B2", name="Ümumi fənn", chair_unit=cls.chair_b
            )
            cls.subj_offered = Subject.objects.create(
                organization=cls.org, code="TFS-B3", name="Təklif fənni", chair_unit=cls.chair_b
            )
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.cur_a, subject=cls.subj_shared, semester_number=1
            )
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.cur_b, subject=cls.subj_b, semester_number=1
            )
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız 2026",
                period_type="semester",
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
            )
            CourseOffering.objects.create(
                organization=cls.org, subject=cls.subj_offered, period=period, group=cls.group_a
            )

            cls.ali = cls._student("tfs_ali", "Əli", cls.program_a, cls.cur_a, cls.group_a)
            cls.far = cls._student("tfs_far", "Fərid", cls.program_b, cls.cur_b, cls.group_b)

            cls.tutor_fac = cls._staff("tfs_tutor_fac", "tutor", cls.fac_a)
            cls.tutor_chair = cls._staff("tfs_tutor_chair", "tutor", cls.chair_a)
            cls.coord_chair = cls._staff("tfs_coord_chair", "program_coordinator", cls.chair_a)
            cls.coord_group = cls._staff("tfs_coord_group", "program_coordinator", cls.group_a)
            cls.dean = cls._staff("tfs_dean", "dean", cls.fac_a)
            cls.chair_head = cls._staff("tfs_chair", "chair_head", cls.chair_a)
            cls.office = cls._staff("tfs_office", "teaching_office_staff", None)

    @classmethod
    def _branch(cls, tag, faculty_name, group_name, sector):
        faculty = OrgUnit.objects.create(
            organization=cls.org, name=faculty_name, slug=f"tfs-fac-{tag}", unit_type=OrgUnitType.FACULTY
        )
        chair = OrgUnit.objects.create(
            organization=cls.org, parent=faculty, name=f"Kafedra {tag}", slug=f"tfs-ch-{tag}", unit_type="chair"
        )
        specialty = OrgUnit.objects.create(
            organization=cls.org,
            parent=faculty,
            name=f"İxtisas {tag}",
            slug=f"tfs-sp-{tag}",
            unit_type=OrgUnitType.SPECIALTY,
        )
        group = OrgUnit.objects.create(
            organization=cls.org,
            parent=specialty,
            name=group_name,
            slug=f"tfs-g-{tag}",
            unit_type=OrgUnitType.GROUP,
            settings={"language_sector": sector, "course_year": 1},
        )
        return faculty, chair, specialty, group

    @classmethod
    def _student(cls, username, first, program, curriculum, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=first, last_name="Test")
        UserProfile.objects.filter(user=user).update(organization=cls.org)
        Membership.objects.create(
            user=user, organization=cls.org, role=Role.objects.get(organization=cls.org, name="student"), is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=2026,
        )
        return user

    @classmethod
    def _staff(cls, username, role_name, unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=username)
        UserProfile.objects.filter(user=user).update(organization=cls.org)
        Membership.objects.create(
            user=user,
            organization=cls.org,
            role=Role.objects.get(organization=cls.org, name=role_name),
            scope_unit=unit,
            is_active=True,
            is_primary=True,
        )
        return user

    # ── köməkçilər ──────────────────────────────────────────────────────────

    @property
    def tutors(self):
        return (self.tutor_fac, self.tutor_chair, self.coord_chair)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def section(self, user, name, key, **params):
        with bypass_rls():
            response = self.client_for(user).get(reverse("accounts:profile"), {"section": name, **params})
        self.assertEqual(response.status_code, 200)
        return response, response.context[key]

    @staticmethod
    def labels(options):
        return {option["label"] for option in options}

    @staticmethod
    def field_labels(section, name):
        field = next(field for field in section["filter_fields"] if field["name"] == name)
        return {option["label"] for option in field["options"] if option.get("value")}

    @staticmethod
    def tree_labels(nodes):
        out = []
        for node in nodes:
            out.append(node["label"])
            out.extend(TutorFacultyScopeTest.tree_labels(node["children"]))
        return out

    # ── əhatə resolveri ─────────────────────────────────────────────────────

    def test_read_scope_widens_to_faculty_write_scope_stays_narrow(self):
        for user, narrow in (
            (self.tutor_fac, self.fac_a),
            (self.tutor_chair, self.chair_a),
            (self.coord_chair, self.chair_a),
            (self.coord_group, self.group_a),
        ):
            with self.subTest(user=user.username):
                for permission in ("unit.view", "people.view_students", "catalog.view", "student.registry_view"):
                    widened = faculty_read_scope(user, self.org, permission)
                    self.assertEqual(set(widened.unit_ids), {self.fac_a.pk}, permission)
                manage = get_permission_scope(user, self.org, "unit.group_manage")
                self.assertEqual(set(manage.unit_ids), {narrow.pk})

    # ── «Tələbə reyestri» ───────────────────────────────────────────────────

    def test_student_registry_rows_kpis_and_all_filter_options_are_faculty_scoped(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                response, section = self.section(user, "student-registry", "student_registry_section")
                self.assertTrue(section["has_access"])
                self.assertEqual([row["name"] for row in section["rows"]], ["Əli Test"])
                self.assertEqual(section["total"], 1)
                self.assertEqual(section["kpis"]["total"], 1)
                options = section["options"]
                self.assertEqual(self.labels(options["faculties"]), {"Alfa məktəbi"})
                self.assertEqual(self.labels(options["programs"]), {"Proqram Alfa"})
                self.assertEqual(self.labels(options["groups"]), {"ALFA-11"})
                self.assertEqual(self.labels(options["sectors"]), {"AZ"})
                self.assertEqual(self.field_labels(section, "sr_faculty"), {"Alfa məktəbi"})
                self.assertNotContains(response, "Beta məktəbi")
                self.assertNotContains(response, "BETA-22")
                self.assertFalse(section["can_move"])
                # Kənar fakültə parametri sətir açmır.
                _response, section = self.section(
                    user, "student-registry", "student_registry_section", sr_faculty=str(self.fac_b.pk)
                )
                self.assertEqual(section["rows"], [])

    def test_student_registry_card_outside_faculty_is_404(self):
        client = self.client_for(self.tutor_chair)
        with bypass_rls():
            own = StudentAcademicRecord.objects.get(student=self.ali)
            foreign = StudentAcademicRecord.objects.get(student=self.far)
            ok = client.get(reverse("accounts:student_registry_card", args=[own.pk]))
            denied = client.get(reverse("accounts:student_registry_card", args=[foreign.pk]))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(denied.status_code, 404)

    # ── «İxtisaslar» / «Fənn kataloqu» ──────────────────────────────────────

    def test_programs_registry_shows_own_faculty_programs(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                _response, section = self.section(user, "programs-registry", "programs_registry_section")
                self.assertEqual([row["name"] for row in section["rows"]], ["Proqram Alfa"])
                self.assertEqual(section["total_count"], 1)

    def test_subject_catalog_shows_own_faculty_subjects(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                _response, section = self.section(user, "subject-catalog", "subject_catalog_section")
                codes = {row["code"] for row in section["rows"]}
                self.assertEqual(codes, {"TFS-A1", "TFS-B2", "TFS-B3"})
                self.assertNotIn("TFS-B1", codes)

    # ── «Qruplar» + yazı düymələri ──────────────────────────────────────────

    def test_groups_registry_rows_and_options_are_faculty_scoped(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                response, section = self.section(user, "groups-registry", "groups_registry_section")
                self.assertEqual([row["name"] for row in section["rows"]], ["ALFA-11"])
                self.assertEqual(self.labels(section["faculty_options"]), {"Alfa məktəbi"})
                self.assertEqual(self.labels(section["specialty_options"]), {"İxtisas A"})
                self.assertNotContains(response, "BETA-22")

    def test_kafedra_tutor_sees_faculty_group_without_write_buttons(self):
        response, section = self.section(self.tutor_chair, "groups-registry", "groups_registry_section")
        self.assertTrue(section["can_manage"])  # öz kafedrasında yeni qrup yarada bilər
        row = section["rows"][0]
        self.assertFalse(row["can_manage"])
        self.assertFalse(row["can_lead"])
        html = response.content.decode()
        self.assertIn('data-can-manage="0"', html)
        self.assertIn('data-can-lead="0"', html)
        self.assertNotIn('data-tof-open="tofGroupArchiveDialog"', html)
        self.assertNotIn(f'data-tof-bulk-item="{self.group_a.pk}"', html)
        client = self.client_for(self.tutor_chair)
        with bypass_rls():
            drawer = client.get(reverse("organizations:group_students", args=[self.org.slug, self.group_a.pk]))
            lead = client.post(
                reverse("accounts:group_lead_action"),
                {
                    "action": "assign",
                    "group_id": str(self.group_a.pk),
                    "record_id": str(StudentAcademicRecord.objects.get(student=self.ali).pk),
                },
            )
        self.assertEqual(drawer.status_code, 200)
        self.assertFalse(drawer.json()["can_manage"])
        self.assertEqual(lead.status_code, 404)

    def test_faculty_tutor_keeps_write_buttons_on_own_groups(self):
        response, section = self.section(self.tutor_fac, "groups-registry", "groups_registry_section")
        row = section["rows"][0]
        self.assertTrue(row["can_manage"])
        self.assertTrue(row["can_lead"])
        html = response.content.decode()
        self.assertIn('data-can-manage="1"', html)
        self.assertIn('data-tof-open="tofGroupArchiveDialog"', html)

    # ── tələbə kataloqu + struktur ağacı ────────────────────────────────────

    def test_people_students_catalog_is_faculty_scoped(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                role = Membership.objects.get(user=user, organization=self.org).role
                actor = PeopleActor(
                    user=user, organization=self.org, permissions=frozenset(role.permissions or []), is_superadmin=False
                )
                with bypass_rls():
                    usernames = set(scoped_student_records(actor).values_list("student__username", flat=True))
                self.assertEqual(usernames, {"tfs_ali"})

    def test_structure_tree_shows_own_faculty_only(self):
        for user in self.tutors:
            with self.subTest(user=user.username):
                response, section = self.section(user, "org-structure-tree", "structure_tree_section")
                labels = self.tree_labels(section["tree_nodes"])
                self.assertIn("Alfa məktəbi", labels)
                self.assertIn("İxtisas A", labels)
                self.assertIn("ALFA-11", labels)
                self.assertNotIn("Beta məktəbi", labels)
                self.assertNotIn("BETA-22", labels)
                self.assertNotContains(response, "BETA-22")
                _response, section = self.section(
                    user, "org-structure-tree", "structure_tree_section", st_unit=str(self.group_b.pk)
                )
                self.assertIsNone(section["detail"])

    def test_tree_group_panel_students_visible_lead_only_in_write_scope(self):
        _response, section = self.section(
            self.tutor_chair, "org-structure-tree", "structure_tree_section", st_unit=str(self.group_a.pk)
        )
        panel = section["detail"]["group_panel"]
        self.assertTrue(panel["can_view_students"])
        self.assertFalse(panel["can_assign_lead"])
        _response, section = self.section(
            self.tutor_fac, "org-structure-tree", "structure_tree_section", st_unit=str(self.group_a.pk)
        )
        self.assertTrue(section["detail"]["group_panel"]["can_assign_lead"])

    # ── «Semestr açılışı» ───────────────────────────────────────────────────

    def test_semester_opening_only_dean_chair_head_and_office(self):
        for user in (self.dean, self.chair_head, self.office):
            with self.subTest(user=user.username):
                response, _section = self.section(user, "semester-opening", "semester_opening_section")
                self.assertIn("semester-opening", response.context["allowed_sections"])
        for user in (self.tutor_fac, self.tutor_chair, self.coord_chair):
            with self.subTest(user=user.username):
                with bypass_rls():
                    page = self.client_for(user).get(reverse("accounts:profile"))
                    fragment = self.client_for(user).get(
                        reverse("accounts:profile_section_fragment", kwargs={"section": "semester-opening"})
                    )
                self.assertNotIn("semester-opening", page.context["allowed_sections"])
                self.assertIn(fragment.status_code, (403, 404))


class FacultyWideningRulesTest(TestCase):
    """``widen_chair_scope_to_faculty`` — tipə görə, ən yaxın AKTİV fakültə; digər tiplər toxunulmur."""

    def setUp(self):
        owner = User.objects.create_user("fwr_owner", "fwr_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="FWR Univ",
                slug="fwr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            self.faculty = OrgUnit.objects.create(
                organization=self.org, name="F", slug="fwr-f", unit_type=OrgUnitType.FACULTY
            )
            self.specialty = OrgUnit.objects.create(
                organization=self.org, parent=self.faculty, name="S", slug="fwr-s", unit_type=OrgUnitType.SPECIALTY
            )
            self.center = OrgUnit.objects.create(
                organization=self.org, parent=self.faculty, name="C", slug="fwr-c", unit_type=OrgUnitType.CENTER
            )
            self.dormant = OrgUnit.objects.create(
                organization=self.org, name="D", slug="fwr-d", unit_type=OrgUnitType.FACULTY, is_active=False
            )
            self.orphan_chair = OrgUnit.objects.create(
                organization=self.org, parent=self.dormant, name="K", slug="fwr-k", unit_type="chair"
            )

    def _widen(self, *units):
        from apps.organizations.scoping import UnitScope, widen_chair_scope_to_faculty

        scope = UnitScope(
            scope_type="unit", unit_ids=frozenset(u.pk for u in units), unit_paths=tuple(u.path for u in units)
        )
        with bypass_rls():
            return widen_chair_scope_to_faculty(self.org, scope)

    def test_specialty_widens_other_types_and_dormant_faculty_do_not(self):
        self.assertEqual(set(self._widen(self.specialty).unit_ids), {self.faculty.pk})
        self.assertEqual(set(self._widen(self.center).unit_ids), {self.center.pk})
        self.assertEqual(set(self._widen(self.orphan_chair).unit_ids), {self.orphan_chair.pk})

    def test_unit_in_scope(self):
        from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, unit_in_scope

        scope = self._widen(self.specialty)
        self.assertTrue(unit_in_scope(scope, self.faculty))
        self.assertTrue(unit_in_scope(scope, self.center))
        self.assertFalse(unit_in_scope(scope, self.dormant))
        self.assertTrue(unit_in_scope(ORG_WIDE_SCOPE, self.dormant))
        self.assertFalse(unit_in_scope(EMPTY_SCOPE, self.faculty))
        self.assertFalse(unit_in_scope(scope, None))


class SemesterViewTemplateTest(TestCase):
    @staticmethod
    def _seed(name):
        return next(row for row in UNIVERSITY_ROLES if row["name"] == name)

    def test_template_semester_view_only_for_dean_chair_and_operators(self):
        for name in ("tutor", "program_coordinator"):
            self.assertNotIn("semester.view", self._seed(name)["permissions"], name)
        for name in ("dean", "chair_head", "teaching_office_head", "teaching_office_staff", "vice_rector"):
            self.assertIn("semester.view", self._seed(name)["permissions"], name)
        self.assertEqual(set(self._seed("tutor")["permissions"]), set(self._seed("program_coordinator")["permissions"]))


class SemesterViewMigrationTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user("svm_owner", "svm_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="SVM Univ",
                slug="svm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            for name in ("tutor", "program_coordinator", "dean", "chair_head"):
                role = Role.objects.get(organization=self.org, name=name)
                if "semester.view" not in role.permissions:
                    role.permissions = [*role.permissions, "semester.view"]
                    role.save(update_fields=["permissions"])

    def _perms(self, name):
        with bypass_rls():
            return list(Role.objects.get(organization=self.org, name=name).permissions)

    def test_forward_removes_key_from_tutor_and_coordinator_only_idempotent(self):
        with bypass_rls():
            MIGRATION.forward(django_apps, None)
            first = {name: self._perms(name) for name in ("tutor", "program_coordinator")}
            MIGRATION.forward(django_apps, None)
        for name in ("tutor", "program_coordinator"):
            self.assertNotIn("semester.view", self._perms(name))
            self.assertEqual(first[name], self._perms(name))
        for name in ("dean", "chair_head"):
            self.assertIn("semester.view", self._perms(name))

    def test_wildcard_roles_untouched(self):
        with bypass_rls():
            tutor = Role.objects.get(organization=self.org, name="tutor")
            tutor.permissions = ["semester.*", "unit.view"]
            tutor.save(update_fields=["permissions"])
            coordinator = Role.objects.get(organization=self.org, name="program_coordinator")
            coordinator.permissions = ["*"]
            coordinator.save(update_fields=["permissions"])
            MIGRATION.forward(django_apps, None)
        self.assertEqual(self._perms("tutor"), ["semester.*", "unit.view"])
        self.assertEqual(self._perms("program_coordinator"), ["*"])

    def test_backward_restores_key_once(self):
        with bypass_rls():
            MIGRATION.forward(django_apps, None)
            MIGRATION.backward(django_apps, None)
            MIGRATION.backward(django_apps, None)
        for name in ("tutor", "program_coordinator"):
            self.assertEqual(self._perms(name).count("semester.view"), 1)
