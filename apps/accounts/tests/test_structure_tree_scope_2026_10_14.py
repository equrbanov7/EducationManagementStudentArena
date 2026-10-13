"""«Struktur ağacı» əhatəsi + qrup paneli (starosta, tələbələr) — sahib 2026-10-14.

Sahib: «burda hər biri özünə aid olan qrupları görsün — fakültə başqa fakültənin qruplarını görməsin»;
«struktur ağacında qrup seçiləndə rəhbər yoxdursa təyin et yeri olmalıdır — vurub hansısa tələbəni seçmək
mümkün olsun ordan. Altda da həmin qrupun tələbələrini göstərmək də olar.»

Kilidlənən müqavilə (REAL rol şablonları ilə — tenant yaradılanda əkilən rollar):
* dekan yalnız ÖZ fakültəsinin alt-ağacını görür: ağac, KPI, tip legendası, axtarış, `st_unit` (kənar id →
  detal yox, ad sızmır); rektor hamısını görür; «Qruplar» reyestrinin fakültə/ixtisas süzgəci də əhatəlidir;
* qrup seçiləndə «Rəhbər» əvəzinə «Starosta» kartı; «Təyin et» yalnız `group_lead` endpoint-inin qapısından
  keçən aktora (tyutor / koordinator — `unit.group_manage`); seçici = qrupun QEYDİYYATLI tələbələri;
* tələbə siyahısı `people.view_students` əhatəsi ilə, e-poçt yalnız `people.view_contacts` ilə;
* qeyri-qrup vahidində köhnə «Rəhbər» UI qalır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import AcademicStatus, Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class StructureTreeScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sts_owner", "sts_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="STS Univ",
                slug="sts-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.fac_a, cls.spec_a, cls.group_a = cls._branch("A", "Alfa fakültəsi", "ALFA-101")
            cls.fac_b, cls.spec_b, cls.group_b = cls._branch("B", "Beta fakültəsi", "BETA-201")
            cls.program = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec_a, code="STSA", name="Proqram A"
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)

            cls.ali = cls._student("sts_ali", "Əli", "Abbasov", "7001", cls.group_a)
            cls.bina = cls._student("sts_bina", "Binə", "Bayramova", "7002", cls.group_a)
            cls.leave = cls._student(
                "sts_leave", "Dilarə", "Dadaşova", "7003", cls.group_a, status=AcademicStatus.ACADEMIC_LEAVE
            )
            cls.far = cls._student("sts_far", "Gülnar", "Qasımova", "8001", cls.group_b)

            cls.dean = cls._staff("sts_dean", "dean", cls.fac_a)
            cls.tutor = cls._staff("sts_tutor", "tutor", cls.spec_a)
            cls.coordinator = cls._staff("sts_coord", "program_coordinator", cls.spec_a)
            cls.office = cls._staff("sts_office", "teaching_office_head", None)
            cls.rector = cls._staff("sts_rector", "rector", None)

    @classmethod
    def _branch(cls, tag, faculty_name, group_name):
        faculty = OrgUnit.objects.create(
            organization=cls.org, name=faculty_name, slug=f"sts-fac-{tag}", unit_type=OrgUnitType.FACULTY
        )
        chair = OrgUnit.objects.create(
            organization=cls.org,
            parent=faculty,
            name=f"Kafedra {tag}",
            slug=f"sts-ch-{tag}",
            unit_type=OrgUnitType.CHAIR,
        )
        specialty = OrgUnit.objects.create(
            organization=cls.org,
            parent=chair,
            name=f"İxtisas {tag}",
            slug=f"sts-sp-{tag}",
            unit_type=OrgUnitType.SPECIALTY,
        )
        group = OrgUnit.objects.create(
            organization=cls.org, parent=specialty, name=group_name, slug=f"sts-g-{tag}", unit_type=OrgUnitType.GROUP
        )
        return faculty, specialty, group

    @classmethod
    def _student(cls, username, first, last, number, group, *, status=AcademicStatus.ENROLLED):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(organization=cls.org, institutional_identifier=number)
        Membership.objects.create(
            user=user, organization=cls.org, role=Role.objects.get(organization=cls.org, name="student"), is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2026,
            status=status,
        )
        return user

    @classmethod
    def _staff(cls, username, role_name, unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=username)
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

    def tree(self, user, **params):
        response = self.client_for(user).get(reverse("accounts:profile"), {"section": "org-structure-tree", **params})
        self.assertEqual(response.status_code, 200)
        return response, response.context["structure_tree_section"]

    @staticmethod
    def _labels(nodes):
        out = []
        for node in nodes:
            out.append(node["label"])
            out.extend(StructureTreeScopeTest._labels(node["children"]))
        return out

    def record(self, user):
        return StudentAcademicRecord.objects.get(organization=self.org, student=user)

    # ── (b) əhatə ───────────────────────────────────────────────────────────

    def test_dean_tree_counters_and_legend_cover_only_own_faculty(self):
        response, section = self.tree(self.dean)
        labels = self._labels(section["tree_nodes"])
        self.assertIn("ALFA-101", labels)
        self.assertNotIn("BETA-201", labels)
        self.assertNotIn("Beta fakültəsi", labels)
        self.assertEqual(section["unit_total"], 4)
        kpi = {tile["label"]: tile["value"] for tile in section["kpi_tiles"]}
        self.assertEqual(kpi.get("FAKÜLTƏ"), 1)
        legend = {item["code"]: item["count"] for item in section["type_legend"]}
        self.assertEqual(legend.get(OrgUnitType.GROUP), 1)
        self.assertNotContains(response, "BETA-201")

    def test_dean_search_does_not_find_foreign_group(self):
        _response, section = self.tree(self.dean, st_q="BETA")
        self.assertEqual(section["unit_total"], 0)
        _response, section = self.tree(self.dean, st_q="ALFA")
        self.assertIn("ALFA-101", self._labels(section["tree_nodes"]))

    def test_foreign_st_unit_is_not_disclosed(self):
        response, section = self.tree(self.dean, st_unit=str(self.group_b.pk))
        self.assertIsNone(section["detail"])
        self.assertEqual(section["selected_unit_id"], "")
        self.assertNotContains(response, "BETA-201")
        fragment = self.client_for(self.dean).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "org-structure-tree"}),
            {"st_unit": str(self.group_b.pk)},
        )
        self.assertEqual(fragment.status_code, 200)
        self.assertNotIn("BETA-201", fragment.content.decode())
        self.assertNotIn("Gülnar", fragment.content.decode())

    def test_rector_sees_both_faculties(self):
        _response, section = self.tree(self.rector)
        labels = self._labels(section["tree_nodes"])
        self.assertIn("ALFA-101", labels)
        self.assertIn("BETA-201", labels)

    def test_groups_registry_filter_options_are_scoped(self):
        response = self.client_for(self.dean).get(reverse("accounts:profile"), {"section": "groups-registry"})
        self.assertEqual(response.status_code, 200)
        section = response.context["groups_registry_section"]
        faculties = {row["label"] for row in section["faculty_options"]}
        specialties = {row["label"] for row in section["specialty_options"]}
        self.assertEqual(faculties, {"Alfa fakültəsi"})
        self.assertEqual(specialties, {"İxtisas A"})
        # İxtisas əhatəli tyutor öz fakültəsini (əcdad) süzgəcdə seçə bilir, başqasını yox.
        response = self.client_for(self.tutor).get(reverse("accounts:profile"), {"section": "groups-registry"})
        section = response.context["groups_registry_section"]
        self.assertEqual({row["label"] for row in section["faculty_options"]}, {"Alfa fakültəsi"})
        self.assertTrue(section["can_assign_lead"])

    # ── (c) qrup paneli ─────────────────────────────────────────────────────

    def test_tutor_group_panel_offers_enrolled_students_only(self):
        response, section = self.tree(self.tutor, st_unit=str(self.group_a.pk))
        panel = section["detail"]["group_panel"]
        self.assertTrue(section["detail"]["is_group"])
        self.assertTrue(panel["can_assign_lead"])
        self.assertIsNone(panel["lead"])
        offered = {row["value"] for row in panel["lead_options"]}
        self.assertEqual(offered, {str(self.record(self.ali).pk), str(self.record(self.bina).pk)})
        self.assertContains(response, 'data-tof-open="tofTreeLeadDialog"')
        self.assertContains(response, 'id="tofTreeLeadDialog"')
        self.assertNotContains(response, 'data-tof-open="tofHeadDialog"')
        self.assertContains(response, "7001")

    def test_coordinator_assigns_starosta_from_tree_and_panel_shows_it(self):
        response = self.client_for(self.coordinator).post(
            reverse("accounts:group_lead_action"),
            {"action": "assign", "group_id": str(self.group_a.pk), "record_id": str(self.record(self.ali).pk)},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org, user=self.ali, role__name="lead_student", scope_unit=self.group_a, is_active=True
            ).exists()
        )
        for actor in (self.coordinator, self.tutor):
            _response, section = self.tree(actor, st_unit=str(self.group_a.pk))
            panel = section["detail"]["group_panel"]
            self.assertEqual(panel["lead"]["username"], "sts_ali")
            self.assertNotIn(str(self.record(self.ali).pk), {row["value"] for row in panel["lead_options"]})
        response, _section = self.tree(self.tutor, st_unit=str(self.group_a.pk))
        self.assertContains(response, 'id="tofTreeLeadRemoveDialog"')
        # Tyutor da götürə bilir (eyni endpoint, eyni açar).
        removed = self.client_for(self.tutor).post(
            reverse("accounts:group_lead_action"), {"action": "remove", "group_id": str(self.group_a.pk)}
        )
        self.assertEqual(removed.status_code, 200, removed.content)

    def test_tutor_cannot_assign_in_foreign_group(self):
        response = self.client_for(self.tutor).post(
            reverse("accounts:group_lead_action"),
            {"action": "assign", "group_id": str(self.group_b.pk), "record_id": str(self.record(self.far).pk)},
        )
        self.assertEqual(response.status_code, 404)

    def test_dean_sees_students_with_contacts_but_cannot_assign(self):
        response, section = self.tree(self.dean, st_unit=str(self.group_a.pk))
        panel = section["detail"]["group_panel"]
        self.assertFalse(panel["can_assign_lead"])
        self.assertEqual(panel["lead_options"], [])
        self.assertTrue(panel["can_view_students"])
        self.assertTrue(panel["show_contacts"])
        self.assertEqual(panel["student_total"], 3)
        self.assertContains(response, "sts_ali@qku.edu.az")
        self.assertNotContains(response, 'id="tofTreeLeadDialog"')

    def test_tutor_sees_students_without_contacts(self):
        response, section = self.tree(self.tutor, st_unit=str(self.group_a.pk))
        panel = section["detail"]["group_panel"]
        self.assertTrue(panel["can_view_students"])
        self.assertFalse(panel["show_contacts"])
        self.assertNotContains(response, "sts_ali@qku.edu.az")

    def test_office_without_student_key_gets_no_student_list(self):
        response, section = self.tree(self.office, st_unit=str(self.group_a.pk))
        panel = section["detail"]["group_panel"]
        self.assertFalse(panel["can_view_students"])
        self.assertEqual(panel["students"], [])
        # Qrup idarəçisi (`unit.group_manage`) starostanı təyin edə bilir — seçicidə yalnız adlar.
        self.assertTrue(panel["can_assign_lead"])
        self.assertNotContains(response, "tof-st-students__list")

    def test_non_group_unit_keeps_head_ui(self):
        response, section = self.tree(self.rector, st_unit=str(self.fac_a.pk))
        self.assertFalse(section["detail"]["is_group"])
        self.assertNotIn("group_panel", section["detail"])
        self.assertContains(response, 'data-tof-open="tofHeadDialog"')
        self.assertNotContains(response, 'id="tofTreeLeadDialog"')
