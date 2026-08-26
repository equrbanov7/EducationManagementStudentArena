"""
Unit scoping və yeni universitet idarəetmə rolları üçün testlər.

Yoxlanılan ssenarilər:
* Yeni university təşkilatında exam_center / hr / lead_student rolları yaranır.
* exam_center yüksək level-ə (85) baxmayaraq org_admin aliası ALMIR.
* HR org_admin aliası almır.
* Dekan (scope_unit ilə) yalnız öz fakültə alt-ağacındakı üzvləri görür.
* Rektor (org-wide) bütün üzvləri görür.
* Adi tələbə struktur səhifəsinə girə bilmir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from core.constants import OrganizationType, OrgUnitType

from ..models import Membership, Organization, OrgUnit
from ..scoping import get_permission_scope, get_unit_scope

User = get_user_model()


def _login(client, username, password="StrongPass123!"):
    assert client.login(username=username, password=password)


class UniversityDefaultRolesTest(TestCase):
    """Yeni rollar university default şablonlarına daxildir."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rektor_owner", "owner@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Test University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )

    def test_new_management_roles_created(self):
        role_names = set(self.org.roles.values_list("name", flat=True))
        self.assertIn("exam_center", role_names)
        self.assertIn("hr", role_names)
        self.assertIn("lead_student", role_names)

    def test_exam_center_role_has_exam_but_not_member_manage(self):
        role = self.org.roles.get(name="exam_center")
        self.assertIn("exam.*", role.permissions)
        self.assertIn("appeal.respond", role.permissions)
        self.assertIn("appeal.decide", role.permissions)
        self.assertNotIn("member.invite", role.permissions)
        self.assertNotIn("member.remove", role.permissions)
        self.assertNotIn("role.assign", role.permissions)

    def test_teacher_role_does_not_receive_appeal_decision_permissions(self):
        role = self.org.roles.get(name="teacher")
        self.assertNotIn("appeal.respond", role.permissions)
        self.assertNotIn("appeal.decide", role.permissions)

    def test_hr_role_has_member_manage_but_not_exams(self):
        role = self.org.roles.get(name="hr")
        self.assertIn("member.invite", role.permissions)
        self.assertIn("role.assign", role.permissions)
        self.assertNotIn("exam.*", role.permissions)
        self.assertNotIn("exam.create", role.permissions)

    def test_exam_center_not_admin_alias(self):
        aliases = ProfileRole.aliases_for_membership_role("exam_center", level=85)
        self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)
        self.assertIn("exam_center", aliases)

    def test_hr_not_admin_alias(self):
        aliases = ProfileRole.aliases_for_membership_role("hr", level=65)
        self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)

    def test_dean_still_admin_alias(self):
        aliases = ProfileRole.aliases_for_membership_role("dean", level=80)
        self.assertIn(ProfileRole.ORG_ADMIN, aliases)

    def test_approval_chain_permissions_are_gone(self):
        """Təsdiq zənciri ləğv olundu — «approve_chair/final» açarları yoxdur."""
        role = self.org.roles.get(name="chair_head")
        self.assertNotIn("grade.approve_chair", role.permissions)
        self.assertNotIn("grade.approve_final", role.permissions)

    def test_rim_role_carries_journal_close_permission(self):
        """Jurnalı semestr sonunda RİM bağlayır (`journal.close`)."""
        role = self.org.roles.get(name="ikt_rehber")
        self.assertIn("journal.close", role.permissions)


