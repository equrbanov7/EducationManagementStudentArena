"""FIX-A ikinci dalğa (QA 2026-10-17 baxışı) — HR tələbə məlumatına köhnə yollarla çatmır.

* «Struktur üzvləri» reyestri, «Üzv kartı» JSON-u, CSV ixracı — `resolve_members_access` YALNIZ-tələbə
  hesablarını tələbə tərəfi açarı olmayan aktordan (HR: `member.view` / `member.edit`) gizlədir.
* «Rol təyin et» / «Rolları idarə et» — siyahıda tələbə yoxdur, POST «tapılmadı» / «əhatədən kənar».
* RİM: gizli tələbə üçün səbəb kodu olmayan id ilə EYNİDİR (`target_not_found`) — orakul yoxdur.
* Qanuni rollar işləyir: İKT rəhbəri (`people.view_students`), Tədris şöbəsi əməkdaşı (`student.records_view`),
  öz fakültəsinin dekanı.
"""

from __future__ import annotations

from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.services.rim import RimAccessError, assert_can_manage
from apps.organizations.models import Membership
from apps.organizations.public import STUDENT_ACCOUNT_PERMISSIONS
from apps.organizations.structure_views.members import build_members_section
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role, make_user
from .test_fixa_2026_10_17 import FixAFixture, _Base, _client, _rim_actor

HR_FULL = [
    "unit.view",
    "member.view",
    "member.edit",
    "member.invite",
    "role.view",
    "role.assign",
    "user.search",
    "user.edit",
    "people.view_teachers",
]


class FixBFixture(FixAFixture):
    def _build_fixa(self):
        super()._build_fixa()
        org = self.org
        self.role_hr_full = make_role(org, "hr", level=65, scope_type=RoleScopeType.ORGANIZATION, permissions=HR_FULL)
        self.role_office_staff = make_role(
            org,
            "office_staff_fx",
            level=70,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["unit.view", "member.view", "student.records_view"],
        )
        self.role_ikt = make_role(
            org,
            "ikt_rehber",
            level=95,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["member.view", "member.edit", "role.assign", "people.view_students"],
        )
        self.role_dean_m = make_role(
            org,
            "dean_m_fx",
            level=80,
            scope_type=RoleScopeType.UNIT,
            permissions=["member.view", "member.edit", "people.view_students"],
        )
        self.hr_full = make_user("fxb_hr", first="Hüseyn", last="Kadrov")
        add_membership(org, self.hr_full, self.role_hr_full)
        self.office_staff = make_user("fxb_office", first="Ofelya", last="Tədrisova")
        add_membership(org, self.office_staff, self.role_office_staff)
        self.ikt = make_user("fxb_ikt", first="İlkin", last="Rəhbərov")
        add_membership(org, self.ikt, self.role_ikt)
        self.dean_m = make_user("fxb_dean", first="Dəniz", last="Dekanlı")
        add_membership(org, self.dean_m, self.role_dean_m, unit=self.faculty_a)
        # Qrupa bağlı tələbə üzvlüyü — dekanın (alt-ağac) reyestrində görünür.
        self.student_g = make_user("fxb_student_g", first="Günay", last="Qrupova")
        self.student_g_membership = add_membership(org, self.student_g, self.role_student, unit=self.group_a1)


class _BBase(_Base):
    @classmethod
    def setUpTestData(cls):
        cls.fx = FixBFixture()

    def members(self, user, role, **params):
        request = RequestFactory().get("/accounts/profile/", params)
        request.user = user
        request.organization = self.fx.org
        request.org_permissions = list(role.permissions)
        with bypass_rls():
            section = build_members_section(request, self.fx.org)
        self.assertTrue(section.get("has_access"), section)
        return {row["username"] for row in section["rows"]}, section


