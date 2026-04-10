"""
Service tests for exams app.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import ProfileRole
from apps.exams import services
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, QuestionBlock
from apps.exams.services import parsing
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamAttemptManagementServicesTest(TestCase):
    """Test exam attempt management service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(title="Test Exam", author=self.teacher, is_active=True, max_attempts_per_user=3)

    def test_get_active_attempt_for_user(self):
        """Test getting active attempt for user."""
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="in_progress")

        active_attempt = services.get_active_attempt_for_user(self.exam, self.student)

        self.assertEqual(active_attempt, attempt)

    def test_can_user_start_new_attempt(self):
        """Test checking if user can start new attempt."""
        can_start, reason = services.can_user_start_new_attempt(self.exam, self.student)

        self.assertTrue(can_start)
        self.assertEqual(reason, "ok")

    def test_cannot_start_attempt_when_active_exists(self):
        """Test cannot start new attempt when active exists."""
        ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="in_progress")

        can_start, reason = services.can_user_start_new_attempt(self.exam, self.student)

        self.assertFalse(can_start)
        self.assertEqual(reason, "active_attempt_exists")

    def test_create_exam_attempt(self):
        """Test creating a new exam attempt."""
        attempt = services.create_exam_attempt(self.exam, self.student)

        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.user, self.student)
        self.assertEqual(attempt.exam, self.exam)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, "in_progress")

    def test_submit_exam_attempt(self):
        """Test submitting an exam attempt."""
        attempt = services.create_exam_attempt(self.exam, self.student)

        submitted_attempt = services.submit_exam_attempt(attempt)

        self.assertEqual(submitted_attempt.status, "submitted")
        self.assertIsNotNone(submitted_attempt.finished_at)


class ExamGradingServicesTest(TestCase):
    """Test exam grading service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, attempt_number=1, status="submitted"
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Test question",
            points=10,
        )
        self.answer = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=self.question,
            text_answer="Test answer",
        )

    def test_grade_exam_answer(self):
        """Test grading an exam answer."""
        graded_answer = services.grade_exam_answer(self.answer, 8, self.teacher)

        self.assertEqual(graded_answer.teacher_score, 8)

    def test_calculate_attempt_score(self):
        """Test calculating total attempt score."""
        services.grade_exam_answer(self.answer, 8, self.teacher)

        total_score = services.calculate_attempt_score(self.attempt)

        self.assertEqual(total_score, Decimal("8"))


class ExamQuestionRandomizerServicesTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="randomizer_teacher", email="rt@example.com", password="pass123")
        self.student = User.objects.create_user(username="randomizer_student", email="rs@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Randomizer Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(
            title="Randomized Block Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            random_question_count=5,
        )

    def test_generate_random_questions_for_attempt_balances_one_question_per_block(self):
        blocks = [
            QuestionBlock.objects.create(exam=self.exam, name=f"Block {index + 1}", order=index + 1)
            for index in range(5)
        ]
        for block in blocks:
            for question_index in range(2):
                ExamQuestion.objects.create(
                    exam=self.exam,
                    block=block,
                    text=f"{block.name} Question {question_index + 1}",
                    points=1,
                    is_active=True,
                )

        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        generate_random_questions_for_attempt(attempt)

        answers = list(attempt.answers.select_related("question__block"))
        self.assertEqual(len(answers), 5)
        block_counts = {}
        for answer in answers:
            block_id = answer.question.block_id
            block_counts[block_id] = block_counts.get(block_id, 0) + 1

        self.assertEqual(set(block_counts.keys()), {block.id for block in blocks})
        self.assertTrue(all(count == 1 for count in block_counts.values()))


class ExamAccessControlServicesTest(TestCase):
    """Test exam access control service functions."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        Membership.objects.create(
            user=self.teacher,
            organization=self.org,
            role=self.org.roles.get(name="teacher"),
            is_primary=True,
            is_active=True,
        )
        self.teacher.set_active_organization_context(self.org)

        self.student = User.objects.create_user(username="student", email="student@example.com", password="pass123")
        self.exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
        )

    def test_is_teacher_user(self):
        """Test checking if user is teacher."""
        self.assertTrue(services.is_teacher_user(self.teacher))
        self.assertFalse(services.is_teacher_user(self.student))

    def test_is_teacher_user_denies_without_bound_tenant_context(self):
        self.teacher.clear_active_organization_context()

        self.assertFalse(services.is_teacher_user(self.teacher))

    def test_is_teacher_user_allows_org_admin_level_membership(self):
        org_admin = User.objects.create_user(username="org_admin", email="org_admin@example.com", password="pass123")
        org_admin.profile.organization = self.org
        org_admin.profile.organization_type = self.org.org_type
        org_admin.profile.role = ProfileRole.ORG_ADMIN
        org_admin.profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.create(
            user=org_admin,
            organization=self.org,
            role=self.org.roles.get(name="deputy_director"),
            is_primary=True,
            is_active=True,
        )
        org_admin.set_active_organization_context(self.org)

        self.assertTrue(services.is_teacher_user(org_admin))

    def test_can_user_access_exam_as_author(self):
        """Test exam access for author."""
        self.assertTrue(services.can_user_access_exam(self.exam, self.teacher))

    def test_parse_score_value(self):
        """Test parsing score values."""
        self.assertEqual(services.parse_score_value("95.5"), Decimal("95.5"))
        self.assertEqual(services.parse_score_value(85), Decimal("85"))
        self.assertIsNone(services.parse_score_value("invalid"))


