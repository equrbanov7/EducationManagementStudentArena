"""
Tests for the seed_ci_e2e_scenario management command.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase

from apps.assignments.models import Assignment
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.organizations.models import Membership, Organization

User = get_user_model()


class SeedCiE2EScenarioCommandTest(TransactionTestCase):
    """Verify that the deterministic multi-role E2E scenario is created correctly."""

    def test_command_seeds_role_scenario_and_regression_data(self):
        out = StringIO()
        call_command(
            "seed_ci_e2e_scenario",
            "--password",
            "ScenarioPass123!",
            stdout=out,
            verbosity=1,
        )

        org = Organization.objects.get(slug="ci-role-matrix-university")
        isolated_org = Organization.objects.get(slug="ci-isolated-university")
        pending_org = Organization.objects.get(slug="ci-pending-university")

        teacher = User.objects.get(username="ci_teacher_e2e")
        student = User.objects.get(username="ci_student_e2e")
        late_student = User.objects.get(username="ci_late_student_e2e")
        resume_student = User.objects.get(username="ci_resume_student_e2e")
        pending_owner = User.objects.get(username="ci_pending_owner_e2e")

        self.assertTrue(teacher.check_password("ScenarioPass123!"))
        self.assertEqual(pending_org.status, "pending")
        self.assertEqual(pending_owner.profile.organization, pending_org)
        self.assertEqual(pending_owner.profile.requested_organization, pending_org)

        self.assertTrue(
            Membership.objects.filter(
                user=teacher,
                organization=org,
                role__name="teacher",
                is_active=True,
            ).exists()
        )

        course = Course.objects.get(slug="ci-role-matrix-course")
        self.assertEqual(course.owner, teacher)
        self.assertEqual(course.organization, org)
        self.assertEqual(course.status, "published")

        group = StudentGroup.objects.get(name="CI Group A", organization=org)
        self.assertIn(student, group.students.all())
        self.assertIn(late_student, group.students.all())

        late_membership = CourseMembership.objects.get(course=course, user=late_student)
        self.assertEqual(late_membership.role, "student")
        self.assertEqual(late_membership.group_name, group.name)

        assignment = Assignment.objects.get(title="CI Assignment", course=course)
        self.assertIn(student, assignment.assigned_students.all())
        self.assertIn(late_student, assignment.assigned_students.all())

        exam = Exam.objects.get(slug="ci-role-matrix-exam")
        self.assertEqual(list(exam.allowed_groups.values_list("name", flat=True)), ["CI Group A"])
        self.assertTrue(exam.can_user_see(late_student))

        resume_exam = Exam.objects.get(slug="ci-resume-exam")
        resume_attempt = ExamAttempt.objects.get(exam=resume_exam, user=resume_student)
        self.assertEqual(resume_attempt.status, "in_progress")

        isolated_exam = Exam.objects.get(slug="ci-isolated-exam")
        self.assertEqual(isolated_exam.organization, isolated_org)

        self.assertIn("Seeded E2E role scenario", out.getvalue())

    def test_command_rerun_repairs_group_based_assignment_access(self):
        call_command(
            "seed_ci_e2e_scenario",
            "--password",
            "ScenarioPass123!",
            verbosity=0,
        )

        course = Course.objects.get(slug="ci-role-matrix-course")
        assignment = Assignment.objects.get(title="CI Assignment", course=course)
        late_student = User.objects.get(username="ci_late_student_e2e")

        assignment.assigned_students.remove(late_student)
        self.assertNotIn(late_student, assignment.assigned_students.all())

        call_command(
            "seed_ci_e2e_scenario",
            "--password",
            "ScenarioPass123!",
            verbosity=0,
        )

        assignment.refresh_from_db()
        self.assertIn(late_student, assignment.assigned_students.all())