class UnitScopingTest(TestCase):
    """Dekan/kafedra müdürü unit scope-u və view scoping-i."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("uni_owner", "uni@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Scoped University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )

        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə A")
        cls.chair_a1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra A1", parent=cls.faculty_a
        )
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə B")

        dean_role = cls.org.roles.get(name="dean")
        student_role = cls.org.roles.get(name="student")

        cls.dean_a = User.objects.create_user("dean_a", "dean_a@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.dean_a, organization=cls.org, role=dean_role, scope_unit=cls.faculty_a, is_primary=True
        )

        # Tələbələr: biri A fakültəsində (kafedra A1), biri B fakültəsində.
        cls.student_a = User.objects.create_user("student_a", "sa@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_a, organization=cls.org, role=student_role, scope_unit=cls.chair_a1, is_primary=True
        )
        cls.student_b = User.objects.create_user("student_b", "sb@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_b, organization=cls.org, role=student_role, scope_unit=cls.faculty_b, is_primary=True
        )

    def test_dean_scope_is_unit_scoped_subtree(self):
        scope = get_unit_scope(self.dean_a, self.org)
        self.assertTrue(scope.is_unit_scoped)
        self.assertIn(self.faculty_a.pk, scope.unit_ids)

        from ..scoping import scope_org_units

        visible_units = set(scope_org_units(OrgUnit.objects.filter(organization=self.org), scope))
        self.assertIn(self.faculty_a, visible_units)
        self.assertIn(self.chair_a1, visible_units)  # alt-ağac daxildir
        self.assertNotIn(self.faculty_b, visible_units)

    def test_permission_scope_ignores_unrelated_membership_unit(self):
        unscoped_chair = User.objects.create_user("unscoped_chair", "uc@test.az", "StrongPass123!")
        # Rola jurnal-bağlama açarı verilir, amma üzvlüyün `scope_unit`-i YOXDUR →
        # başqa (tələbə) üzvlüyün uniti ona borc verilməməlidir (fail-closed).
        chair_role = self.org.roles.get(name="chair_head")
        chair_role.permissions = list(chair_role.permissions or []) + ["journal.close"]
        chair_role.save(update_fields=["permissions"])
        Membership.objects.create(
            user=unscoped_chair,
            organization=self.org,
            role=chair_role,
        )
        Membership.objects.create(
            user=unscoped_chair,
            organization=self.org,
            role=self.org.roles.get(name="student"),
            scope_unit=self.faculty_a,
        )

        scope = get_permission_scope(unscoped_chair, self.org, "journal.close")
        self.assertFalse(scope.has_structure_access)

    def test_owner_scope_is_org_wide(self):
        scope = get_unit_scope(self.owner, self.org)
        self.assertTrue(scope.is_org_wide)

    def test_dean_members_page_scoped_to_own_faculty(self):
        client = Client()
        _login(client, "dean_a")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("organizations:members", kwargs={"slug": self.org.slug}))
        self.assertEqual(response.status_code, 200)
        members = list(response.context["members"])
        member_users = {m.user_id for m in members}
        self.assertIn(self.student_a.id, member_users)
        self.assertNotIn(self.student_b.id, member_users)
        # Dekanın özü scope_unit=faculty_a üzvlüyü ilə görünür.
        self.assertIn(self.dean_a.id, member_users)

    def test_owner_members_page_sees_all(self):
        client = Client()
        _login(client, "uni_owner")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("organizations:members", kwargs={"slug": self.org.slug}))
        self.assertEqual(response.status_code, 200)
        member_users = {m.user_id for m in response.context["members"]}
        self.assertIn(self.student_a.id, member_users)
        self.assertIn(self.student_b.id, member_users)

    def test_student_cannot_open_structure_page(self):
        client = Client()
        _login(client, "student_a")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("organizations:structure", kwargs={"slug": self.org.slug}))
        # Adi tələbə struktur idarəetmə səhifəsini görməməlidir → redirect.
        self.assertEqual(response.status_code, 302)

    def test_dean_structure_page_scoped(self):
        client = Client()
        _login(client, "dean_a")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("organizations:structure", kwargs={"slug": self.org.slug}))
        self.assertEqual(response.status_code, 200)
        units = list(response.context["units"])
        self.assertEqual([self.faculty_a], units)


class TutorRoleTest(TestCase):
    """Tyutor rolu: default şablon, scoped üzv görünüşü, idarəetmə yoxdur."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tutor_uni_owner", "tuni@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Tutor University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )
        cls.faculty = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə T")
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə Y"
        )

        tutor_role = cls.org.roles.get(name="tutor")
        student_role = cls.org.roles.get(name="student")

        cls.tutor = User.objects.create_user("tutor_user", "tutor@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.tutor, organization=cls.org, role=tutor_role, scope_unit=cls.faculty, is_primary=True
        )
        cls.student_in = User.objects.create_user("t_student_in", "tsi@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_in, organization=cls.org, role=student_role, scope_unit=cls.faculty, is_primary=True
        )
        cls.student_out = User.objects.create_user("t_student_out", "tso@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_out,
            organization=cls.org,
            role=student_role,
            scope_unit=cls.other_faculty,
            is_primary=True,
        )

    def test_tutor_role_template(self):
        role = self.org.roles.get(name="tutor")
        self.assertEqual(role.level, 40)
        self.assertEqual(role.scope_type, "unit")
        self.assertIn("member.view", role.permissions)
        self.assertIn("analytics.view_unit", role.permissions)
        # İdarəetmə icazələri olmamalıdır:
        self.assertNotIn("exam.create", role.permissions)
        self.assertNotIn("member.invite", role.permissions)
        self.assertNotIn("grade.input", role.permissions)

    def test_tutor_not_admin_or_teacher_alias(self):
        aliases = ProfileRole.aliases_for_membership_role("tutor", level=40)
        self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)
        self.assertNotIn(ProfileRole.TEACHER, aliases)
        self.assertIn("tutor", aliases)

    def test_tutor_scope_is_unit_scoped(self):
        scope = get_unit_scope(self.tutor, self.org)
        self.assertTrue(scope.is_unit_scoped)
        self.assertIn(self.faculty.pk, scope.unit_ids)

    def test_tutor_members_page_scoped(self):
        client = Client()
        _login(client, "tutor_user")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("organizations:members", kwargs={"slug": self.org.slug}))
        self.assertEqual(response.status_code, 200)
        member_users = {m.user_id for m in response.context["members"]}
        self.assertIn(self.student_in.id, member_users)
        self.assertNotIn(self.student_out.id, member_users)


