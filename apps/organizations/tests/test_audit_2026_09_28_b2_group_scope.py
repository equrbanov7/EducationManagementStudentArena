"""Audit 2026-09-28 B2 — qrup reyestrinin yazı əhatəsi (S3 / S4).

* **S3** «Tələbə əlavə et» namizədləri və ``add_students`` yalnız aktorun
  ``unit.group_manage`` əhatəsindəki (ixtisası / arxiv qrupu əhatədə olan)
  qrupsuz tələbələrlə məhdudlaşır — başqa fakültənin tələbəsi görünmür və
  birbaşa POST ilə də əlavə edilmir.
* **S4** yazı əməlləri ``unit.view`` deyil, ``unit.group_manage`` əhatəsi ilə
  həll olunur: baxışı bütün təşkilat, idarəsi bir fakültə olan aktor başqa
  fakültənin qrupunu redaktə edə bilmir (404), çekmecədə ``can_manage`` yalan.
"""

from django.contrib.auth import get_user_model

from apps.accounts.tests.test_groups_registry_add_students import _AddStudentsBase
from apps.organizations.models import Membership, OrgUnit, Role
from apps.registrar.models import Program, StudentAcademicRecord
from core.constants import OrgUnitType, RoleScopeType

from ..groups_registry import student_record_scope_q
from ..scoping import EMPTY_SCOPE, ORG_WIDE_SCOPE

User = get_user_model()

PASSWORD = "StrongPass123!"


class _ScopeBase(_AddStudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # İkinci fakültə: öz ixtisası, qrupu və QRUPSUZ tələbəsi.
        cls.faculty2 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Humanitar", slug="b2-fak2"
        )
        cls.chair2 = OrgUnit.objects.create(
            organization=cls.org, parent=cls.faculty2, unit_type=OrgUnitType.CHAIR, name="Tarix", slug="b2-kaf2"
        )
        cls.specialty2 = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.chair2,
            unit_type=OrgUnitType.SPECIALTY,
            name="Tarix ixtisası",
            slug="b2-ixt2",
        )
        cls.group_far = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty2,
            unit_type=OrgUnitType.GROUP,
            name="B2 TAR-24",
            slug="b2-tar-24",
            code="TAR-24",
            settings={"language_sector": "AZ", "course_year": 1, "admission_year": 2024},
        )
        cls.program2 = Program.objects.create(
            organization=cls.org,
            code="B2-TAR",
            official_code="6010100",
            name="B2 Tarix",
            specialty_unit=cls.specialty2,
        )
        from apps.registrar.models import Curriculum

        plan2 = Curriculum.objects.create(
            organization=cls.org, program=cls.program2, admission_year=2026, name="B2 plan", version=1
        )
        far_user = User.objects.create_user("b2_far_free", "b2_far_free@qku.edu.az", PASSWORD)
        far_user.first_name, far_user.last_name = "Uzaq", "Fakültəli"
        far_user.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=far_user, organization=cls.org, role=cls.roles["teacher"], is_primary=True, is_active=True
        )
        cls.far_free = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=far_user,
            program=cls.program2,
            curriculum=plan2,
            group=None,
            admission_year=2026,
        )

        # S3: birinci fakültənin qrup meneceri (UNIT əhatəli).
        manager_role = Role.objects.create(
            organization=cls.org,
            name="b2_faculty_group_manager",
            display_name="B2 fakültə qrup meneceri",
            level=72,
            scope_type=RoleScopeType.UNIT,
            permissions=["unit.view", "unit.group_manage"],
            is_active=True,
        )
        cls.users["faculty_manager"] = cls._member("b2_fac_mgr", manager_role, cls.faculty)

        # S4: baxış bütün təşkilat, idarə yalnız İKİNCİ fakültə.
        viewer_role = Role.objects.create(
            organization=cls.org,
            name="b2_org_viewer",
            display_name="B2 təşkilat baxışı",
            level=60,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["unit.view"],
            is_active=True,
        )
        far_manager_role = Role.objects.create(
            organization=cls.org,
            name="b2_far_manager",
            display_name="B2 uzaq fakültə meneceri",
            level=61,
            scope_type=RoleScopeType.UNIT,
            permissions=["unit.view", "unit.group_manage"],
            is_active=True,
        )
        split_user = cls._member("b2_split", viewer_role, None)
        Membership.objects.create(
            user=split_user,
            organization=cls.org,
            role=far_manager_role,
            scope_unit=cls.faculty2,
            is_primary=False,
            is_active=True,
        )
        cls.users["split_actor"] = split_user

    @classmethod
    def _member(cls, username, role, scope_unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=user, organization=cls.org, role=role, scope_unit=scope_unit, is_primary=True, is_active=True
        )
        return user


