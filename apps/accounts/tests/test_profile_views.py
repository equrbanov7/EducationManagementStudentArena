"""
Tests for profile and dashboard views.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class ProfileViewTest(TestCase):
    """Tests for the profile view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_profile_requires_login(self):
        """Test that profile page requires authentication."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_page_loads(self):
        """Test that profile page loads for authenticated user."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil")

    def test_profile_creates_userprofile(self):
        """Test that profile view creates UserProfile if missing."""
        from apps.accounts.models import UserProfile

        # Delete any auto-created profile
        UserProfile.objects.filter(user=self.user).delete()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_has_stats(self):
        """Test that profile page includes stats context."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertIn("assigned_exams_count", response.context)
        self.assertIn("assigned_courses_count", response.context)
        self.assertIn("is_teacher", response.context)
        self.assertIn("is_admin", response.context)

    def test_profile_edit_section(self):
        """Test that edit-profile section renders form with save button."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yadda Saxla")

    def test_superuser_is_teacher_and_admin(self):
        """Test that superusers always pass role checks."""
        superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.assertTrue(superuser.is_teacher_or_above)
        self.assertTrue(superuser.is_admin_level)

    def test_profile_my_exams_context_for_teacher(self):
        """Test that teacher profile includes my_exams context."""
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.TEACHER
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertIn("my_exams_count", response.context)
        self.assertIn("my_created_courses_count", response.context)

    def test_profile_role_field(self):
        """Test that profile has role field with default member role."""
        from apps.accounts.models import ProfileRole, UserProfile

        self.client.login(username="testuser", password="testpass123")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.role, ProfileRole.MEMBER)
        self.assertEqual(profile.role_level, 20)

    def test_profile_role_level_check(self):
        """Test that profile role is used for role level checks."""
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.TEACHER
        profile.save()
        # Reload user
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_teacher_or_above)

    def test_student_profile_hides_teacher_and_admin_navigation(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.STUDENT
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("accounts:role_assignment"))
        self.assertNotContains(response, reverse("accounts:permission_editor"))
        self.assertNotContains(response, reverse("exams:teacher_group_list"))
        self.assertNotContains(response, reverse("accounts:pending_review"))

    def test_student_profile_shows_posts_and_results_navigation(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.STUDENT
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("create_post"))
        self.assertContains(response, reverse("accounts:my_results"))

    def test_student_profile_keeps_single_assigned_courses_sidebar_entry(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.STUDENT
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:assigned_courses"))
        self.assertNotContains(response, reverse("accounts:profile") + "?section=courses")

    def test_teacher_profile_shows_teacher_navigation_only(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.TEACHER
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:teacher_group_list"))
        self.assertContains(response, reverse("accounts:pending_review"))
        self.assertNotContains(response, reverse("accounts:superadmin_organizations"))

    def test_member_profile_shows_group_navigation(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:teacher_group_list"))
        self.assertNotContains(response, reverse("accounts:pending_review"))

    def test_org_admin_profile_shows_groups_and_management_navigation(self):
        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.ORG_ADMIN
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:role_assignment"))
        self.assertContains(response, reverse("accounts:permission_editor"))
        self.assertNotContains(response, reverse("accounts:pending_review"))
        self.assertContains(response, reverse("exams:teacher_group_list"))


class AssignedItemsViewTest(TestCase):
    """Tests for assigned exams and courses views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_assigned_exams_requires_login(self):
        """Test that assigned exams page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_exams_loads(self):
        """Test that assigned exams page loads."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş imtahanlarım")

    def test_assigned_courses_requires_login(self):
        """Test that assigned courses page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_courses_loads(self):
        """Test that assigned courses page loads."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş kurslarım")

    def test_assigned_courses_with_items_uses_course_dashboard_link(self):
        from apps.courses.models import Course, CourseMembership

        teacher = User.objects.create_user(
            username="course_teacher",
            email="course_teacher@example.com",
            password="testpass123",
        )
        course = Course.objects.create(
            owner=teacher,
            title="Assigned Course",
            status="published",
        )
        CourseMembership.objects.create(course=course, user=self.user, role="student")

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Course")
        self.assertContains(response, reverse("courses:course_dashboard", args=[course.id]))

    def test_assigned_courses_empty_state_message(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No courses assigned yet.")

    def test_assigned_exams_shows_only_assigned_and_links_to_start(self):
        from apps.courses.models import Course, CourseMembership
        from apps.exams.models import Exam

        teacher = User.objects.create_user(
            username="exam_teacher",
            email="exam_teacher@example.com",
            password="testpass123",
        )
        course = Course.objects.create(
            owner=teacher,
            title="Assigned Exam Course",
            status="published",
        )
        CourseMembership.objects.create(course=course, user=self.user, role="student")

        direct_exam = Exam.objects.create(
            author=teacher,
            title="Directly Assigned Exam",
            is_active=True,
            is_public=False,
        )
        direct_exam.allowed_users.add(self.user)

        course_exam = Exam.objects.create(
            author=teacher,
            title="Course Assigned Exam",
            is_active=True,
            is_public=False,
            course=course,
        )

        code_exam = Exam.objects.create(
            author=teacher,
            title="Code Assigned Exam",
            is_active=True,
            is_public=False,
            access_code="123456",
        )
        code_exam.allowed_users.add(self.user)

        assigned_public_exam = Exam.objects.create(
            author=teacher,
            title="Assigned Public Exam",
            is_active=True,
            is_public=True,
        )
        assigned_public_exam.allowed_users.add(self.user)

        public_exam = Exam.objects.create(
            author=teacher,
            title="Public Unassigned Exam",
            is_active=True,
            is_public=True,
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, direct_exam.title)
        self.assertContains(response, course_exam.title)
        self.assertContains(response, code_exam.title)
        self.assertNotContains(response, assigned_public_exam.title)
        self.assertNotContains(response, public_exam.title)
        self.assertContains(response, reverse("exams:start_exam", args=[direct_exam.slug]))
        self.assertContains(response, reverse("exams:start_exam", args=[course_exam.slug]))
        self.assertContains(response, reverse("exams:exam_code_check"))
        self.assertContains(response, f'data-exam-slug="{code_exam.slug}"')


class MyResultsViewTest(TestCase):
    def setUp(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission
        from django.utils import timezone

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="results_teacher",
            email="results_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="results_student",
            email="results_student@example.com",
            password="testpass123",
        )
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Result Course", status="published")

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Unified Exam",
            is_active=True,
            is_public=True,
        )
        self.exam_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
        )

        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Unified Assignment",
            start_date=timezone.now(),
            status="published",
        )
        self.assignment_submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Assignment answer",
            status="graded",
            feedback="Assignment feedback",
            grade=91,
        )

        self.lab = Lab.objects.create(
            course=self.course,
            title="Unified Lab",
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=2),
            status="published",
            created_by=self.teacher,
        )
        self.lab_assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.lab_submission = LabSubmission.objects.create(
            assignment=self.lab_assignment,
            submission_text="Lab answer",
            status="submitted",
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Unified Project",
            start_date=timezone.now(),
            deadline=timezone.now() + timedelta(days=3),
            status="active",
        )
        self.project_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Project answer",
            status="pending",
        )

    def test_my_results_requires_login(self):
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 302)

    def test_my_results_unified_list_contains_all_submission_types(self):
        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Exam")
        self.assertContains(response, "Unified Assignment")
        self.assertContains(response, "Unified Lab")
        self.assertContains(response, "Unified Project")
        self.assertContains(response, "View answer/details")

    def test_my_results_filter_labs_only(self):
        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(reverse("accounts:my_results") + "?type=labs")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Lab")
        self.assertNotContains(response, "Unified Assignment")

    def test_my_result_detail_for_assignment_submission(self):
        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Assignment")
        self.assertContains(response, "Assignment feedback")


class PendingReviewViewTest(TestCase):
    """Tests for pending review view (teacher-only)."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_pending_review_requires_login(self):
        """Test that pending review requires authentication."""
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)

    def test_pending_review_redirects_non_teacher(self):
        """Test that non-teacher users are redirected."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)  # Redirect for non-teacher

    def test_pending_review_loads_for_teacher(self):
        from apps.accounts.models import ProfileRole

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("review_items", response.context)

    def test_pending_review_only_includes_teacher_owned_exam_attempts(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.models import Exam, ExamAttempt
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        other_teacher = User.objects.create_user(
            username="other_teacher",
            email="other_teacher@example.com",
            password="testpass123",
        )
        student = User.objects.create_user(
            username="pending_student",
            email="pending_student@example.com",
            password="testpass123",
        )

        org = Organization.objects.create(
            name="Pending Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )

        self.user.profile.organization = org
        self.user.profile.organization_type = org.org_type
        self.user.profile.role = ProfileRole.TEACHER
        self.user.profile.save()

        other_teacher.profile.organization = org
        other_teacher.profile.organization_type = org.org_type
        other_teacher.profile.role = ProfileRole.TEACHER
        other_teacher.profile.save()

        student.profile.organization = org
        student.profile.organization_type = org.org_type
        student.profile.role = ProfileRole.STUDENT
        student.profile.save()

        teacher_exam = Exam.objects.create(
            author=self.user,
            title="Teacher Pending Exam",
            exam_type="written",
            is_active=True,
        )
        other_exam = Exam.objects.create(
            author=other_teacher,
            title="Other Pending Exam",
            exam_type="written",
            is_active=True,
        )

        ExamAttempt.objects.create(
            user=student,
            exam=teacher_exam,
            status="submitted",
            checked_by_teacher=False,
        )
        ExamAttempt.objects.create(
            user=student,
            exam=other_exam,
            status="submitted",
            checked_by_teacher=False,
        )

        self.client.login(username="testuser", password="testpass123")
        session = self.client.session
        session["active_organization"] = org.slug
        session.save()

        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teacher Pending Exam")
        self.assertNotContains(response, "Other Pending Exam")
