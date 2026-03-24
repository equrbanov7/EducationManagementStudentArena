"""
Service tests for courses app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.courses import services
from apps.courses.models import Course, CourseMembership
from apps.exams.models import StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class CourseEnrollmentServicesTest(TestCase):
    """Test course enrollment service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Enrollment Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )

    def test_enroll_user_in_course(self):
        """Test enrolling a user in a course."""
        membership = services.enroll_user_in_course(self.course, self.student, role="student", group_name="Group A")

        self.assertIsNotNone(membership)
        self.assertEqual(membership.user, self.student)
        self.assertEqual(membership.course, self.course)
        self.assertEqual(membership.group_name, "Group A")

    def test_remove_user_from_course(self):
        """Test removing a user from a course."""
        services.enroll_user_in_course(self.course, self.student)

        removed = services.remove_user_from_course(self.course, self.student)

        self.assertTrue(removed)
        self.assertFalse(CourseMembership.objects.filter(course=self.course, user=self.student).exists())


class RosterManagementServicesTest(TestCase):
    """Test roster management service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Roster Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        Membership.objects.create(
            user=self.teacher,
            organization=self.org,
            role=self.org.roles.get(name="teacher"),
            is_primary=True,
            is_active=True,
        )
        self.students = [
            User.objects.create_user(username=f"student{i}", email=f"student{i}@example.com", password="pass123")
            for i in range(3)
        ]

    def test_bulk_add_members_to_course(self):
        """Test bulk adding members to a course."""
        student_ids = [s.id for s in self.students]

        created, existing = services.bulk_add_members_to_course(
            self.course, student_ids, role="student", group_name="Group A"
        )

        self.assertEqual(created, 3)
        self.assertEqual(existing, 0)
        self.assertEqual(CourseMembership.objects.filter(course=self.course).count(), 3)

    def test_bulk_add_members_idempotent(self):
        """Re-enrolling existing members does not create duplicates."""
        student_ids = [s.id for s in self.students]
        services.bulk_add_members_to_course(self.course, student_ids)
        created, existing = services.bulk_add_members_to_course(self.course, student_ids)

        self.assertEqual(created, 0)
        self.assertEqual(existing, 3)
        self.assertEqual(CourseMembership.objects.filter(course=self.course).count(), 3)

    def test_add_students_from_group_to_course(self):
        """Students in a StudentGroup are enrolled in a single batch."""
        group = StudentGroup.objects.create(
            name="Group A",
            teacher=self.teacher,
            organization=self.org,
        )
        for student in self.students:
            group.students.add(student)

        created, existing = services.add_students_from_group_to_course(self.course, group, group_name="Group A")

        self.assertEqual(created, 3)
        self.assertEqual(existing, 0)
        self.assertEqual(CourseMembership.objects.filter(course=self.course, group_name="Group A").count(), 3)

    def test_add_students_from_group_updates_existing_group_name(self):
        """Existing student members get their group name updated when re-added."""
        group = StudentGroup.objects.create(
            name="Old Group",
            teacher=self.teacher,
            organization=self.org,
        )
        for student in self.students:
            group.students.add(student)
            services.enroll_user_in_course(self.course, student, group_name="Old Group")

        created, existing = services.add_students_from_group_to_course(self.course, group, group_name="New Group")

        self.assertEqual(created, 0)
        self.assertEqual(existing, 3)
        self.assertEqual(CourseMembership.objects.filter(course=self.course, group_name="New Group").count(), 3)

    def test_remove_group_from_course(self):
        """Test removing a group from a course."""
        for student in self.students:
            services.enroll_user_in_course(self.course, student, group_name="Group A")

        deleted_count = services.remove_group_from_course(self.course, "Group A")

        self.assertEqual(deleted_count, 3)
        self.assertEqual(CourseMembership.objects.filter(course=self.course).count(), 0)


class CourseQueryServicesTest(TestCase):
    """Test course query service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Query Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        services.enroll_user_in_course(self.course, self.student, group_name="Group A")

    def test_get_course_members(self):
        """Test getting course members."""
        members = services.get_course_members(self.course)

        self.assertEqual(members.count(), 1)
        self.assertEqual(members.first().user, self.student)

    def test_get_course_groups(self):
        """Test getting course groups."""
        groups = services.get_course_groups(self.course)

        self.assertIn("Group A", groups)

    def test_is_user_enrolled_in_course(self):
        """Test checking if user is enrolled."""
        self.assertTrue(services.is_user_enrolled_in_course(self.course, self.student))

        other_user = User.objects.create_user(username="other", email="other@example.com", password="pass123")
        self.assertFalse(services.is_user_enrolled_in_course(self.course, other_user))


class CourseTenantOrganizationTest(TestCase):
    def test_course_organization_defaults_from_owner_profile(self):
        teacher = User.objects.create_user(
            username="tenant_teacher",
            email="tenant_teacher@example.com",
            password="pass123",
        )
        organization = Organization.objects.create(
            name="Course Model Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        teacher.profile.organization = organization
        teacher.profile.organization_type = organization.org_type
        teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        course = Course.objects.create(
            title="Tenant Bound Course",
            owner=teacher,
            status="published",
        )

        self.assertEqual(course.organization, organization)
