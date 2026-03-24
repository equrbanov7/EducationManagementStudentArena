from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm, StudentGroupForm
from apps.exams.models import Exam
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamFormDefaultStateTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="exam_form_teacher",
            email="exam_form_teacher@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="Exam Form Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

    def test_create_form_marks_is_active_checked_by_default(self):
        form = ExamForm()
        self.assertTrue(form.initial.get("is_active"))

    def test_edit_form_keeps_existing_is_active_value(self):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Draft exam",
            exam_type="test",
            is_active=False,
        )
        form = ExamForm(instance=exam)
        self.assertFalse(bool(form["is_active"].value()))


class StudentGroupFormRoleSourceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="group_form_owner",
            email="group_form_owner@example.com",
            password="StrongPass123!",
        )
        self.teacher = User.objects.create_user(
            username="group_form_teacher",
            email="group_form_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="group_form_student",
            email="group_form_student@example.com",
            password="StrongPass123!",
        )
        self.member_with_teacher_group = User.objects.create_user(
            username="group_form_member_teacher_group",
            email="group_form_member_teacher_group@example.com",
            password="StrongPass123!",
        )
        self.member_with_student_group = User.objects.create_user(
            username="group_form_member_student_group",
            email="group_form_member_student_group@example.com",
            password="StrongPass123!",
        )
        self.legacy_profile_teacher = User.objects.create_user(
            username="group_form_legacy_profile_teacher",
            email="group_form_legacy_profile_teacher@example.com",
            password="StrongPass123!",
        )
        self.legacy_profile_student = User.objects.create_user(
            username="group_form_legacy_profile_student",
            email="group_form_legacy_profile_student@example.com",
            password="StrongPass123!",
        )

        self.org = Organization.objects.create(
            name="Student Group Form Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )

        for user, membership_role in (
            (self.teacher, "teacher"),
            (self.student, "student"),
            (self.member_with_teacher_group, "member"),
            (self.member_with_student_group, "member"),
        ):
            Membership.objects.create(
                user=user,
                organization=self.org,
                role=self.org.roles.get(name=membership_role),
                is_primary=True,
                is_active=True,
            )

        teacher_group = Group.objects.create(name=ProfileRole.TEACHER)
        student_group = Group.objects.create(name=ProfileRole.STUDENT)
        self.member_with_teacher_group.groups.add(teacher_group)
        self.member_with_student_group.groups.add(student_group)
        self.legacy_profile_teacher.profile.organization = self.org
        self.legacy_profile_teacher.profile.organization_type = self.org.org_type
        self.legacy_profile_teacher.profile.role = ProfileRole.TEACHER
        self.legacy_profile_teacher.profile.save(
            update_fields=["organization", "organization_type", "role", "updated_at"]
        )
        self.legacy_profile_student.profile.organization = self.org
        self.legacy_profile_student.profile.organization_type = self.org.org_type
        self.legacy_profile_student.profile.role = ProfileRole.STUDENT
        self.legacy_profile_student.profile.save(
            update_fields=["organization", "organization_type", "role", "updated_at"]
        )

    def test_auth_groups_do_not_expand_teacher_or_student_queryset(self):
        form = StudentGroupForm(actor=self.teacher, organization=self.org)

        teacher_ids = set(form.fields["primary_teacher"].queryset.values_list("id", flat=True))
        student_ids = set(form.fields["students"].queryset.values_list("id", flat=True))

        self.assertIn(self.teacher.id, teacher_ids)
        self.assertIn(self.student.id, student_ids)
        self.assertNotIn(self.member_with_teacher_group.id, teacher_ids)
        self.assertNotIn(self.member_with_student_group.id, student_ids)
        self.assertNotIn(self.legacy_profile_teacher.id, teacher_ids)
        self.assertNotIn(self.legacy_profile_student.id, student_ids)
