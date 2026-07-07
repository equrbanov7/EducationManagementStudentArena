"""
Faza 2 / bənd 3 — rol-skoplu qrup görünüşü.

`_group_queryset_for_actor` mərkəzi unit-scoping servisini (`get_unit_scope`)
işlədir:
* org-geniş rol (owner/rektor/superadmin) → bütün qruplar;
* unit-scoped rol (dekan, scope_unit=fakültə) → yalnız öz alt-ağacındakı qruplar
  (+ öz müəllim olduğu qruplar);
* adi müəllim → yalnız öz qrupları.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.exams.models import StudentGroup
from apps.exams.views.teacher.groups import _group_queryset_for_actor
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()


class GroupUnitScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gus_owner", "gus_owner@test.az", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="Scoped Uni",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        # Fakültə A → Kafedra A1 (alt-ağac); ayrıca Fakültə B.
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə A")
        cls.chair_a1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra A1", parent=cls.faculty_a
        )
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə B")

        dean_role = cls.org.roles.get(name="dean")
        teacher_role = cls.org.roles.get(name="teacher")

        # Dekan A — fakültə A scope-u; heç bir qrupun müəllimi deyil.
        cls.dean_a = User.objects.create_user("gus_dean", "gus_dean@test.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.dean_a, organization=cls.org, role=dean_role, scope_unit=cls.faculty_a, is_primary=True
        )
        # Müəllim — bütün qrupların sahibi; struktur scope-u yoxdur.
        cls.teacher_x = User.objects.create_user("gus_teacher", "gus_teacher@test.az", "StrongPass123!")
        Membership.objects.create(user=cls.teacher_x, organization=cls.org, role=teacher_role, is_primary=True)
        # Başqa müəllim — heç bir qrupu yoxdur.
        cls.teacher_y = User.objects.create_user("gus_teacher_y", "gus_teacher_y@test.az", "StrongPass123!")
        Membership.objects.create(user=cls.teacher_y, organization=cls.org, role=teacher_role, is_primary=True)

        cls.group_in_a = StudentGroup.objects.create(
            teacher=cls.teacher_x, organization=cls.org, name="A1 qrup", org_unit=cls.chair_a1
        )
        cls.group_in_b = StudentGroup.objects.create(
            teacher=cls.teacher_x, organization=cls.org, name="B qrup", org_unit=cls.faculty_b
        )
        cls.group_no_unit = StudentGroup.objects.create(
            teacher=cls.teacher_x, organization=cls.org, name="Vahidsiz qrup"
        )

    def _visible(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return set(_group_queryset_for_actor(request, self.org).values_list("name", flat=True))

    def test_dean_sees_only_own_faculty_subtree(self):
        # Dekan A: fakültə A alt-ağacındakı qrup (kafedra A1) görünür; B və
        # vahidsiz qrup görünmür (dekan onların müəllimi deyil).
        visible = self._visible(self.dean_a)
        self.assertIn("A1 qrup", visible)
        self.assertNotIn("B qrup", visible)
        self.assertNotIn("Vahidsiz qrup", visible)

    def test_owner_sees_all_groups(self):
        self.assertEqual(self._visible(self.owner), {"A1 qrup", "B qrup", "Vahidsiz qrup"})

    def test_teacher_sees_only_own_groups(self):
        # teacher_x bütün qrupların müəllimidir → hamısını görür.
        self.assertEqual(self._visible(self.teacher_x), {"A1 qrup", "B qrup", "Vahidsiz qrup"})
        # teacher_y heç bir qrupun müəllimi deyil, scope-u yoxdur → heç nə görməz.
        self.assertEqual(self._visible(self.teacher_y), set())
