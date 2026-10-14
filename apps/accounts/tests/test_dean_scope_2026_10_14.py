"""Dekan / kafedra müdiri əhatəsi — kabinet reyestrləri (sahib, 2026-10-14).

Sahib (dekan və kafedra müdiri kimi baxış): «Hər dekan özünün aid olduğu fakültə tələbə məlumatını
görsün»; «Fənn kataloqu — ancaq özünə aid olan fənlər, fakültədəki»; «İxtisaslar — özünə aid olduğu»;
«Təşkilatın mövcud üzvləri»ndə «Bölmə» süzgəci əslində qrupları göstərirdi («Qrup yaz»); kafedra
müdirinə «Fakültələr» lazım deyil; kafedra müdiri öz fakültəsinin tələbələrini görsün.

Struktur REAL universitet kimidir: ixtisas və qruplar FAKÜLTƏNİN altındadır, kafedra yanındadır:
``Fakültə A → {Kafedra A, İxtisas A → Qrup A}``. Rollar tenant yaradılanda əkilən şablonlardır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.people.permissions import PERM_VIEW_STUDENTS, PeopleActor
from apps.accounts.services.people.students import scoped_student_records
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
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


@override_settings(UNIVERSITY_MODE=True)
class DeanScopeRegistriesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("dsc_owner", "dsc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="DSC Univ",
                slug="dsc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.fac_a, cls.chair_a, cls.spec_a, cls.group_a = cls._branch("A", "Alfa məktəbi", "ALFA-11")
            cls.fac_b, cls.chair_b, cls.spec_b, cls.group_b = cls._branch("B", "Beta məktəbi", "BETA-22")
            cls.program_a = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec_a, code="DSCA", name="Proqram Alfa"
            )
            cls.program_b = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec_b, code="DSCB", name="Proqram Beta"
            )
            cls.cur_a = Curriculum.objects.create(organization=cls.org, program=cls.program_a, admission_year=2026)
            cls.cur_b = Curriculum.objects.create(organization=cls.org, program=cls.program_b, admission_year=2026)

            # Fənlər: A kafedrasının öz fənni; B-nin öz fənni; B-yə məxsus, amma A planında işlənən ümumi fənn;
            # B-yə məxsus, amma A qrupuna dərs təklifi olan fənn.
            cls.subj_a = Subject.objects.create(
                organization=cls.org, code="DSC-A1", name="Alfa fənni", chair_unit=cls.chair_a
            )
            cls.subj_b = Subject.objects.create(
                organization=cls.org, code="DSC-B1", name="Beta fənni", chair_unit=cls.chair_b
            )
            cls.subj_shared = Subject.objects.create(
                organization=cls.org, code="DSC-B2", name="Ümumi fənn", chair_unit=cls.chair_b
            )
            cls.subj_offered = Subject.objects.create(
                organization=cls.org, code="DSC-B3", name="Təklif fənni", chair_unit=cls.chair_b
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

            cls.ali = cls._student("dsc_ali", "Əli", cls.program_a, cls.cur_a, cls.group_a)
            cls.far = cls._student("dsc_far", "Fərid", cls.program_b, cls.cur_b, cls.group_b)

            cls.dean = cls._staff("dsc_dean", "dean", cls.fac_a)
            cls.chair_head = cls._staff("dsc_chair", "chair_head", cls.chair_a)
            cls.rector = cls._staff("dsc_rector", "rector", None)
            cls.office = cls._staff("dsc_office", "teaching_office_staff", None)

    @classmethod
    def _branch(cls, tag, faculty_name, group_name):
        faculty = OrgUnit.objects.create(
            organization=cls.org, name=faculty_name, slug=f"dsc-fac-{tag}", unit_type=OrgUnitType.FACULTY
        )
        chair = OrgUnit.objects.create(
            organization=cls.org,
            parent=faculty,
            name=f"Kafedra {tag}",
            slug=f"dsc-ch-{tag}",
            unit_type=OrgUnitType.CHAIR,
        )
        specialty = OrgUnit.objects.create(
            organization=cls.org,
            parent=faculty,
            name=f"İxtisas {tag}",
            slug=f"dsc-sp-{tag}",
            unit_type=OrgUnitType.SPECIALTY,
        )
        group = OrgUnit.objects.create(
            organization=cls.org, parent=specialty, name=group_name, slug=f"dsc-g-{tag}", unit_type=OrgUnitType.GROUP
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
    def kpi(section):
        return {tile["label"]: tile["value"] for tile in section["kpi_tiles"]}

    # ── «Qruplar» ───────────────────────────────────────────────────────────

    def test_groups_registry_rows_and_kpis_are_dean_scoped(self):
        response, section = self.section(self.dean, "groups-registry", "groups_registry_section")
        self.assertEqual([row["name"] for row in section["rows"]], ["ALFA-11"])
        kpi = self.kpi(section)
        self.assertEqual(kpi["QRUP"], 1)
        self.assertEqual(kpi["TƏLƏBƏ"], 1)
        self.assertEqual(kpi["REYESTRDƏ CƏMİ"], 1)
        self.assertEqual({row["label"] for row in section["faculty_options"]}, {"Alfa məktəbi"})
        self.assertNotContains(response, "BETA-22")
        # Birbaşa kənar fakültə parametri sətir açmır.
        _response, section = self.section(
            self.dean, "groups-registry", "groups_registry_section", gr_faculty=str(self.fac_b.pk)
        )
        self.assertEqual(section["rows"], [])

    def test_groups_registry_rector_sees_all(self):
        _response, section = self.section(self.rector, "groups-registry", "groups_registry_section")
        self.assertEqual({row["name"] for row in section["rows"]}, {"ALFA-11", "BETA-22"})
        self.assertEqual(self.kpi(section)["TƏLƏBƏ"], 2)

    # ── «Fənn kataloqu» ─────────────────────────────────────────────────────

    def test_subject_catalog_dean_sees_own_chair_plan_and_offering_subjects(self):
        response, section = self.section(self.dean, "subject-catalog", "subject_catalog_section")
        codes = {row["code"] for row in section["rows"]}
        self.assertEqual(codes, {"DSC-A1", "DSC-B2", "DSC-B3"})
        self.assertEqual(section["total_count"], 3)
        self.assertEqual(self.kpi(section)["FƏNN"], 3)
        self.assertEqual(self.kpi(section)["PLANDA İSTİFADƏDƏ"], 1)
        chairs = {row["label"] for row in section["chair_options"]}
        self.assertIn("Kafedra A", chairs)
        self.assertNotContains(response, "Beta fənni")
        # Axtarış və birbaşa kafedra parametri əhatədən çıxarmır.
        _response, section = self.section(self.dean, "subject-catalog", "subject_catalog_section", sb_q="Beta")
        self.assertEqual(section["rows"], [])
        _response, section = self.section(
            self.dean, "subject-catalog", "subject_catalog_section", sb_chair=str(self.chair_b.pk)
        )
        self.assertEqual({row["code"] for row in section["rows"]}, {"DSC-B2", "DSC-B3"})

    def test_subject_catalog_org_wide_roles_see_all(self):
        for actor in (self.rector, self.office):
            _response, section = self.section(actor, "subject-catalog", "subject_catalog_section")
            self.assertEqual(section["total_count"], 4)
            self.assertEqual(self.kpi(section)["PLANDA İSTİFADƏDƏ"], 2)

    # ── «İxtisaslar» ────────────────────────────────────────────────────────

    def test_programs_registry_dean_scoped_and_detail_blocked(self):
        _response, section = self.section(self.dean, "programs-registry", "programs_registry_section")
        self.assertEqual([row["name"] for row in section["rows"]], ["Proqram Alfa"])
        self.assertEqual(section["total_count"], 1)
        self.assertEqual(self.kpi(section)["REYESTRDƏ CƏMİ"], 1)
        self.assertNotIn("Kafedra B", {row["label"] for row in section["chair_options"]})
        client = self.client_for(self.dean)
        with bypass_rls():
            own = client.get(reverse("registrar:program_detail"), {"id": str(self.program_a.pk)})
            foreign = client.get(reverse("registrar:program_detail"), {"id": str(self.program_b.pk)})
            garbage = client.get(reverse("registrar:program_detail"), {"id": "not-a-uuid"})
        self.assertEqual(own.status_code, 200)
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(garbage.status_code, 404)

    def test_programs_registry_rector_sees_all(self):
        _response, section = self.section(self.rector, "programs-registry", "programs_registry_section")
        self.assertEqual(section["total_count"], 2)

    # ── «Təşkilatın mövcud üzvləri» ─────────────────────────────────────────

    def test_member_filters_split_structure_and_group_and_are_scoped(self):
        _response, section = self.section(
            self.dean, "student-organization-management", "student_org_management_section"
        )
        fields = {field["name"]: field for field in section["filter_fields"]}
        self.assertEqual(fields["hm_unit"]["label"], "Struktur bölməsi")
        self.assertEqual(fields["hm_group"]["label"], "Qrup")
        self.assertEqual(fields["hm_group"]["options"][0]["label"], "Bütün qruplar")
        unit_labels = {option["label"] for option in fields["hm_unit"]["options"][1:]}
        group_labels = {option["label"] for option in fields["hm_group"]["options"][1:]}
        self.assertEqual(group_labels, {"ALFA-11"})
        self.assertIn("Alfa məktəbi", unit_labels)
        self.assertNotIn("ALFA-11", unit_labels)
        self.assertFalse(unit_labels & {"Beta məktəbi", "Kafedra B", "İxtisas B", "BETA-22"})
        # Dekan öz fakültəsinin tələbəsini görür (tələbə üzvlüyünün bölməsi boşdur), başqasını yox.
        usernames = {row["username"] for row in section["rows"]}
        self.assertIn("dsc_ali", usernames)
        self.assertNotIn("dsc_far", usernames)

    def test_member_group_filter_matches_students_and_ignores_foreign_group(self):
        _response, section = self.section(
            self.dean,
            "student-organization-management",
            "student_org_management_section",
            hm_group=str(self.group_a.pk),
        )
        self.assertEqual([row["username"] for row in section["rows"]], ["dsc_ali"])
        self.assertEqual(section["rows"][0]["unit_name"], "ALFA-11")
        _response, section = self.section(
            self.dean,
            "student-organization-management",
            "student_org_management_section",
            hm_group=str(self.group_b.pk),
        )
        usernames = {row["username"] for row in section["rows"]}
        self.assertNotIn("dsc_far", usernames)
        self.assertIn("dsc_ali", usernames)  # tanınmayan qrup süzgəci sadəcə tətbiq olunmur

    # ── «Fakültələr» + kafedra müdirinin tələbə kataloqu ────────────────────

    def test_faculties_section_hidden_for_chair_head_visible_for_dean(self):
        with bypass_rls():
            dean_page = self.client_for(self.dean).get(reverse("accounts:profile"), {"section": "org-faculties"})
            chair_page = self.client_for(self.chair_head).get(reverse("accounts:profile"))
            fragment = self.client_for(self.chair_head).get(
                reverse("accounts:profile_section_fragment", kwargs={"section": "org-faculties"})
            )
        self.assertIn("org-faculties", dean_page.context["allowed_sections"])
        self.assertNotIn("org-faculties", chair_page.context["allowed_sections"])
        self.assertIn("org-kafedras", chair_page.context["allowed_sections"])
        self.assertIn(fragment.status_code, (403, 404))

    def _student_usernames(self, user):
        role = Membership.objects.get(user=user, organization=self.org).role
        actor = PeopleActor(
            user=user, organization=self.org, permissions=frozenset(role.permissions or []), is_superadmin=False
        )
        with bypass_rls():
            records = scoped_student_records(actor)
            return set(records.values_list("student__username", flat=True)) if records is not None else set()

    def test_chair_head_sees_own_faculty_students_read_only(self):
        self.assertEqual(self._student_usernames(self.chair_head), {"dsc_ali"})
        self.assertEqual(self._student_usernames(self.dean), {"dsc_ali"})
        self.assertEqual(self._student_usernames(self.rector), {"dsc_ali", "dsc_far"})
        role = Membership.objects.get(user=self.chair_head, organization=self.org).role
        actor = PeopleActor(
            user=self.chair_head,
            organization=self.org,
            permissions=frozenset(role.permissions or []),
            is_superadmin=False,
        )
        # Genişlənmə YALNIZ tələbə kataloqunun oxusundadır — digər açarların əhatəsi kafedrada qalır.
        widened = actor.scope_for(PERM_VIEW_STUDENTS)
        self.assertEqual(set(widened.unit_ids), {self.fac_a.pk})
        from apps.organizations.public import get_permission_scope

        self.assertEqual(set(get_permission_scope(self.chair_head, self.org, "unit.view").unit_ids), {self.chair_a.pk})

    # ── Kafedra müdiri: OXU əhatəsi valideyn fakültəyə (qruplar, ixtisaslar, fənlər) ──

    def test_chair_head_groups_registry_sees_own_faculty_groups_only(self):
        response, section = self.section(self.chair_head, "groups-registry", "groups_registry_section")
        self.assertEqual([row["name"] for row in section["rows"]], ["ALFA-11"])
        self.assertEqual(self.kpi(section)["TƏLƏBƏ"], 1)
        self.assertEqual({row["label"] for row in section["faculty_options"]}, {"Alfa məktəbi"})
        self.assertEqual({row["label"] for row in section["specialty_options"]}, {"İxtisas A"})
        self.assertNotContains(response, "BETA-22")
        self.assertFalse(section["can_manage"])
        # Tələbə çekmecəsi: öz fakültəsinin qrupu açılır, başqasınınkı yox.
        client = self.client_for(self.chair_head)
        with bypass_rls():
            own = client.get(reverse("organizations:group_students", args=[self.org.slug, self.group_a.pk]))
            foreign = client.get(reverse("organizations:group_students", args=[self.org.slug, self.group_b.pk]))
        self.assertEqual(own.status_code, 200)
        self.assertEqual(foreign.status_code, 404)

    def test_chair_head_programs_registry_sees_own_faculty_programs(self):
        _response, section = self.section(self.chair_head, "programs-registry", "programs_registry_section")
        self.assertEqual([row["name"] for row in section["rows"]], ["Proqram Alfa"])
        self.assertEqual(section["total_count"], 1)

    def test_chair_head_subject_catalog_own_chair_plus_faculty_plans(self):
        _response, section = self.section(self.chair_head, "subject-catalog", "subject_catalog_section")
        self.assertEqual({row["code"] for row in section["rows"]}, {"DSC-A1", "DSC-B2", "DSC-B3"})
        self.assertNotIn("DSC-B1", {row["code"] for row in section["rows"]})
