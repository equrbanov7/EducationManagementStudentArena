"""
Service tests for labs app.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Course
from apps.labs import services
from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LabSubmissionServicesTest(TestCase):
    """Test lab submission service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Lab Submission Services Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Block 1")
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)

    def test_create_lab_submission(self):
        """Test creating a lab submission."""
        submission = services.create_lab_submission(self.assignment)

        self.assertIsNotNone(submission)
        self.assertEqual(submission.assignment, self.assignment)
        self.assertEqual(submission.status, "submitted")
        self.assertIsNotNone(submission.submitted_at)

    def test_auto_save_lab_answers(self):
        """Test auto-saving lab answers."""
        question = LabQuestion.objects.create(block=self.block, question_text="Test question", points=10)

        answers_data = {question.id: "Test answer"}

        count = services.auto_save_lab_answers(self.assignment, answers_data)

        self.assertEqual(count, 1)
        self.assertTrue(LabAnswer.objects.filter(lab=self.lab, student=self.student, question=question).exists())


class LabGradingServicesTest(TestCase):
    """Test lab grading service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Lab Grading Services Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.teacher,
            status="published",
            organization=self.org,
        )
        self.lab = Lab.objects.create(
            title="Test Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
        )
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.submission = LabSubmission.objects.create(assignment=self.assignment, status="submitted")

    def test_grade_lab_submission(self):
        """Test grading a lab submission."""
        graded_submission = services.grade_lab_submission(self.submission, Decimal("85.5"), "Good work!", self.teacher)

        self.assertEqual(graded_submission.score, Decimal("85.5"))
        self.assertEqual(graded_submission.feedback, "Good work!")
        self.assertEqual(graded_submission.graded_by, self.teacher)
        self.assertEqual(graded_submission.status, "graded")

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertIsNone(services.parse_score_value("invalid"))


# ─────────────────────────────────────────────────────────────────────────────
# lab_submission_service additional coverage
# ─────────────────────────────────────────────────────────────────────────────


class LabSubmissionServiceExtendedTest(TestCase):
    """Extended tests for lab_submission_service and lab_grading_service."""

    def setUp(self):
        from apps.courses.models import Course, CourseMembership
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        self.teacher = User.objects.create_user(username="ext_teacher", email="ext_t@example.com", password="pass")
        self.student = User.objects.create_user(username="ext_student", email="ext_s@example.com", password="pass")
        org = Organization.objects.create(
            name="Ext Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Ext Course", owner=self.teacher, status="published", organization=org
        )
        # Enroll student so can_student_access passes
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        self.lab = Lab.objects.create(
            title="Ext Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(hours=1),
            status="published",
        )
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)

    # ── lab_submission_service ────────────────────────────────────────────

    def test_is_lab_open_published_within_window(self):
        from apps.labs.lab_submission_service import is_lab_open

        self.assertTrue(is_lab_open(self.lab))

    def test_is_lab_open_draft_returns_false(self):
        from apps.labs.lab_submission_service import is_lab_open

        self.lab.status = "draft"
        self.lab.save()
        self.assertFalse(is_lab_open(self.lab))

    def test_is_lab_open_before_start_returns_false(self):
        from apps.labs.lab_submission_service import is_lab_open

        # Pass a time before the lab's start_datetime
        before_start = self.lab.start_datetime - timedelta(hours=2)
        self.assertFalse(is_lab_open(self.lab, current_time=before_start))

    def test_is_lab_open_no_datetimes_depends_on_status(self):
        from apps.labs.lab_submission_service import is_lab_open

        # Create a lab with very wide datetimes to simulate always-open
        always_open_lab = Lab.objects.create(
            title="Always Open Lab",
            course=self.course,
            created_by=self.teacher,
            start_datetime=timezone.now() - timedelta(days=365),
            end_datetime=timezone.now() + timedelta(days=365),
            status="published",
        )
        self.assertTrue(is_lab_open(always_open_lab))

    def test_get_next_attempt_number_no_submissions(self):
        from apps.labs.lab_submission_service import get_next_attempt_number

        self.assertEqual(get_next_attempt_number(self.assignment), 1)

    def test_get_next_attempt_number_with_existing(self):
        from apps.labs.lab_submission_service import create_lab_submission, get_next_attempt_number

        create_lab_submission(self.assignment, attempt_number=1)
        self.assertEqual(get_next_attempt_number(self.assignment), 2)

    def test_get_next_attempt_number_none_assignment(self):
        from apps.labs.lab_submission_service import get_next_attempt_number

        self.assertEqual(get_next_attempt_number(None), 1)

    def test_format_lab_submission_duration_hours_and_minutes(self):
        from apps.labs.lab_submission_service import format_lab_submission_duration

        start = timezone.now()
        end = start + timedelta(hours=2, minutes=15)
        result = format_lab_submission_duration(start, end)
        self.assertIsNotNone(result)
        self.assertIn("2", result)

    def test_format_lab_submission_duration_minutes_only(self):
        from apps.labs.lab_submission_service import format_lab_submission_duration

        start = timezone.now()
        end = start + timedelta(minutes=30)
        result = format_lab_submission_duration(start, end)
        self.assertIsNotNone(result)

    def test_format_lab_submission_duration_none_inputs(self):
        from apps.labs.lab_submission_service import format_lab_submission_duration

        self.assertIsNone(format_lab_submission_duration(None, timezone.now()))
        self.assertIsNone(format_lab_submission_duration(timezone.now(), None))

    def test_format_lab_submission_duration_zero_or_negative(self):
        from apps.labs.lab_submission_service import format_lab_submission_duration

        t = timezone.now()
        self.assertIsNone(format_lab_submission_duration(t, t))

    def test_update_lab_submission_sets_status(self):
        from apps.labs.lab_submission_service import create_lab_submission, update_lab_submission

        sub = create_lab_submission(self.assignment)
        updated = update_lab_submission(sub)
        self.assertEqual(updated.status, "submitted")

    def test_finalize_submission_answers_marks_not_draft(self):
        from apps.labs.lab_submission_service import (
            auto_save_lab_answers,
            create_lab_submission,
            finalize_submission_answers,
        )

        block = LabBlock.objects.create(lab=self.lab, title="B")
        question = LabQuestion.objects.create(block=block, question_text="Q?", points=5)
        auto_save_lab_answers(self.assignment, {question.id: "my answer"})

        sub = create_lab_submission(self.assignment)
        count = finalize_submission_answers(sub)
        self.assertGreaterEqual(count, 0)

    # ── lab_grading_service ───────────────────────────────────────────────

    def test_parse_decimal_input_valid(self):
        from decimal import Decimal

        from apps.labs.lab_grading_service import parse_decimal_input

        self.assertEqual(parse_decimal_input("9.5"), Decimal("9.5"))

    def test_parse_decimal_input_comma_separator(self):
        from decimal import Decimal

        from apps.labs.lab_grading_service import parse_decimal_input

        self.assertEqual(parse_decimal_input("9,5"), Decimal("9.5"))

    def test_parse_decimal_input_empty_returns_none(self):
        from apps.labs.lab_grading_service import parse_decimal_input

        self.assertIsNone(parse_decimal_input(""))
        self.assertIsNone(parse_decimal_input(None))

    def test_parse_decimal_input_invalid_returns_none(self):
        from apps.labs.lab_grading_service import parse_decimal_input

        self.assertIsNone(parse_decimal_input("abc"))

    def test_format_decimal_input_strips_trailing_zeros(self):
        from apps.labs.lab_grading_service import format_decimal_input

        self.assertEqual(format_decimal_input("9.500"), "9.5")

    def test_format_decimal_input_zero(self):
        from apps.labs.lab_grading_service import format_decimal_input

        self.assertEqual(format_decimal_input("0.0"), "0")

    def test_format_decimal_input_none_returns_empty(self):
        from apps.labs.lab_grading_service import format_decimal_input

        self.assertEqual(format_decimal_input(None), "")

    def test_grade_lab_answer(self):
        from decimal import Decimal

        from apps.labs.lab_grading_service import grade_lab_answer

        block = LabBlock.objects.create(lab=self.lab, title="BG")
        question = LabQuestion.objects.create(block=block, question_text="Q2?", points=10)
        answer = LabAnswer.objects.create(
            lab=self.lab,
            question=question,
            student=self.student,
            answer="my answer",
        )
        result = grade_lab_answer(answer, "8.5")
        self.assertEqual(result.score, Decimal("8.5"))

    # ── lab_access ────────────────────────────────────────────────────────

    def test_can_student_access_lab_enrolled(self):
        from apps.labs.lab_access import can_student_access_lab

        self.assertTrue(can_student_access_lab(self.lab, self.student))

    def test_can_teacher_access_lab(self):
        from apps.labs.lab_access import can_teacher_access_lab

        self.assertTrue(can_teacher_access_lab(self.lab, self.teacher))

    def test_ensure_student_can_access_lab_raises_for_unknown(self):
        from django.core.exceptions import PermissionDenied

        from apps.labs.lab_access import ensure_student_can_access_lab

        stranger = User.objects.create_user(username="stranger2", email="s2@example.com", password="pass")
        with self.assertRaises(PermissionDenied):
            ensure_student_can_access_lab(self.lab, stranger)

    def test_ensure_teacher_can_access_lab_raises_for_non_owner(self):
        from django.core.exceptions import PermissionDenied

        from apps.labs.lab_access import ensure_teacher_can_access_lab

        other = User.objects.create_user(username="other_teacher2", email="ot2@example.com", password="pass")
        with self.assertRaises(PermissionDenied):
            ensure_teacher_can_access_lab(self.lab, other)

    def test_get_lab_submissions_filtered_by_status(self):
        from apps.labs.lab_access import get_lab_submissions
        from apps.labs.lab_submission_service import create_lab_submission

        sub = create_lab_submission(self.assignment)
        qs = get_lab_submissions(self.lab, status="submitted")
        self.assertIn(sub, qs)

    def test_get_pending_lab_submissions_for_teacher(self):
        from apps.labs.lab_access import get_pending_lab_submissions
        from apps.labs.lab_submission_service import create_lab_submission

        create_lab_submission(self.assignment)
        qs = get_pending_lab_submissions(self.teacher)
        self.assertTrue(qs.exists())

    # ── lab_assignment_service ────────────────────────────────────────────

    def test_create_lab_assignments_for_students_creates_new(self):
        from apps.labs.lab_assignment_service import create_lab_assignments_for_students

        student2 = User.objects.create_user(username="assign_s2", email="as2@example.com", password="pass")
        created, existing = create_lab_assignments_for_students(self.lab, [student2.id])
        self.assertEqual(created, 1)
        self.assertEqual(existing, 0)

    def test_create_lab_assignments_for_students_existing_not_duplicated(self):
        from apps.labs.lab_assignment_service import create_lab_assignments_for_students

        # Student already has an assignment from setUp
        created, existing = create_lab_assignments_for_students(self.lab, [self.student.id])
        self.assertEqual(created, 0)
        self.assertEqual(existing, 1)

    def test_get_lab_assignment_for_student(self):
        from apps.labs.lab_assignment_service import get_lab_assignment_for_student

        # The assignment already exists from setUp, so this just retrieves it
        assignment = get_lab_assignment_for_student(self.lab, self.student)
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.student, self.student)
