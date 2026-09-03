"""Tests for `apps.organizations.unit_heads` — reverse org-structure lookups.

Builds a faculty → chair → specialty → group hierarchy and checks:
* `resolve_ancestor` walks the parent chain (incl. self) for a unit_type.
* `ancestor_paths` returns materialized-path prefixes incl. self.
* `members_covering_unit` matches unit-scoped roles on the unit or any
  ancestor, and org-wide (ORGANIZATION scope_type) roles unconditionally.
* `coordinator_memberships_for_student` resolves via the student's active
  `StudentAcademicRecord.group`, scoped so another specialty's coordinator
  never leaks in.
* `chair_head_memberships_for_unit` / `dean_memberships_for_unit` cover a
  descendant unit from their respective ancestor scope_unit.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.unit_heads import (
    ancestor_paths,
    chair_head_memberships_for_unit,
    coordinator_memberships_for_student,
    dean_memberships_for_unit,
    members_covering_unit,
    resolve_ancestor,
)
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


class UnitHeadsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("uh_owner", "uh_owner@test.az", "StrongPass123!")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Unit Heads Univ",
                slug="unit-heads-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="uh-faculty", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra",
                slug="uh-chair",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty,
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org,
                name="İxtisas",
                slug="uh-specialty",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.chair,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                name="Qrup",
                slug="uh-group",
                unit_type=OrgUnitType.GROUP,
                parent=cls.specialty,
            )

            # A sibling specialty (own chain) used to prove non-leakage.
            cls.other_specialty = OrgUnit.objects.create(
                organization=cls.org,
                name="Digər ixtisas",
                slug="uh-other-specialty",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.chair,
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org,
                name="Digər qrup",
                slug="uh-other-group",
                unit_type=OrgUnitType.GROUP,
                parent=cls.other_specialty,
            )

            cls.program = Program.objects.create(
                organization=cls.org, code="UH", name="Unit Heads Programı", absence_limit_percent=25
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)

            cls.student = User.objects.create_user("uh_student", "uh_student@test.az", "StrongPass123!")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2025,
            )


class ResolveAncestorTests(UnitHeadsTestBase):
    def test_resolve_ancestor_finds_chair_from_group(self):
        self.assertEqual(resolve_ancestor(self.group, OrgUnitType.CHAIR), self.chair)

    def test_resolve_ancestor_finds_faculty_from_group(self):
        self.assertEqual(resolve_ancestor(self.group, OrgUnitType.FACULTY), self.faculty)

    def test_resolve_ancestor_matches_self(self):
        self.assertEqual(resolve_ancestor(self.group, OrgUnitType.GROUP), self.group)

    def test_resolve_ancestor_returns_none_when_absent(self):
        # Faculty has no GROUP ancestor (it IS the root).
        self.assertIsNone(resolve_ancestor(self.faculty, OrgUnitType.GROUP))


class AncestorPathsTests(UnitHeadsTestBase):
    def test_ancestor_paths_incl_self_root_first(self):
        paths = ancestor_paths(self.group)
        self.assertEqual(len(paths), 4)
        self.assertEqual(paths[0], str(self.faculty.pk))
        self.assertEqual(paths[-1], self.group.path)
        # Every prefix must itself be a valid ancestor path of an existing unit.
        self.assertTrue(paths[-1].endswith(str(self.group.pk)))

    def test_ancestor_paths_of_root_unit(self):
        self.assertEqual(ancestor_paths(self.faculty), [str(self.faculty.pk)])


class MembersCoveringUnitTests(UnitHeadsTestBase):
    def test_unit_scoped_role_on_unit_itself_covers(self):
        coordinator = User.objects.create_user("uh_coord_self", "c1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=coordinator,
            organization=self.org,
            role=self.org.roles.get(name="program_coordinator"),
            scope_unit=self.group,
            is_active=True,
        )
        result = members_covering_unit(self.org, self.group, role_names=["program_coordinator"])
        self.assertIn(coordinator, [m.user for m in result])

    def test_unit_scoped_role_on_ancestor_covers_descendant(self):
        chair_head = User.objects.create_user("uh_chair_head", "ch1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=chair_head,
            organization=self.org,
            role=self.org.roles.get(name="chair_head"),
            scope_unit=self.chair,
            is_active=True,
        )
        result = members_covering_unit(self.org, self.group, role_names=["chair_head"])
        self.assertIn(chair_head, [m.user for m in result])

    def test_unrelated_unit_does_not_cover(self):
        other_coordinator = User.objects.create_user("uh_coord_other", "c2@test.az", "StrongPass123!")
        Membership.objects.create(
            user=other_coordinator,
            organization=self.org,
            role=self.org.roles.get(name="program_coordinator"),
            scope_unit=self.other_specialty,
            is_active=True,
        )
        result = members_covering_unit(self.org, self.group, role_names=["program_coordinator"])
        self.assertNotIn(other_coordinator, [m.user for m in result])

    def test_org_wide_role_scope_type_always_covers(self):
        # Temporarily flip the seeded "dean" role to ORGANIZATION scope to
        # exercise the org-wide branch (rector/vice_rector-style roles).
        dean_role = self.org.roles.get(name="dean")
        dean_role.scope_type = RoleScopeType.ORGANIZATION
        dean_role.save(update_fields=["scope_type"])

        org_wide_dean = User.objects.create_user("uh_dean_orgwide", "d1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=org_wide_dean,
            organization=self.org,
            role=dean_role,
            scope_unit=None,
            is_active=True,
        )
        result = members_covering_unit(self.org, self.other_group, role_names=["dean"])
        self.assertIn(org_wide_dean, [m.user for m in result])

    def test_permission_filter_excludes_role_without_it(self):
        chair_head = User.objects.create_user("uh_chair_head_perm", "ch2@test.az", "StrongPass123!")
        Membership.objects.create(
            user=chair_head,
            organization=self.org,
            role=self.org.roles.get(name="chair_head"),
            scope_unit=self.chair,
            is_active=True,
        )
        # chair_head has syllabus.approve but not journal.close (RİM-only).
        with_syllabus = members_covering_unit(
            self.org, self.group, role_names=["chair_head"], permission="syllabus.approve"
        )
        self.assertIn(chair_head, [m.user for m in with_syllabus])

        with_journal_close = members_covering_unit(
            self.org, self.group, role_names=["chair_head"], permission="journal.close"
        )
        self.assertNotIn(chair_head, [m.user for m in with_journal_close])

    def test_inactive_membership_excluded(self):
        inactive_coordinator = User.objects.create_user("uh_coord_inactive", "c3@test.az", "StrongPass123!")
        Membership.objects.create(
            user=inactive_coordinator,
            organization=self.org,
            role=self.org.roles.get(name="program_coordinator"),
            scope_unit=self.specialty,
            is_active=False,
        )
        result = members_covering_unit(self.org, self.group, role_names=["program_coordinator"])
        self.assertNotIn(inactive_coordinator, [m.user for m in result])


class CoordinatorMembershipsForStudentTests(UnitHeadsTestBase):
    def test_specialty_coordinator_covers_student(self):
        coordinator = User.objects.create_user("uh_coord_covers", "cc1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=coordinator,
            organization=self.org,
            role=self.org.roles.get(name="program_coordinator"),
            scope_unit=self.specialty,
            is_active=True,
        )
        result = coordinator_memberships_for_student(self.org, self.student)
        self.assertIn(coordinator, [m.user for m in result])

    def test_other_specialty_coordinator_does_not_cover(self):
        other_coordinator = User.objects.create_user("uh_coord_notcover", "cc2@test.az", "StrongPass123!")
        Membership.objects.create(
            user=other_coordinator,
            organization=self.org,
            role=self.org.roles.get(name="program_coordinator"),
            scope_unit=self.other_specialty,
            is_active=True,
        )
        result = coordinator_memberships_for_student(self.org, self.student)
        self.assertNotIn(other_coordinator, [m.user for m in result])

    def test_student_without_group_returns_empty(self):
        groupless_student = User.objects.create_user("uh_student_nogroup", "sng@test.az", "StrongPass123!")
        Membership.objects.create(
            user=groupless_student,
            organization=self.org,
            role=self.org.roles.get(name="student"),
            is_active=True,
        )
        with bypass_rls():
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=groupless_student,
                program=self.program,
                curriculum=self.curriculum,
                group=None,
                admission_year=2025,
            )
        result = coordinator_memberships_for_student(self.org, groupless_student)
        self.assertEqual(list(result), [])


class ChairHeadDeanMembershipsForUnitTests(UnitHeadsTestBase):
    def test_chair_head_memberships_for_unit_covers_descendant_group(self):
        chair_head = User.objects.create_user("uh_ch_for_unit", "chu1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=chair_head,
            organization=self.org,
            role=self.org.roles.get(name="chair_head"),
            scope_unit=self.chair,
            is_active=True,
        )
        result = chair_head_memberships_for_unit(self.org, self.group)
        self.assertIn(chair_head, [m.user for m in result])

    def test_dean_memberships_for_unit_covers_descendant_group(self):
        dean = User.objects.create_user("uh_dean_for_unit", "du1@test.az", "StrongPass123!")
        Membership.objects.create(
            user=dean,
            organization=self.org,
            role=self.org.roles.get(name="dean"),
            scope_unit=self.faculty,
            is_active=True,
        )
        result = dean_memberships_for_unit(self.org, self.group)
        self.assertIn(dean, [m.user for m in result])

    def test_dean_memberships_for_unit_excludes_unrelated_faculty(self):
        with bypass_rls():
            other_faculty = OrgUnit.objects.create(
                organization=self.org, name="Digər fakültə", slug="uh-other-faculty", unit_type=OrgUnitType.FACULTY
            )
        other_dean = User.objects.create_user("uh_dean_other", "du2@test.az", "StrongPass123!")
        Membership.objects.create(
            user=other_dean,
            organization=self.org,
            role=self.org.roles.get(name="dean"),
            scope_unit=other_faculty,
            is_active=True,
        )
        result = dean_memberships_for_unit(self.org, self.group)
        self.assertNotIn(other_dean, [m.user for m in result])
