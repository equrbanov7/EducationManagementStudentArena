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
        self.assertIn("assigned_tasks_count", response.context)
        self.assertIn("is_teacher", response.context)
        self.assertIn("is_admin", response.context)

    def test_profile_edit_section(self):
        """Test that edit-profile section renders form with save button."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yadda Saxla")

    def test_profile_edit_section_prefills_existing_values(self):
        from apps.accounts.models import UserProfile
        from apps.courses.models import Course

        self.user.first_name = "Elvin"
        self.user.last_name = "Qurbanov"
        self.user.email = "elvin@example.com"
        self.user.save(update_fields=["first_name", "last_name", "email"])

        profile = UserProfile.objects.get(user=self.user)
        profile.phone = "+994501112233"
        profile.location = "Baku"
        profile.student_university_name = "ADA University"
        profile.student_school_identifier = "AZ-123"
        profile.bio = "Bio test text"
        profile.save(
            update_fields=[
                "phone",
                "location",
                "student_university_name",
                "student_school_identifier",
                "bio",
                "updated_at",
            ]
        )
        Course.objects.create(owner=self.user, title="Owned Course", status="published")

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Elvin"')
        self.assertContains(response, 'value="Qurbanov"')
        self.assertContains(response, 'value="elvin@example.com"')
        self.assertContains(response, 'value="+994501112233"')
        self.assertContains(response, 'value="Baku"')
        self.assertContains(response, 'value="ADA University"')
        self.assertContains(response, 'value="AZ-123"')
        self.assertContains(response, "Bio test text")

    def test_non_profile_post_does_not_overwrite_profile_fields(self):
        from apps.accounts.models import UserProfile

        self.user.first_name = "Elvin"
        self.user.last_name = "Qurbanov"
        self.user.email = "elvin@example.com"
        self.user.save(update_fields=["first_name", "last_name", "email"])

        profile = UserProfile.objects.get(user=self.user)
        profile.phone = "+994501112233"
        profile.location = "Baku"
        profile.student_university_name = "ADA University"
        profile.student_school_identifier = "AZ-123"
        profile.bio = "Bio test text"
        profile.save(
            update_fields=[
                "phone",
                "location",
                "student_university_name",
                "student_school_identifier",
                "bio",
                "updated_at",
            ]
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("accounts:profile") + "?section=posts",
            data={"title": "Post title", "content": "Post content"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile") + "?section=posts")

        self.user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "Elvin")
        self.assertEqual(self.user.last_name, "Qurbanov")
        self.assertEqual(self.user.email, "elvin@example.com")
        self.assertEqual(profile.phone, "+994501112233")
        self.assertEqual(profile.location, "Baku")
        self.assertEqual(profile.student_university_name, "ADA University")
        self.assertEqual(profile.student_school_identifier, "AZ-123")
        self.assertEqual(profile.bio, "Bio test text")

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
        self.assertContains(response, reverse("accounts:pending_answers"))

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

    def test_org_owner_with_teacher_secondary_role_sees_teacher_navigation(self):
        from django.contrib.auth.models import Group

        from apps.accounts.models import ProfileRole, UserProfile

        profile = UserProfile.objects.get(user=self.user)
        profile.role = ProfileRole.ORG_OWNER
        profile.save(update_fields=["role", "updated_at"])

        teacher_group, _ = Group.objects.get_or_create(name=ProfileRole.TEACHER)
        self.user.groups.add(teacher_group)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:pending_review"))

    def test_manage_roles_assigns_multiple_roles_and_keeps_highest_as_primary(self):
        from apps.accounts.models import ProfileRole

        User.objects.create_superuser(
            username="superadmin_manage_roles",
            email="superadmin_manage_roles@example.com",
            password="adminpass123",
        )
        self.client.login(username="superadmin_manage_roles", password="adminpass123")

        response = self.client.post(
            reverse("accounts:manage_roles"),
            data={
                "user_id": self.user.id,
                "action": "assign",
                "role_names": [ProfileRole.TEACHER, ProfileRole.ORG_OWNER],
                "next": reverse("accounts:manage_roles"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:manage_roles"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.role, ProfileRole.ORG_OWNER)
        self.assertTrue(self.user.has_role(ProfileRole.ORG_OWNER))
        self.assertTrue(self.user.has_role(ProfileRole.TEACHER))
        self.assertIn(
            ProfileRole.TEACHER,
            set(self.user.groups.values_list("name", flat=True)),
        )
        self.assertNotIn(
            ProfileRole.ORG_OWNER,
            set(self.user.groups.values_list("name", flat=True)),
        )

    def test_manage_roles_respects_next_redirect_url(self):
        from apps.accounts.models import ProfileRole

        User.objects.create_superuser(
            username="superadmin_manage_roles_next",
            email="superadmin_manage_roles_next@example.com",
            password="adminpass123",
        )
        self.client.login(username="superadmin_manage_roles_next", password="adminpass123")

        next_url = reverse("accounts:profile") + "?section=manage-roles"
        response = self.client.post(
            reverse("accounts:manage_roles"),
            data={
                "user_id": self.user.id,
                "action": "assign",
                "role_names": [ProfileRole.TEACHER],
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

    def test_assigned_tasks_section_lists_course_assignment_lab_and_project(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment
        from apps.courses.models import Course, CourseMembership
        from apps.labs.models import Lab
        from apps.projects.models import Project

        teacher = User.objects.create_user(
            username="tasks_teacher",
            email="tasks_teacher@example.com",
            password="testpass123",
        )
        self.user.profile.role = ProfileRole.STUDENT
        self.user.profile.save(update_fields=["role", "updated_at"])

        course = Course.objects.create(
            owner=teacher,
            title="Task Course",
            status="published",
        )
        CourseMembership.objects.create(
            course=course,
            user=self.user,
            role="student",
            group_name="850",
        )

        assignment = Assignment.objects.create(
            course=course,
            title="Task Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        assignment.assigned_students.add(self.user)

        unassigned_assignment = Assignment.objects.create(
            course=course,
            title="Unassigned Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        unassigned_assignment.assigned_students.add(teacher)

        lab = Lab.objects.create(
            course=course,
            title="Task Lab",
            start_datetime=timezone.now() - timedelta(hours=2),
            end_datetime=timezone.now() + timedelta(days=1),
            status="published",
            allowed_students=str(self.user.id),
            created_by=teacher,
        )

        project = Project.objects.create(
            course=course,
            title="Task Project",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=3),
            status="active",
        )
        project.assigned_students.add(self.user)

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=assigned-exams")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş tapşırıqlar")
        self.assertContains(response, course.title)
        self.assertContains(response, assignment.title)
        self.assertContains(response, lab.title)
        self.assertContains(response, project.title)
        self.assertNotContains(response, unassigned_assignment.title)

        self.assertEqual(response.context["assigned_tasks_count"], 4)
        self.assertEqual(response.context["assigned_task_counts"]["courses"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["assignments"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["labs"], 1)
        self.assertEqual(response.context["assigned_task_counts"]["independent"], 1)

        assignment_item = next(
            item for item in response.context["assigned_task_items"] if item["category"] == "assignments"
        )
        course_item = next(item for item in response.context["assigned_task_items"] if item["category"] == "courses")
        lab_item = next(item for item in response.context["assigned_task_items"] if item["category"] == "labs")
        project_item = next(
            item for item in response.context["assigned_task_items"] if item["category"] == "independent"
        )

        self.assertIn("from_section=assigned-exams", course_item["detail_url"])
        self.assertIn("assigned_type=all", course_item["detail_url"])
        self.assertIn("from_section=assigned-exams", assignment_item["detail_url"])
        self.assertIn("assigned_type=all", assignment_item["detail_url"])
        self.assertIn("from_section=assigned-exams", lab_item["detail_url"])
        self.assertIn("assigned_type=all", lab_item["detail_url"])
        self.assertIn("from_section=assigned-exams", project_item["detail_url"])
        self.assertIn("assigned_type=all", project_item["detail_url"])


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

        from django.utils import timezone

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

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
        self.assertContains(response, reverse("accounts:profile") + "?section=my-results")
        self.assertContains(response, "results_type=all")

    def test_my_result_detail_preserves_profile_results_filter_in_back_link(self):
        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
            + "?results_type=courses"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:profile") + "?section=my-results")
        self.assertContains(response, "results_type=courses")

    def test_my_results_hides_recently_graded_submission_until_window_closes(self):
        from datetime import timedelta

        from django.utils import timezone

        self.assignment_submission.graded_at = timezone.now()
        self.assignment_submission.save(update_fields=["graded_at"])

        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Unified Assignment")

        self.assignment_submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.assignment_submission.save(update_fields=["graded_at"])
        response_after_window = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(response_after_window.status_code, 200)
        self.assertContains(response_after_window, "Unified Assignment")

    def test_my_result_detail_redirects_when_review_window_is_open(self):
        from django.utils import timezone

        self.assignment_submission.graded_at = timezone.now()
        self.assignment_submission.save(update_fields=["graded_at"])

        self.client.login(username="results_student", password="testpass123")
        response = self.client.get(
            reverse(
                "accounts:my_result_detail",
                kwargs={"item_type": "courses", "item_id": self.assignment_submission.id},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=my-results", response.url)


class PendingAnswersViewTest(TestCase):
    """Tests for student pending answers section and standalone view."""

    def setUp(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.projects.models import Project, ProjectSubmission
        from django.utils import timezone

        self.client = Client()
        self.teacher = User.objects.create_user(
            username="pending_answers_teacher",
            email="pending_answers_teacher@example.com",
            password="testpass123",
        )
        self.student = User.objects.create_user(
            username="pending_answers_student",
            email="pending_answers_student@example.com",
            password="testpass123",
        )
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Pending Answers Course", status="published")

        self.pending_assignment = Assignment.objects.create(
            course=self.course,
            title="Pending Assignment Visible",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        Submission.objects.create(
            assignment=self.pending_assignment,
            user=self.student,
            content="Pending assignment answer",
            status="submitted",
        )

        self.recently_graded_assignment = Assignment.objects.create(
            course=self.course,
            title="Recently Graded Hidden Assignment",
            start_date=timezone.now() - timedelta(days=2),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        self.recent_submission = Submission.objects.create(
            assignment=self.recently_graded_assignment,
            user=self.student,
            content="Recent graded assignment",
            status="graded",
            grade=90,
            graded_at=timezone.now(),
        )

        old_assignment = Assignment.objects.create(
            course=self.course,
            title="Old Finalized Assignment",
            start_date=timezone.now() - timedelta(days=4),
            due_date=timezone.now() - timedelta(days=2),
            status="published",
        )
        Submission.objects.create(
            assignment=old_assignment,
            user=self.student,
            content="Old graded assignment",
            status="graded",
            grade=88,
            graded_at=timezone.now() - timedelta(minutes=6),
        )

        self.written_exam = Exam.objects.create(
            author=self.teacher,
            title="Async Written Exam",
            exam_type="written",
            is_active=True,
        )
        ExamAttempt.objects.create(
            user=self.student,
            exam=self.written_exam,
            status="submitted",
            checked_by_teacher=False,
        )

        self.project = Project.objects.create(
            course=self.course,
            title="Pending Project Work",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Pending project answer",
            status="pending",
        )

    def test_pending_answers_requires_login(self):
        response = self.client.get(reverse("accounts:pending_answers"))
        self.assertEqual(response.status_code, 302)

    def test_pending_answers_lists_only_pending_or_window_items(self):
        self.client.login(username="pending_answers_student", password="testpass123")
        response = self.client.get(reverse("accounts:pending_answers"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Assignment Visible")
        self.assertContains(response, "Recently Graded Hidden Assignment")
        self.assertContains(response, "Async Written Exam")
        self.assertContains(response, "Pending Project Work")
        self.assertNotContains(response, "Old Finalized Assignment")

        items = response.context["pending_answer_items"]
        recent_item = next(item for item in items if item["title"] == "Recently Graded Hidden Assignment")
        self.assertGreater(recent_item["review_window_seconds_left"], 0)
        self.assertIn("section=pending-answers", recent_item["detail_url"])

    def test_pending_answers_search_filters_results(self):
        self.client.login(username="pending_answers_student", password="testpass123")
        response = self.client.get(reverse("accounts:pending_answers") + "?pending_search=Async")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Async Written Exam")
        self.assertNotContains(response, "Pending Assignment Visible")


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

    def test_pending_review_assignment_points_to_pending_detail_with_type_label(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from django.utils import timezone

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        student = User.objects.create_user(
            username="pending_assignment_student",
            email="pending_assignment_student@example.com",
            password="testpass123",
        )
        course = Course.objects.create(owner=self.user, title="Pending Detail Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Pending Detail Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Pending detail answer",
            status="submitted",
        )

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 200)
        items = response.context["review_items"]
        assignment_item = next(item for item in items if item["type"] == "assignment")
        self.assertEqual(assignment_item["type_label"], "Sərbəst iş")
        self.assertEqual(assignment_item["student_display"], "Anonim tələbə")
        self.assertIn(
            reverse(
                "accounts:pending_review_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            ),
            assignment_item["action_url"],
        )
        self.assertContains(response, "Anonim tələbə")
        self.assertNotContains(response, student.username)

    def test_pending_review_detail_allows_edit_within_window_and_locks_after(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from django.utils import timezone

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        student = User.objects.create_user(
            username="pending_lock_student",
            email="pending_lock_student@example.com",
            password="testpass123",
        )
        course = Course.objects.create(owner=self.user, title="Pending Lock Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Pending Lock Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Answer to lock test",
            status="submitted",
        )

        self.client.login(username="testuser", password="testpass123")
        detail_url = reverse(
            "accounts:pending_review_detail",
            kwargs={"item_type": "assignment", "item_id": submission.id},
        )

        save_response = self.client.post(
            detail_url,
            {"score": "87.5", "feedback": "Initial review feedback"},
        )
        self.assertEqual(save_response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "graded")
        self.assertEqual(float(submission.grade), 87.5)
        self.assertEqual(submission.feedback, "Initial review feedback")
        self.assertIsNotNone(submission.graded_at)

        pending_response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(pending_response.status_code, 200)
        self.assertContains(pending_response, "Pending Lock Assignment")
        self.assertContains(pending_response, "Yenidən yoxla")
        pending_items = pending_response.context["review_items"]
        lock_item = next(item for item in pending_items if item["title"] == "Pending Lock Assignment")
        self.assertGreater(lock_item["review_window_seconds_left"], 0)

        submission.graded_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["graded_at"])

        locked_response = self.client.post(
            detail_url,
            {"score": "95", "feedback": "Should not be saved"},
        )
        self.assertEqual(locked_response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(float(submission.grade), 87.5)
        self.assertEqual(submission.feedback, "Initial review feedback")

        pending_after_window = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(pending_after_window.status_code, 200)
        self.assertNotContains(pending_after_window, "Pending Lock Assignment")


class ReviewResultsViewTest(TestCase):
    """Tests for evaluated review results view (teacher-only)."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="review_user",
            email="review_user@example.com",
            password="testpass123",
        )

    def test_review_results_requires_login(self):
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 302)

    def test_review_results_redirects_non_teacher(self):
        self.client.login(username="review_user", password="testpass123")
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 302)

    def test_review_results_loads_for_teacher(self):
        from apps.accounts.models import ProfileRole

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save()

        self.client.login(username="review_user", password="testpass123")
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("evaluated_review_items", response.context)

    def test_review_results_exam_action_url_points_to_attempt_detail(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.models import Exam, ExamAttempt

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        student = User.objects.create_user(
            username="review_result_student",
            email="review_result_student@example.com",
            password="testpass123",
        )
        exam = Exam.objects.create(
            author=self.user,
            title="Direct Detail Test",
            exam_type="test",
            is_active=True,
        )
        attempt = ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status="submitted",
        )

        self.client.login(username="review_user", password="testpass123")
        response = self.client.get(reverse("accounts:review_results"))

        self.assertEqual(response.status_code, 200)
        items = response.context["evaluated_review_items"]
        exam_item = next(item for item in items if item["type"] == "exam" and item["title"] == exam.title)
        expected_path = reverse(
            "exams:teacher_view_attempt",
            kwargs={"slug": exam.slug, "attempt_id": attempt.id},
        )
        self.assertIn(expected_path, exam_item["action_url"])
        self.assertNotIn("/results/", exam_item["action_url"])

    def test_review_results_non_exam_action_urls_point_to_review_detail_page(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission
        from django.utils import timezone

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        student = User.objects.create_user(
            username="review_result_student_2",
            email="review_result_student_2@example.com",
            password="testpass123",
        )

        course = Course.objects.create(owner=self.user, title="Review Result Course", status="published")

        assignment = Assignment.objects.create(
            course=course,
            title="Reviewed Assignment",
            start_date=timezone.now() - timedelta(days=1),
            status="published",
        )
        assignment_submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Assignment reviewed answer",
            status="graded",
            grade=88,
        )

        project = Project.objects.create(
            course=course,
            title="Reviewed Project",
            start_date=timezone.now() - timedelta(days=2),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        project_submission = ProjectSubmission.objects.create(
            project=project,
            student=student,
            content="Project reviewed answer",
            status="graded",
            grade=91,
        )

        lab = Lab.objects.create(
            course=course,
            title="Reviewed Lab",
            start_datetime=timezone.now() - timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1),
            status="published",
            created_by=self.user,
        )
        lab_assignment = LabAssignment.objects.create(lab=lab, student=student)
        lab_submission = LabSubmission.objects.create(
            assignment=lab_assignment,
            submission_text="Lab reviewed answer",
            status="graded",
            score=77,
        )

        self.client.login(username="review_user", password="testpass123")
        response = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(response.status_code, 200)

        items = response.context["evaluated_review_items"]
        assignment_item = next(item for item in items if item["type"] == "assignment")
        project_item = next(item for item in items if item["type"] == "project")
        lab_item = next(item for item in items if item["type"] == "lab")

        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "assignment", "item_id": assignment_submission.id},
            ),
            assignment_item["action_url"],
        )
        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "project", "item_id": project_submission.id},
            ),
            project_item["action_url"],
        )
        self.assertIn(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "lab", "item_id": lab_submission.id},
            ),
            lab_item["action_url"],
        )

    def test_review_result_detail_assignment_loads_for_teacher(self):
        from datetime import timedelta

        from apps.accounts.models import ProfileRole
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from django.utils import timezone

        profile = self.user.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        student = User.objects.create_user(
            username="review_detail_student",
            email="review_detail_student@example.com",
            password="testpass123",
        )

        course = Course.objects.create(owner=self.user, title="Detail Course", status="published")
        assignment = Assignment.objects.create(
            course=course,
            title="Detail Assignment",
            start_date=timezone.now() - timedelta(days=1),
            status="published",
        )
        submission = Submission.objects.create(
            assignment=assignment,
            user=student,
            content="Detail content",
            status="graded",
            grade=100,
        )

        self.client.login(username="review_user", password="testpass123")
        response = self.client.get(
            reverse(
                "accounts:review_result_detail",
                kwargs={"item_type": "assignment", "item_id": submission.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Assignment")
