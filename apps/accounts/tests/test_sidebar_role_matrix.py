"""Rol × sidebar bölməsi matrisi (2026-07-31 auditi, Faza 5 + Faza 8).

Nəyi qoruyur
------------
``_role_capabilities`` bölmələri əsasən MÜSBƏT qaydalarla paylayır (org_admin →
bunlar, müəllim → bunlar…), lakin bir NEGATİV qayda var idi::

    if not (is_student or is_teacher or is_org_admin):
        allowed_sections.update({"courses", "assigned-exams", "assigned-courses", "groups"})

Yəni «sadalanmayan hər kəs» — HR, imtahan mərkəzi, dekan, kafedra müdiri, tyutor,
İKT rəhbəri — tələbə səthlərini (`assigned-exams` = «Mənə təyin edilmiş
imtahanlar`) və `groups` idarəetmə bölməsini alırdı. `groups` isə sidebar-da
**«Müəllim»** qrup başlığının şərtidir, ona görə HR-ın menyusunda «Müəllim»
bölməsi görünürdü.

Bu fayl matrisi TEST kimi sabitləyir: hər rol üçün gözlənilən bölmələr və —
daha vacibi — gözlənilməyənlər. Yeni rol və ya bölmə əlavə edəndə matris
yenilənməlidir; bu, qərarı görünən edir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

#: Rol adı → (səviyyə). Real konfiqurasiyadakı səviyyələr.
ROLE_LEVELS = {
    "org_admin": 80,
    "teacher": 60,
    "student": 10,
    "hr": 65,
    "exam_center": 85,
    "dean": 80,
    "department_head": 70,
    "tutor": 40,
    "member": 20,
    "ikt_rehber": 88,
}

#: TƏLƏBƏ səthləri — yalnız tələbədə olmalıdır.
STUDENT_ONLY = frozenset({"assigned-exams", "assigned-courses", "my-subjects", "my-transcript"})

#: İdarəetmə səthləri — adi üzv/tələbədə OLMAMALIDIR.
MANAGEMENT_ONLY = frozenset({"groups", "role-assignment", "manage-roles", "permission-editor"})


class SidebarRoleMatrixTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mx_owner", "mx_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Matrix Univ",
            slug="matrix-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.users = {}
        for name, level in ROLE_LEVELS.items():
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_system": False,
                    "is_active": True,
                },
            )
            user = User.objects.create_user(f"mx_{name}", f"mx_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.users[name] = user

    def _sections(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    # ── Tələbə səthləri sızmamalıdır ────────────────────────────────────────

    def test_staff_roles_do_not_get_student_surfaces(self):
        """«Mənə təyin edilmiş imtahanlar» əməkdaş menyusunda yeri yoxdur."""
        for role in ("hr", "exam_center", "dean", "department_head", "tutor", "ikt_rehber"):
            with self.subTest(role=role):
                leaked = self._sections(role) & STUDENT_ONLY
                self.assertEqual(leaked, set(), f"{role} tələbə bölməsi alır: {sorted(leaked)}")

    def test_student_keeps_its_own_surfaces(self):
        sections = self._sections("student")

        self.assertIn("assigned-exams", sections)
        self.assertIn("assigned-courses", sections)

    # ── İdarəetmə səthləri sızmamalıdır ─────────────────────────────────────

    def test_student_does_not_get_management_surfaces(self):
        leaked = self._sections("student") & MANAGEMENT_ONLY

        self.assertEqual(leaked, set(), f"tələbə idarəetmə bölməsi alır: {sorted(leaked)}")

    def test_member_keeps_group_navigation_but_no_role_management(self):
        """Adi üzvün `groups` görməsi QƏSDƏNDİR (mövcud davranış).

        `test_member_profile_shows_group_navigation` bunu sənədləşdirir: məktəb
        tipli təşkilatda adi üzv qrup naviqasiyasını görür. Auditin şikayəti
        üzvə deyil, ƏMƏKDAŞ rollarına (HR, imtahan mərkəzi, dekan, tyutor)
        aid idi — onlar üçün `groups` sidebar-da «Müəllim» başlığını açırdı.
        Rol/icazə idarəetməsi isə üzvdə olmamalıdır.
        """
        sections = self._sections("member")

        self.assertIn("groups", sections)
        self.assertNotIn("role-assignment", sections)
        self.assertNotIn("manage-roles", sections)
        self.assertNotIn("permission-editor", sections)

    def test_hr_does_not_get_the_teacher_group(self):
        """`groups` sidebar-da «Müəllim» qrup başlığının şərtidir.

        HR-ın işi kadr/üzvlükdür — qrup idarəetməsi deyil.
        """
        sections = self._sections("hr")

        self.assertNotIn("groups", sections)
        self.assertIn("role-assignment", sections)  # öz sahəsi qalır

    def test_hr_has_no_exam_or_course_surfaces(self):
        """Kod şərhi bunu vəd edir: «HR — … İmtahan/kurs YOXDUR»."""
        sections = self._sections("hr")

        self.assertNotIn("my-exams", sections)
        self.assertNotIn("my-courses", sections)

    # ── Hər rolun öz nüvəsi qalır (regressiya qapısı) ───────────────────────

    def test_each_role_keeps_its_core_sections(self):
        expected = {
            "org_admin": {"my-exams", "my-courses", "groups", "role-assignment", "manage-roles"},
            "teacher": {"my-exams", "my-courses", "groups", "pending-review", "review-results"},
            "exam_center": {"my-exams", "groups", "exam-center-pins", "exam-center-stats", "academic-records"},
            "student": {"assigned-exams", "assigned-courses", "my-results"},
            "hr": {"role-assignment", "manage-roles", "student-organization-management"},
        }
        for role, core in expected.items():
            with self.subTest(role=role):
                missing = core - self._sections(role)
                self.assertEqual(missing, set(), f"{role} öz bölməsini itirib: {sorted(missing)}")

    def test_everyone_keeps_the_common_sections(self):
        common = {"profile-info", "notifications", "edit-profile", "change-password"}
        for role in ROLE_LEVELS:
            with self.subTest(role=role):
                self.assertTrue(common <= self._sections(role), role)

    # ── Permission-əsaslı «Qruplar» görünürlüyü (2026-08) ───────────────────

    def test_group_permission_opens_groups_section(self):
        """`group.view` / `group.manage` icazəsi olan rol «Qruplar» bölməsini görür.

        Rol bayraqları (org_admin/teacher/exam_center/member) toxunulmazdır —
        bu, permission-editordan verilən açarın ƏLAVƏ qoludur.
        """
        # Tyutor default-da qrup bölməsini görmür.
        self.assertNotIn("groups", self._sections("tutor"))

        tutor_role = Role.objects.get(organization=self.org, name="tutor")
        tutor_role.permissions = ["group.view"]
        tutor_role.save(update_fields=["permissions", "updated_at"])
        self.assertIn("groups", self._sections("tutor"))

        # `group.manage` də bölməni açır (məs. yalnız idarə açarı verilibsə).
        tutor_role.permissions = ["group.manage"]
        tutor_role.save(update_fields=["permissions", "updated_at"])
        self.assertIn("groups", self._sections("tutor"))

    def test_role_flag_based_groups_visibility_is_preserved(self):
        """Mövcud qollar qalır: org_admin/teacher/exam_center/member `groups` görür."""
        for role in ("org_admin", "teacher", "exam_center", "member", "dean", "department_head"):
            with self.subTest(role=role):
                self.assertIn("groups", self._sections(role))


class SidebarGroupHeadingTest(TestCase):
    """Qrup başlığı boş qalmamalıdır.

    «Universitet idarəetməsi» başlığı şərtsiz render olunurdu — tələbə heç bir
    bənd olmayan idarəetmə başlığı görürdü.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sg_owner", "sg_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Group Univ",
            slug="group-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        student_role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="student",
            defaults={
                "display_name": "Student",
                "level": 10,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        cls.student = User.objects.create_user("sg_student", "sg_student@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=cls.student, organization=cls.org, role=student_role, is_primary=True, is_active=True
        )

    def _html(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_student_does_not_see_an_empty_management_heading(self):
        from django.utils.translation import pgettext

        heading = pgettext("profile.sidebar", "group_university_management")

        self.assertNotIn(heading, self._html(self.student))

    def test_owner_still_sees_the_management_heading(self):
        from django.utils.translation import pgettext

        heading = pgettext("profile.sidebar", "group_university_management")

        self.assertIn(heading, self._html(self.owner))