class UnitScopedStatisticsTest(TestCase):
    """get_org_admin_statistics scoped_unit_ids parametri ilə yalnız alt-ağac datasını sayır."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("stats_owner", "so@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Stats University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə SA")
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə SB")

        student_role = cls.org.roles.get(name="student")
        for index, faculty in enumerate([cls.faculty_a, cls.faculty_a, cls.faculty_b]):
            student = User.objects.create_user(f"stats_student_{index}", f"ss{index}@test.az", "StrongPass123!")
            Membership.objects.create(
                user=student, organization=cls.org, role=student_role, scope_unit=faculty, is_primary=True
            )

    def test_member_counts_scoped_to_unit(self):
        from apps.accounts.services.statistics_selectors import get_org_admin_statistics

        org_wide = get_org_admin_statistics(organization=self.org)
        scoped = get_org_admin_statistics(organization=self.org, scoped_unit_ids=[self.faculty_a.pk])

        self.assertEqual(org_wide["summary"]["student_count"], 3)
        self.assertEqual(scoped["summary"]["student_count"], 2)
        self.assertLess(scoped["summary"]["total_members"], org_wide["summary"]["total_members"])


class UnitScopedStudentManagementSectionTest(TestCase):
    """student-organization-management bölməsi dekan üçün unit-scoped olmalıdır."""

    @classmethod
    def setUpTestData(cls):
        from django.test import RequestFactory

        cls.factory = RequestFactory()
        cls.owner = User.objects.create_user("mgmt_owner", "mo@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Mgmt University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə MA")
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə MB")

        dean_role = cls.org.roles.get(name="dean")
        student_role = cls.org.roles.get(name="student")

        cls.dean = User.objects.create_user("mgmt_dean", "md@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.dean, organization=cls.org, role=dean_role, scope_unit=cls.faculty_a, is_primary=True
        )
        cls.student_a = User.objects.create_user("mgmt_student_a", "msa@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_a, organization=cls.org, role=student_role, scope_unit=cls.faculty_a, is_primary=True
        )
        cls.student_b = User.objects.create_user("mgmt_student_b", "msb@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.student_b, organization=cls.org, role=student_role, scope_unit=cls.faculty_b, is_primary=True
        )

    def _build_section(self, user, user_level):
        from apps.accounts.views._helpers.org_sections import _build_student_org_management_section

        request = self.factory.get("/profile/", {"section": "student-organization-management"})
        request.user = user
        return _build_student_org_management_section(
            request=request,
            organization=self.org,
            is_superadmin=False,
            user_level=user_level,
        )

    def test_dean_sees_only_own_faculty_students(self):
        section = self._build_section(self.dean, user_level=90)
        self.assertTrue(section.get("unit_scope_active"))
        student_user_ids = {profile.user_id for profile in section["students"]}
        self.assertIn(self.student_a.id, student_user_ids)
        self.assertNotIn(self.student_b.id, student_user_ids)
        # Org-səviyyəli intake siyahıları dekan üçün boşdur.
        self.assertEqual(section["pending_requested_students_total_count"], 0)
        self.assertEqual(section["unassigned_students_total_count"], 0)

    def test_owner_sees_all_students(self):
        section = self._build_section(self.owner, user_level=100)
        self.assertFalse(section.get("unit_scope_active"))
        student_user_ids = {profile.user_id for profile in section["students"]}
        self.assertIn(self.student_a.id, student_user_ids)
        self.assertIn(self.student_b.id, student_user_ids)


class UnitExamsSectionTest(TestCase):
    """Faza 3: dekan üçün 'unit-exams' bölməsi — yalnız öz alt-ağacının imtahanları."""

    @classmethod
    def setUpTestData(cls):
        from apps.exams.models import Exam

        cls.owner = User.objects.create_user("ue_owner", "ueo@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="UnitExam University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
        )
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə UA")
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə UB")

        dean_role = cls.org.roles.get(name="dean")
        teacher_role = cls.org.roles.get(name="teacher")

        cls.dean = User.objects.create_user("ue_dean", "ued@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.dean, organization=cls.org, role=dean_role, scope_unit=cls.faculty_a, is_primary=True
        )
        cls.teacher_a = User.objects.create_user("ue_teacher_a", "ueta@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.teacher_a, organization=cls.org, role=teacher_role, scope_unit=cls.faculty_a, is_primary=True
        )
        cls.teacher_b = User.objects.create_user("ue_teacher_b", "uetb@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.teacher_b, organization=cls.org, role=teacher_role, scope_unit=cls.faculty_b, is_primary=True
        )

        cls.exam_a = Exam.objects.create(title="Fakültə A imtahanı", author=cls.teacher_a, organization=cls.org)
        cls.exam_b = Exam.objects.create(title="Fakültə B imtahanı", author=cls.teacher_b, organization=cls.org)

    def test_dean_unit_exams_section_scoped(self):
        client = Client()
        _login(client, "ue_dean")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("accounts:profile"), {"section": "unit-exams"})
        self.assertEqual(response.status_code, 200)
        page_obj = response.context.get("unit_exams_page_obj")
        self.assertIsNotNone(page_obj)
        exam_ids = {exam.id for exam in page_obj.object_list}
        self.assertIn(self.exam_a.id, exam_ids)
        self.assertNotIn(self.exam_b.id, exam_ids)

    def test_student_cannot_access_unit_exams_section(self):
        student_role = self.org.roles.get(name="student")
        student = User.objects.create_user("ue_student", "ues@test.az", "StrongPass123!")
        Membership.objects.create(
            user=student, organization=self.org, role=student_role, scope_unit=self.faculty_a, is_primary=True
        )
        client = Client()
        _login(client, "ue_student")
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("accounts:profile"), {"section": "unit-exams"})
        # Bölmə icazəli deyil → unit_exams konteksti boş qalmalıdır.
        self.assertIsNone(response.context.get("unit_exams_page_obj"))
        self.assertNotIn("unit-exams", response.context.get("allowed_sections", set()))