class MembersRegistryStudentPrivacyTest(_BBase):
    def test_hr_does_not_list_students(self):
        names, _section = self.members(self.fx.hr_full, self.fx.role_hr_full, om_kind="students")
        self.assertEqual(names, set())
        names, _section = self.members(self.fx.hr_full, self.fx.role_hr_full)
        self.assertIn(self.fx.teacher_a.username, names)
        self.assertNotIn(self.fx.student_a.username, names)
        self.assertNotIn(self.fx.student_g.username, names)

    def test_ikt_and_teaching_office_staff_still_list_students(self):
        for user, role in ((self.fx.ikt, self.fx.role_ikt), (self.fx.office_staff, self.fx.role_office_staff)):
            with self.subTest(role=role.name):
                names, _section = self.members(user, role, om_kind="students")
                self.assertIn(self.fx.student_a.username, names)

    def test_own_faculty_dean_lists_group_student(self):
        names, _section = self.members(self.fx.dean_m, self.fx.role_dean_m)
        self.assertIn(self.fx.student_g.username, names)

    def test_member_card_is_404_for_hr_and_200_for_legit_roles(self):
        def url(user):
            return reverse("organizations:structure_member_detail", args=[self.fx.org.slug, user.pk])

        response = self.get(self.fx.hr_full, url(self.fx.student_a))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.fx.student_a.email, response.content.decode())
        self.assertEqual(self.get(self.fx.hr_full, url(self.fx.teacher_a)).status_code, 200)
        self.assertEqual(
            self.get(self.fx.ikt, url(self.fx.student_a)).json()["person"]["email"], self.fx.student_a.email
        )
        self.assertEqual(self.get(self.fx.dean_m, url(self.fx.student_g)).status_code, 200)

    def test_csv_export_has_no_student_emails_for_hr(self):
        url = reverse("organizations:members_export", args=[self.fx.org.slug])
        response = self.get(self.fx.hr_full, url)
        self.assertEqual(response.status_code, 200)
        hr_csv = response.content.decode()
        self.assertIn(self.fx.teacher_a.email, hr_csv)
        self.assertNotIn(self.fx.student_a.email, hr_csv)
        ikt_csv = self.get(self.fx.ikt, url).content.decode()
        self.assertIn(self.fx.student_a.email, ikt_csv)


PROFILE_URL = "/accounts/profile/"


class RoleSectionsStudentPrivacyTest(_BBase):
    def section(self, user, name, key, **params):
        with bypass_rls():
            response = _client(user, self.fx.org).get(PROFILE_URL, {"section": name, **params})
        self.assertEqual(response.status_code, 200)
        return {row["data"]["username"] for row in response.context[key]["table_rows"]}

    def _check(self, name, key, param):
        student, teacher = self.fx.student_a.username, self.fx.teacher_a.username
        self.assertEqual(self.section(self.fx.hr_full, name, key, **{param: student}), set())
        self.assertEqual(self.section(self.fx.hr_full, name, key, **{param: teacher}), {teacher})
        self.assertEqual(self.section(self.fx.ikt, name, key, **{param: student}), {student})

    def test_role_assignment_hides_students_from_hr(self):
        self._check("role-assignment", "role_assignment_section", "ra_q")

    def test_manage_roles_hides_students_from_hr(self):
        self._check("manage-roles", "manage_roles_section", "mr_q")

    def _update_student_role(self, actor):
        with bypass_rls():
            membership = Membership.objects.get(organization=self.fx.org, user=self.fx.student_g)
            response = _client(actor, self.fx.org).post(
                reverse("accounts:role_assignment"),
                {
                    "action": "update_member",
                    "membership_id": str(membership.id),
                    "role_id": str(self.fx.role_teacher.id),
                },
                HTTP_ACCEPT="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            membership.refresh_from_db()
        return response, membership

    def test_hr_cannot_change_student_role(self):
        response, membership = self._update_student_role(self.fx.hr_full)
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(membership.role_id, self.fx.role_student.id)

    def test_ikt_can_change_student_role(self):
        _response, membership = self._update_student_role(self.fx.ikt)
        self.assertEqual(membership.role_id, self.fx.role_teacher.id)


class RimHiddenStudentOracleTest(_BBase):
    def test_hidden_student_reason_matches_missing_id(self):
        actor = _rim_actor(self.fx.hr, self.fx.org, self.fx.role_hr)
        with bypass_rls():
            with self.assertRaises(RimAccessError) as ctx:
                assert_can_manage(actor, self.fx.student_a)
        self.assertEqual((ctx.exception.reason_code, ctx.exception.status), ("target_not_found", 404))

    def test_rim_action_body_is_identical_for_hidden_student_and_missing_id(self):
        url = reverse("accounts:rim_action")

        def post(user_id):
            with bypass_rls():
                response = _client(self.fx.hr, self.fx.org).post(
                    url, {"action": "block", "user_id": str(user_id), "reason": "Yoxlama səbəbi — test"}
                )
            return response.status_code, response.json()

        self.assertEqual(post(self.fx.student_a.pk), post(987654321))

    def test_single_source_of_student_keys(self):
        from apps.accounts.services.rim.policy import STUDENT_ACCOUNT_PERMISSIONS as RIM_KEYS

        self.assertEqual(RIM_KEYS, STUDENT_ACCOUNT_PERMISSIONS)
        self.assertIn("student.records_view", STUDENT_ACCOUNT_PERMISSIONS)