class CandidateScopeTest(_ScopeBase):
    def test_candidates_are_limited_to_manage_scope(self):
        response = self._client("faculty_manager").get(self._candidates_url(), {"limit": 50})
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertTrue({str(record.pk) for record in self.free} <= ids)
        self.assertNotIn(str(self.far_free.pk), ids)

    def test_org_wide_manager_still_sees_every_faculty(self):
        response = self._client("teaching_office_head").get(self._candidates_url(), {"limit": 50})
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(str(self.far_free.pk), ids)

    def test_out_of_scope_student_cannot_be_added_by_direct_post(self):
        response = self._action(
            "faculty_manager",
            {"action": "add_students", "id": str(self.group.pk), "record_ids": [str(self.far_free.pk)]},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "no_candidates")
        self.far_free.refresh_from_db()
        self.assertIsNone(self.far_free.group_id)

    def test_scope_q_helper_is_fail_closed(self):
        self.assertEqual(
            StudentAcademicRecord.objects.filter(organization=self.org)
            .filter(student_record_scope_q(EMPTY_SCOPE))
            .count(),
            0,
        )
        self.assertEqual(
            StudentAcademicRecord.objects.filter(organization=self.org)
            .filter(student_record_scope_q(ORG_WIDE_SCOPE))
            .count(),
            StudentAcademicRecord.objects.filter(organization=self.org).count(),
        )


class WriteScopeTest(_ScopeBase):
    def test_view_scope_does_not_grant_write_outside_manage_scope(self):
        response = self._action(
            "split_actor", {"action": "save_group", "id": str(self.group.pk), "name": "Oğurlanmış ad"}
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.name, "Oğurlanmış ad")

    def test_write_inside_manage_scope_is_allowed(self):
        response = self._action(
            "split_actor", {"action": "save_group", "id": str(self.group_far.pk), "name": "B2 TAR-24 yeni"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.group_far.refresh_from_db()
        self.assertEqual(self.group_far.name, "B2 TAR-24 yeni")

    def test_drawer_reads_but_hides_manage_buttons_outside_manage_scope(self):
        body = self._client("split_actor").get(self._students_url()).json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["can_manage"])
        far = self._client("split_actor").get(self._students_url(self.group_far)).json()
        self.assertTrue(far["can_manage"])

    def test_candidates_endpoint_uses_manage_scope(self):
        response = self._client("split_actor").get(self._candidates_url())
        self.assertEqual(response.status_code, 404, response.content)


class SplitKeepsTeacherTest(_ScopeBase):
    """Audit 2026-09-28 S2: bölgüdən sonra alt qrup jurnalı müəllimsiz qalmır."""

    def test_subgroup_offering_inherits_instructor_and_hours(self):
        import json

        from apps.registrar.models import CourseOffering, Enrollment

        CourseOffering.objects.filter(pk=self.offering.pk).update(lesson_hours=60)
        a, b, _c = self.students
        for record in (a, b):
            Enrollment.objects.create(organization=self.org, student=record.student, offering=self.offering)
        payload = {
            "action": "split_group",
            "id": str(self.group.pk),
            "reason": "Laboratoriya dərsləri üçün alt qruplara bölünür.",
            "subgroups": json.dumps(
                [
                    {"name": "B2 KE-24-1", "record_ids": [str(a.pk)]},
                    {"name": "B2 KE-24-2", "record_ids": [str(b.pk)]},
                ]
            ),
        }
        response = self._action("teaching_office_head", payload)
        self.assertEqual(response.status_code, 200, response.content)
        for name in ("B2 KE-24-1", "B2 KE-24-2"):
            offering = CourseOffering.objects.get(organization=self.org, group__name=name, subject=self.subject)
            self.assertEqual(offering.instructor_id, self.users["teacher"].pk)
            self.assertEqual(offering.lesson_hours, 60)
