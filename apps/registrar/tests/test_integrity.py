"""Engine-neutral tests for registrar migration-target validation services."""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import journal_actions, services
from apps.registrar.forms import OfferingForm
from apps.registrar.integrity import (
    validate_active_member,
    validate_enrollment_target,
    validate_instructor_assignment,
    validate_offering_target,
    validate_student_record_target,
)
from apps.registrar.models import CourseOffering, Curriculum, Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


class RegistrarIntegrityServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner_a = User.objects.create_user("integrity_owner_a", password="pw")
            cls.owner_b = User.objects.create_user("integrity_owner_b", password="pw")
            cls.org_a = Organization.objects.create(
                name="Integrity A",
                slug="integrity-a",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_a,
                status="active",
                is_active=True,
            )
            cls.org_b = Organization.objects.create(
                name="Integrity B",
                slug="integrity-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_b,
                status="active",
                is_active=True,
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org_a,
                name="Group A",
                slug="integrity-group-a",
                unit_type=OrgUnitType.GROUP,
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org_b,
                name="Group B",
                slug="integrity-group-b",
                unit_type=OrgUnitType.GROUP,
            )
            cls.period_a = AcademicPeriod.objects.create(
                organization=cls.org_a,
                name="Period A",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
            )
            cls.period_b = AcademicPeriod.objects.create(
                organization=cls.org_b,
                name="Period B",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
            )
            cls.program_a = Program.objects.create(organization=cls.org_a, code="A", name="A")
            cls.program_b = Program.objects.create(organization=cls.org_b, code="B", name="B")
            cls.curriculum_a = Curriculum.objects.create(
                organization=cls.org_a,
                program=cls.program_a,
                admission_year=2026,
            )
            cls.curriculum_b = Curriculum.objects.create(
                organization=cls.org_b,
                program=cls.program_b,
                admission_year=2026,
            )
            cls.subject_a = Subject.objects.create(organization=cls.org_a, code="SA", name="SA")
            cls.subject_b = Subject.objects.create(organization=cls.org_b, code="SB", name="SB")

            cls.student = User.objects.create_user("integrity_student", password="pw")
            Membership.objects.create(
                organization=cls.org_a,
                user=cls.student,
                role=cls.org_a.roles.get(name="student"),
                is_active=True,
            )
            cls.teacher = User.objects.create_user("integrity_teacher", password="pw")
            Membership.objects.create(
                organization=cls.org_a,
                user=cls.teacher,
                role=cls.org_a.roles.get(name="teacher"),
                is_active=True,
            )

    def test_same_tenant_student_record_and_enrollment_are_accepted(self):
        with bypass_rls():
            validate_student_record_target(
                organization=self.org_a,
                student=self.student,
                program=self.program_a,
                curriculum=self.curriculum_a,
                group=self.group_a,
            )
            offering = CourseOffering.objects.create(
                organization=self.org_a,
                subject=self.subject_a,
                period=self.period_a,
                group=self.group_a,
            )
            validate_enrollment_target(
                organization=self.org_a,
                student=self.student,
                offering=offering,
            )

    def test_cross_tenant_parent_is_rejected_before_database_write(self):
        with bypass_rls(), self.assertRaises(ValidationError) as caught:
            services.get_or_create_offering(
                organization=self.org_a,
                subject=self.subject_b,
                period=self.period_a,
                group=self.group_a,
            )
        self.assertIn("subject", caught.exception.message_dict)

    def test_curriculum_must_belong_to_selected_program(self):
        with bypass_rls(), self.assertRaises(ValidationError) as caught:
            validate_student_record_target(
                organization=self.org_a,
                student=self.student,
                program=self.program_a,
                curriculum=self.curriculum_b,
                group=self.group_a,
            )
        self.assertIn("curriculum", caught.exception.message_dict)

    def test_student_requires_active_same_tenant_membership(self):
        outsider = User.objects.create_user("integrity_outsider", password="pw")
        with bypass_rls(), self.assertRaises(ValidationError):
            validate_active_member(organization=self.org_a, user=outsider)

        cross_member = User.objects.create_user("integrity_cross_member", password="pw")
        with bypass_rls():
            Membership.objects.create(
                organization=self.org_b,
                user=cross_member,
                role=self.org_b.roles.get(name="student"),
                is_active=True,
            )
            with self.assertRaises(ValidationError):
                validate_active_member(organization=self.org_a, user=cross_member)

    def test_instructor_permission_uses_central_wildcard_semantics(self):
        wildcard_teacher = User.objects.create_user("integrity_wildcard_teacher", password="pw")
        with bypass_rls():
            wildcard_role = Role.objects.create(
                organization=self.org_a,
                name="migration_grader",
                display_name="Migration grader",
                scope_type=RoleScopeType.COURSE,
                permissions=["grading.*"],
                is_active=True,
            )
            Membership.objects.create(
                organization=self.org_a,
                user=wildcard_teacher,
                role=wildcard_role,
                is_active=True,
            )
            validate_instructor_assignment(
                organization=self.org_a,
                instructor=wildcard_teacher,
            )
            self.assertIn(
                wildcard_teacher,
                OfferingForm(organization=self.org_a).fields["instructor"].queryset,
            )

    def test_permissionless_or_inactive_instructor_is_rejected(self):
        permissionless = User.objects.create_user("integrity_permissionless", password="pw")
        inactive = User.objects.create_user("integrity_inactive", password="pw")
        with bypass_rls():
            Membership.objects.create(
                organization=self.org_a,
                user=permissionless,
                role=self.org_a.roles.get(name="student"),
                is_active=True,
            )
            Membership.objects.create(
                organization=self.org_a,
                user=inactive,
                role=self.org_a.roles.get(name="teacher"),
                is_active=False,
            )
            for user in (permissionless, inactive):
                with self.subTest(user=user.username), self.assertRaises(ValidationError):
                    validate_instructor_assignment(organization=self.org_a, instructor=user)

    def test_deactivated_user_is_not_an_active_student_or_journal_instructor(self):
        with bypass_rls():
            User.objects.filter(pk=self.teacher.pk).update(is_active=False)
            with self.assertRaises(ValidationError):
                validate_active_member(organization=self.org_a, user=self.teacher)
            with self.assertRaises(Http404):
                journal_actions._resolve_instructor(self._offering(), str(self.teacher.pk))

    def test_inactive_organization_blocks_member_and_journal_resolution(self):
        with bypass_rls():
            Organization.objects.filter(pk=self.org_a.pk).update(is_active=False)
            with self.assertRaises(ValidationError):
                validate_active_member(organization=self.org_a, user=self.student)
            with self.assertRaises(Http404):
                journal_actions._resolve_instructor(self._offering(), str(self.teacher.pk))
            self.assertNotIn(
                self.teacher,
                OfferingForm(organization=self.org_a).fields["instructor"].queryset,
            )

    def test_explicit_lesson_instructor_is_validated_by_request_service(self):
        outsider = User.objects.create_user("integrity_lesson_outsider", password="pw")
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org_a,
                subject=self.subject_a,
                period=self.period_a,
                group=self.group_a,
            )
            with self.assertRaises(Http404):
                journal_actions._resolve_instructor(offering, str(outsider.pk))

    def _offering(self):
        return CourseOffering.objects.create(
            organization=self.org_a,
            subject=self.subject_a,
            period=self.period_a,
            group=self.group_a,
        )

    def test_offering_validator_rejects_cross_tenant_course(self):
        Course = __import__("apps.courses.models", fromlist=["Course"]).Course
        with bypass_rls():
            course_b = Course.objects.create(
                owner=self.owner_b,
                title="Cross tenant LMS course",
                organization=self.org_b,
            )
            with self.assertRaises(ValidationError) as caught:
                validate_offering_target(
                    organization=self.org_a,
                    subject=self.subject_a,
                    period=self.period_a,
                    group=self.group_a,
                    course=course_b,
                )
        self.assertIn("course", caught.exception.message_dict)