class ExamParsingServicesTest(TestCase):
    def test_extract_text_from_upload_reads_pdf_with_pypdf(self):
        uploaded = SimpleUploadedFile("questions.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        fake_page = Mock()
        fake_page.extract_text.return_value = "1) Sual A) Bir B) Iki C) Uc D) Dord Cavab: B"

        with patch.object(parsing, "PdfReader", return_value=SimpleNamespace(pages=[fake_page])) as pdf_reader:
            text = parsing.extract_text_from_upload(uploaded)

        self.assertEqual(text, "1) Sual\nA) Bir\nB) Iki\nC) Uc\nD) Dord\nCavab: B")
        pdf_reader.assert_called_once_with(uploaded)

    def test_extract_text_from_upload_fails_without_pypdf(self):
        uploaded = SimpleUploadedFile("questions.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        with patch.object(parsing, "PdfReader", None):
            with self.assertRaises(ValueError) as exc:
                parsing.extract_text_from_upload(uploaded)

        self.assertIn("pypdf", str(exc.exception))


# ─────────────────────────────────────────────────────────────────────────────
# Exams grading service coverage
# ─────────────────────────────────────────────────────────────────────────────


class ExamGradingServiceTest(TestCase):
    """Tests for apps/exams/services/grading.py and domain/grading.py."""

    def setUp(self):
        self.teacher = User.objects.create_user(username="grd_teacher", email="grd_t@example.com", password="pass")
        self.student = User.objects.create_user(username="grd_student", email="grd_s@example.com", password="pass")
        org = Organization.objects.create(
            name="Grading Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Grading Exam",
            slug="grading-exam",
            author=self.teacher,
            organization=org,
            exam_type="test",
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Q?",
            points=10,
            order=1,
        )
        self.attempt = ExamAttempt.objects.create(exam=self.exam, user=self.student)
        self.answer = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=self.question,
        )

    def test_grade_exam_answer_sets_score(self):
        from apps.exams.services.grading import grade_exam_answer

        result = grade_exam_answer(self.answer, "8")
        self.assertEqual(result.teacher_score, 8)

    def test_grade_exam_answer_with_feedback(self):
        from apps.exams.services.grading import grade_exam_answer

        result = grade_exam_answer(self.answer, "7", feedback="Good answer")
        self.assertEqual(result.teacher_feedback, "Good answer")

    def test_grade_exam_answer_decimal_input(self):
        from decimal import Decimal

        from apps.exams.services.grading import grade_exam_answer

        result = grade_exam_answer(self.answer, Decimal("9"))
        self.assertEqual(result.teacher_score, 9)

    def test_bulk_grade_answers(self):
        from apps.exams.services.grading import bulk_grade_answers

        answer2 = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=ExamQuestion.objects.create(exam=self.exam, text="Q2?", points=5, order=2),
        )
        count = bulk_grade_answers([self.answer.id, answer2.id], [5, 7])
        self.assertEqual(count, 2)

    def test_calculate_attempt_score_test_type_correct(self):
        from decimal import Decimal

        from apps.exams.models import ExamQuestionOption
        from apps.exams.services.grading import calculate_attempt_score

        option = ExamQuestionOption.objects.create(question=self.question, text="Yes", is_correct=True)
        self.answer.selected_options.add(option)
        self.answer.is_correct = True
        self.answer.save()
        score = calculate_attempt_score(self.attempt)
        self.assertEqual(score, Decimal("10"))

    def test_calculate_attempt_score_uses_teacher_score_if_set(self):
        from decimal import Decimal

        from apps.exams.services.grading import calculate_attempt_score

        self.answer.teacher_score = 6
        self.answer.save()
        score = calculate_attempt_score(self.attempt)
        self.assertEqual(score, Decimal("6"))

    def test_parse_score_value_valid(self):
        from decimal import Decimal

        from apps.exams.services.grading import parse_score_value

        self.assertEqual(parse_score_value("9.5"), Decimal("9.5"))

    def test_parse_score_value_invalid_returns_default(self):
        from apps.exams.services.grading import parse_score_value

        self.assertIsNone(parse_score_value("bad"))
        self.assertEqual(parse_score_value("bad", default=0), 0)

    def test_parse_score_value_none_returns_default(self):
        from apps.exams.services.grading import parse_score_value

        self.assertIsNone(parse_score_value(None))
        self.assertIsNone(parse_score_value(""))
