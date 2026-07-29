"""
Service tests for exams app.
"""

import base64
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.translation import override, pgettext

from apps.accounts.models import ProfileRole
from apps.exams import services
from apps.exams.models import (
    Exam,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamSupervisionConfig,
    QuestionBlock,
    SupervisionIncident,
)
from apps.exams.services import parsing
from apps.exams.services.ai_grading import _parse_ai_grade, grade_written_answer
from apps.exams.services.ai_question_generation import generate_question_bank_text
from apps.exams.services.ai_summary import generate_exam_statistics_summary
from apps.exams.services.difficulty import ensure_ai_question_difficulties, schedule_ai_question_difficulty_warmup
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.supervision import (
    get_attempt_live_snapshot,
    get_attempt_supervision_status,
    get_supervision_monitor_data,
    log_supervision_incident,
    save_supervision_config_from_form,
    sweep_expired_resume_windows,
    teacher_lock_attempt,
    teacher_resume_attempt,
    teacher_stop_attempt,
)
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII="
)


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

    def test_get_active_attempt_for_user_expires_timed_out_attempt(self):
        self.exam.total_duration_minutes = 30
        self.exam.save(update_fields=["total_duration_minutes"])
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1, status="in_progress")
        attempt.started_at = timezone.now() - timedelta(minutes=31)
        attempt.save(update_fields=["started_at"])

        active_attempt = services.get_active_attempt_for_user(self.exam, self.student)

        self.assertIsNone(active_attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertIsNotNone(attempt.finished_at)

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


class AIWrittenGradingServiceTest(SimpleTestCase):
    def test_parse_ai_grade_rounds_decimal_scores_like_teacher_points(self):
        score, explanation = _parse_ai_grade("SCORE: 7.5\nEXPLANATION: Mostly correct.", 10)

        self.assertEqual(score, 8)
        self.assertEqual(explanation, "Mostly correct.")

    def test_parse_ai_grade_scales_fractional_score_to_requested_max(self):
        score, explanation = _parse_ai_grade("SCORE: 8/10\nEXPLANATION: Strong answer.", 5)

        self.assertEqual(score, 4)
        self.assertEqual(explanation, "Strong answer.")

    def test_parse_ai_grade_accepts_localized_score_label(self):
        score, explanation = _parse_ai_grade("Bal: 9\nRəy: Cavab aydındır.", 10)

        self.assertEqual(score, 9)
        self.assertEqual(explanation, "Cavab aydındır.")

    @override_settings(GEMINI_API_KEY="test-gemini-key")
    @patch("apps.exams.services.ai_grading.requests.post")
    def test_grade_written_answer_sends_uploaded_images_to_gemini(self, mock_post):
        cache.clear()
        uploaded_image = SimpleUploadedFile(
            "written-answer.png",
            _TINY_PNG_BYTES,
            content_type="image/png",
        )
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "SCORE: 4\nEXPLANATION: The handwritten solution is mostly correct."}]}}
            ]
        }
        mock_post.return_value = mock_response

        result = grade_written_answer(
            question_text="Explain the theorem",
            student_answer="",
            max_points=5,
            answer_files=[SimpleNamespace(file=uploaded_image)],
            language_code="en",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["score"], 4)
        self.assertIn("handwritten solution", result["explanation"])
        mock_post.assert_called_once()

        payload = mock_post.call_args.kwargs["json"]
        parts = payload["contents"][0]["parts"]
        self.assertTrue(parts[0]["text"].startswith("You are an expert exam grader."))
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/png")
        self.assertEqual(parts[1]["inline_data"]["data"], base64.b64encode(_TINY_PNG_BYTES).decode("ascii"))


class AIQuestionGenerationServiceTest(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="test-gemini-key")
    @patch("apps.exams.services.ai_question_generation._call_gemini_text")
    def test_generates_test_questions_in_bulk_import_format(self, mock_call_gemini_text):
        mock_call_gemini_text.return_value = """
        {
          "questions": [
            {
              "text": "Python-da funksiya nə üçündür?",
              "options": {
                "A": "Kod blokunu təkrar istifadə etmək",
                "B": "Yalnız rəng seçmək",
                "C": "Faylı silmək",
                "D": "Brauzeri bağlamaq",
                "E": "Şəbəkəni söndürmək"
              },
              "correct": ["A"],
              "answer_mode": "single"
            }
          ]
        }
        """

        result = generate_question_bank_text(
            exam_title="Python Quiz",
            exam_type="test",
            prompt_text="Funksiyalar mövzusu",
            question_count=1,
            language_code="az",
        )

        self.assertTrue(result["ok"])
        self.assertIn("1. Python-da funksiya nə üçündür?", result["text"])
        self.assertIn("A) Kod blokunu təkrar istifadə etmək", result["text"])
        self.assertIn("Cavab: A", result["text"])
        parsed = parsing.parse_bulk_mcq(result["text"])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["correct"], ["A"])

    @override_settings(GEMINI_API_KEY="test-gemini-key")
    @patch("apps.exams.services.ai_question_generation._call_gemini_text")
    def test_generates_written_questions_in_block_format(self, mock_call_gemini_text):
        mock_call_gemini_text.return_value = """
        {"questions": [{"text": "Dövr operatorunun məqsədini izah edin."}, {"text": "For və while fərqini yazın."}]}
        """

        result = generate_question_bank_text(
            exam_title="Python Midterm",
            exam_type="written",
            prompt_text="Dövr operatorları",
            question_count=2,
            block_name="Bölmə 1",
            language_code="az",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["text"],
            "1. Dövr operatorunun məqsədini izah edin.\n2. For və while fərqini yazın.",
        )


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
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.graded_by_id, self.teacher.id)
        event = self.attempt.grade_events.get()
        self.assertEqual((event.old_score, event.new_score), (None, 8))
        self.assertEqual(event.grader_id, self.teacher.id)

    def test_grade_exam_answer_clamps_to_delivered_maximum(self):
        graded_answer = services.grade_exam_answer(self.answer, 99, self.teacher)

        self.assertEqual(graded_answer.teacher_score, 10)
        self.assertEqual(self.attempt.grade_events.get().max_points, 10)

    def test_calculate_attempt_score(self):
        """Test calculating total attempt score."""
        services.grade_exam_answer(self.answer, 8, self.teacher)

        total_score = services.calculate_attempt_score(self.attempt)

        self.assertEqual(total_score, Decimal("8"))


class ExamQuestionRandomizerServicesTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="randomizer_teacher", email="rt@example.com", password="pass123"
        )
        self.student = User.objects.create_user(
            username="randomizer_student", email="rs@example.com", password="pass123"
        )
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
            ai_difficulty_balance_enabled=False,
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

    def test_generate_random_questions_for_attempt_distributes_remainder_to_first_blocks_by_order(self):
        self.exam.random_question_count = 7
        self.exam.save(update_fields=["random_question_count"])

        blocks = [
            QuestionBlock.objects.create(exam=self.exam, name=f"Block {index + 1}", order=index + 1)
            for index in range(5)
        ]
        for block in blocks:
            for question_index in range(3):
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
        self.assertEqual(len(answers), 7)

        block_counts = {block.id: 0 for block in blocks}
        for answer in answers:
            block_counts[answer.question.block_id] += 1

        ordered_counts = [block_counts[block.id] for block in blocks]
        self.assertEqual(ordered_counts, [2, 2, 1, 1, 1])

    def test_generate_random_questions_for_attempt_gives_extra_question_to_first_block_when_one_remainder(self):
        self.exam.random_question_count = 5
        self.exam.save(update_fields=["random_question_count"])

        blocks = [
            QuestionBlock.objects.create(exam=self.exam, name=f"Block {index + 1}", order=index + 1)
            for index in range(4)
        ]
        for block in blocks:
            for question_index in range(3):
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

        block_counts = {block.id: 0 for block in blocks}
        for answer in answers:
            block_counts[answer.question.block_id] += 1

        ordered_counts = [block_counts[block.id] for block in blocks]
        self.assertEqual(ordered_counts, [2, 1, 1, 1])

    def test_generate_random_questions_for_attempt_avoids_questions_already_seen_by_four_students(self):
        self.exam.random_question_count = 2
        self.exam.fair_question_distribution_enabled = True
        self.exam.save(update_fields=["random_question_count", "fair_question_distribution_enabled"])

        questions = [
            ExamQuestion.objects.create(
                exam=self.exam,
                text=f"Question {index + 1}",
                points=1,
                is_active=True,
            )
            for index in range(6)
        ]
        overused_question_ids = {questions[0].id, questions[1].id}

        for user_index in range(4):
            user = User.objects.create_user(
                username=f"prior_student_{user_index}",
                email=f"prior_student_{user_index}@example.com",
                password="pass123",
            )
            prior_attempt = ExamAttempt.objects.create(
                user=user,
                exam=self.exam,
                attempt_number=1,
                status="submitted",
            )
            for question in questions[:2]:
                ExamAnswer.objects.create(attempt=prior_attempt, question=question)

        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        generate_random_questions_for_attempt(attempt)

        selected_question_ids = set(attempt.answers.values_list("question_id", flat=True))
        self.assertEqual(len(selected_question_ids), 2)
        self.assertTrue(selected_question_ids.isdisjoint(overused_question_ids))

    def test_generate_random_questions_for_attempt_rotates_blocks_when_enough_blocks_exist(self):
        self.exam.random_question_count = 3
        self.exam.fair_question_distribution_enabled = True
        self.exam.save(update_fields=["random_question_count", "fair_question_distribution_enabled"])

        blocks = [
            QuestionBlock.objects.create(exam=self.exam, name=f"Block {index + 1}", order=index + 1)
            for index in range(5)
        ]
        questions = []
        for block in blocks:
            questions.append(
                ExamQuestion.objects.create(
                    exam=self.exam,
                    block=block,
                    text=f"{block.name} Question",
                    points=1,
                    is_active=True,
                )
            )

        prior_attempt = ExamAttempt.objects.create(
            user=User.objects.create_user("prior_block_student", "pbs@example.com", "pass123"),
            exam=self.exam,
            attempt_number=1,
            status="submitted",
        )
        for question in questions[:3]:
            ExamAnswer.objects.create(attempt=prior_attempt, question=question)

        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        generate_random_questions_for_attempt(attempt)

        selected_block_ids = set(
            attempt.answers.select_related("question__block").values_list("question__block_id", flat=True)
        )
        self.assertEqual(len(selected_block_ids), 3)
        self.assertIn(blocks[3].id, selected_block_ids)
        self.assertIn(blocks[4].id, selected_block_ids)

    def test_generate_random_questions_for_attempt_balances_existing_difficulty_levels(self):
        self.exam.random_question_count = 3
        self.exam.ai_difficulty_balance_enabled = True
        self.exam.save(update_fields=["random_question_count", "ai_difficulty_balance_enabled"])

        for difficulty in ("easy", "medium", "hard"):
            for index in range(3):
                ExamQuestion.objects.create(
                    exam=self.exam,
                    text=f"{difficulty} Question {index + 1}",
                    difficulty=difficulty,
                    difficulty_source="ai",
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

        self.assertEqual(
            Counter(attempt.answers.select_related("question").values_list("question__difficulty", flat=True)),
            Counter({"easy": 1, "medium": 1, "hard": 1}),
        )

    @patch("apps.exams.services.difficulty.classify_question_difficulties_with_ai")
    @patch("apps.exams.services.difficulty._get_api_key", return_value="test-key")
    @patch("apps.exams.services.difficulty._is_ai_enabled", return_value=True)
    def test_ensure_ai_question_difficulties_updates_questions(self, _mock_enabled, _mock_key, mock_classify):
        self.exam.ai_difficulty_balance_enabled = True
        self.exam.save(update_fields=["ai_difficulty_balance_enabled"])
        question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Explain a multi-step algorithm.",
            points=1,
            is_active=True,
        )
        mock_classify.return_value = {question.id: "hard"}

        updated_count = ensure_ai_question_difficulties(self.exam)

        self.assertEqual(updated_count, 1)
        question.refresh_from_db()
        self.assertEqual(question.difficulty, "hard")
        self.assertEqual(question.difficulty_source, "ai")
        self.assertIsNotNone(question.difficulty_checked_at)

    @patch("core.tasks.defer")
    def test_schedule_ai_question_difficulty_warmup_only_when_active_and_enabled(self, mock_defer):
        self.exam.is_active = True
        self.exam.ai_difficulty_balance_enabled = False
        self.exam.save(update_fields=["is_active", "ai_difficulty_balance_enabled"])

        self.assertFalse(schedule_ai_question_difficulty_warmup(self.exam))
        mock_defer.assert_not_called()

        self.exam.ai_difficulty_balance_enabled = True
        self.exam.save(update_fields=["ai_difficulty_balance_enabled"])

        self.assertTrue(schedule_ai_question_difficulty_warmup(self.exam))
        mock_defer.assert_called_once()


class ExamSupervisionServicesTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="supervision_teacher",
            email="supervision_teacher@example.com",
            password="pass123",
        )
        self.student = User.objects.create_user(
            username="supervision_student",
            email="supervision_student@example.com",
            password="pass123",
        )
        self.org = Organization.objects.create(
            name="Supervision Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.exam = Exam.objects.create(
            title="Supervision Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
        )

    def test_teacher_stop_attempt_persists_removed_status_and_finishes_attempt(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        teacher_stop_attempt(attempt, self.teacher)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertTrue(attempt.is_finished)
        self.assertIsNotNone(attempt.finished_at)

    def test_monitor_data_includes_exam_without_supervision_config_or_attempts(self):
        data = get_supervision_monitor_data(self.org)

        self.assertIn((self.exam.id, self.exam.title), data["supervised_exams"])
        self.assertIn(self.exam.id, list(data["monitor_exams"].values_list("id", flat=True)))
        self.assertFalse(data["monitor_attempts"].exists())

    def test_monitor_data_includes_attempt_without_violations(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
            supervision_violation_count=0,
        )

        data = get_supervision_monitor_data(self.org)

        self.assertTrue(data["monitor_attempts"].filter(id=attempt.id).exists())

    @override_settings(EXAM_SUPERVISION_ENABLED=False)
    def test_disabled_supervision_does_not_log_lock_or_keep_config_enabled(self):
        config = ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            max_fullscreen_violations=1,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        result = log_supervision_incident(attempt, "fullscreen_exited", {"source": "test"})

        self.assertIsNone(result)
        self.assertFalse(SupervisionIncident.objects.filter(attempt=attempt).exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 0)
        self.assertEqual(attempt.supervision_status, "active")

        status = get_attempt_supervision_status(attempt)
        self.assertFalse(status["supervised"])
        self.assertEqual(status["max_violations"], 0)

        save_supervision_config_from_form(self.exam, {"supervision_enabled": "on"})
        config.refresh_from_db()
        self.assertFalse(config.enabled)

        with self.assertRaises(ValueError):
            teacher_lock_attempt(attempt, self.teacher)

    def test_auto_submit_persists_removed_status_and_finishes_attempt(self):
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            violation_action="auto_submit",
            max_fullscreen_violations=1,
            detect_tab_switch=True,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        result = log_supervision_incident(attempt, "fullscreen_exited", {"source": "test"})

        self.assertEqual(result["action_taken"], "auto_submitted")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertTrue(attempt.is_finished)
        self.assertIsNotNone(attempt.finished_at)

    def test_teacher_resume_attempt_rejects_expired_timed_attempt(self):
        self.exam.total_duration_minutes = 60
        self.exam.save(update_fields=["total_duration_minutes"])
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            recovery_policy="teacher_controlled",
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
            supervision_status="locked",
        )
        attempt.started_at = timezone.now() - timedelta(minutes=61)
        attempt.save(update_fields=["started_at"])

        with self.assertRaises(ValueError):
            teacher_resume_attempt(attempt, self.teacher)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertEqual(attempt.supervision_status, "locked")
        self.assertIsNotNone(attempt.finished_at)

    def _supervised_resumable_exam(self, resume_window_seconds=600):
        self.exam.total_duration_minutes = 600  # long enough to not auto-expire
        self.exam.save(update_fields=["total_duration_minutes"])
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            recovery_policy="teacher_controlled",
            resume_window_seconds=resume_window_seconds,
        )

    def _locked_attempt(self, locked_minutes_ago, number=1, user=None):
        # user parametri: uniq_active_attempt_per_user_exam constraint-i eyni
        # user+exam üçün ikinci in_progress attempt-ə icazə vermir, ona görə
        # paralel aktiv attempt-lər ayrı istifadəçilərlə qurulmalıdır.
        attempt = ExamAttempt.objects.create(
            user=user or self.student,
            exam=self.exam,
            attempt_number=number,
            status="in_progress",
            supervision_status="locked",
        )
        attempt.supervision_locked_at = timezone.now() - timedelta(minutes=locked_minutes_ago)
        attempt.save(update_fields=["supervision_locked_at"])
        return attempt

    def test_lock_action_stamps_locked_at(self):
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            violation_action="lock_exam",
            max_fullscreen_violations=1,
            resume_window_seconds=600,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        result = log_supervision_incident(attempt, "fullscreen_exited", {"source": "test"})

        self.assertEqual(result["action_taken"], "locked")
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")
        self.assertIsNotNone(attempt.supervision_locked_at)
        # Countdown is exposed on the locked attempt.
        self.assertIsNotNone(attempt.supervision_resume_deadline)

    def test_lock_window_auto_finishes_when_teacher_does_not_resume(self):
        self._supervised_resumable_exam(resume_window_seconds=600)
        # Locked 11 minutes ago, window is 10 minutes → should auto-finish.
        attempt = self._locked_attempt(locked_minutes_ago=11)

        finished = attempt.expire_if_resume_window_expired()

        self.assertTrue(finished)
        attempt.refresh_from_db()
        # Submitted (not expired) so the student's current answers are kept.
        self.assertEqual(attempt.status, "submitted")
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertTrue(attempt.is_finished)
        self.assertTrue(attempt.supervision_incidents.filter(event_type="resume_window_expired").exists())

    def test_lock_window_not_expired_when_within_window(self):
        self._supervised_resumable_exam(resume_window_seconds=600)
        attempt = self._locked_attempt(locked_minutes_ago=3)

        finished = attempt.expire_if_resume_window_expired()

        self.assertFalse(finished)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_finished)
        self.assertEqual(attempt.supervision_status, "locked")

    def test_teacher_resume_stops_lock_countdown(self):
        self._supervised_resumable_exam(resume_window_seconds=600)
        attempt = self._locked_attempt(locked_minutes_ago=1)

        teacher_resume_attempt(attempt, self.teacher)

        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertIsNone(attempt.supervision_locked_at)
        # Sweep must not touch a resumed attempt.
        self.assertEqual(sweep_expired_resume_windows(), 0)

    def test_manual_teacher_lock_does_not_start_auto_finish_window(self):
        # A manual teacher pause must never auto-finish, even under a tight
        # resume window — the teacher controls when it ends.
        self._supervised_resumable_exam(resume_window_seconds=300)
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        teacher_lock_attempt(attempt, self.teacher)

        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")
        self.assertTrue(attempt.supervision_manual_lock)
        # No countdown stamped → no auto-finish deadline.
        self.assertIsNone(attempt.supervision_locked_at)
        self.assertIsNone(attempt.supervision_resume_deadline)
        self.assertFalse(attempt.expire_if_resume_window_expired())
        self.assertEqual(sweep_expired_resume_windows(), 0)

    def test_manual_lock_is_resumable_even_with_no_second_chance(self):
        # The recovery policy governs the auto-lock (violation) flow; it must
        # not block a teacher from undoing their own manual pause.
        self.exam.total_duration_minutes = 600
        self.exam.save(update_fields=["total_duration_minutes"])
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            recovery_policy="no_second_chance",
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
            supervision_violation_count=2,
        )

        teacher_lock_attempt(attempt, self.teacher)
        # Should NOT raise despite no_second_chance.
        teacher_resume_attempt(attempt, self.teacher, grant_extra_chance=True)

        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertEqual(attempt.status, "in_progress")
        self.assertFalse(attempt.supervision_manual_lock)
        # Manual-lock resume preserves the violation count (no extra chance).
        self.assertEqual(attempt.supervision_violation_count, 2)
        self.assertEqual(attempt.supervision_extra_chances, 0)

    def test_auto_lock_resume_still_honours_no_second_chance(self):
        # Regression guard: a genuine auto-lock under no_second_chance must
        # still refuse resumption.
        self.exam.total_duration_minutes = 600
        self.exam.save(update_fields=["total_duration_minutes"])
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            recovery_policy="no_second_chance",
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
            supervision_status="locked",
        )
        attempt.supervision_locked_at = timezone.now()
        attempt.save(update_fields=["supervision_locked_at"])

        with self.assertRaises(ValueError):
            teacher_resume_attempt(attempt, self.teacher)

    def test_snapshot_surfaces_coding_draft_files(self):
        # Practical exams keep live work in CodingSubmission, not ExamAnswer.
        # The monitor snapshot must read those draft files so the teacher sees
        # what the student is typing.
        from apps.exams.models import CodingExamQuestion, CodingSubmission

        coding_exam = Exam.objects.create(
            title="Coding Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            exam_type="coding",
        )
        question = ExamQuestion.objects.create(exam=coding_exam, text="Build a page", order=1)
        coding_q = CodingExamQuestion.objects.create(
            question=question,
            language=CodingExamQuestion.LANGUAGE_HTML,
            title="HTML task",
            problem_statement="Make index.html",
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=coding_exam,
            attempt_number=1,
            status="draft",
        )
        CodingSubmission.objects.create(
            student=self.student,
            exam=coding_exam,
            attempt=attempt,
            question=coding_q,
            selected_language=CodingExamQuestion.LANGUAGE_HTML,
            files=[
                {"name": "index.html", "content": "<h1>Hi</h1>"},
                {"name": "style.css", "content": "h1{color:red}"},
            ],
            is_final=False,
        )

        snap = get_attempt_live_snapshot(attempt)

        self.assertEqual(snap["exam_type"], "coding")
        self.assertEqual(len(snap["answers"]), 1)
        row = snap["answers"][0]
        self.assertEqual(row["kind"], "coding")
        names = [f["name"] for f in row["files"]]
        self.assertIn("index.html", names)
        self.assertIn("style.css", names)
        self.assertTrue(row["is_answered"])
        self.assertEqual(snap["answered"], 1)

    def test_snapshot_lists_test_questions_with_selected_options(self):
        test_exam = Exam.objects.create(
            title="Test Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            exam_type="test",
        )
        q = ExamQuestion.objects.create(exam=test_exam, text="2+2?", order=1)
        opt_a = ExamQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        opt_b = ExamQuestionOption.objects.create(question=q, label="B", text="5", is_correct=False)
        q2 = ExamQuestion.objects.create(exam=test_exam, text="Unanswered?", order=2)

        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=test_exam,
            attempt_number=1,
            status="in_progress",
        )
        ans = ExamAnswer.objects.create(attempt=attempt, question=q)
        ans.selected_options.add(opt_a)
        ExamAnswer.objects.create(attempt=attempt, question=q2)

        snap = get_attempt_live_snapshot(attempt)

        self.assertEqual(len(snap["answers"]), 2)
        first = snap["answers"][0]
        self.assertEqual(first["kind"], "test")
        self.assertTrue(first["is_answered"])
        self.assertEqual(first["selected_options"][0]["text"], "4")
        self.assertTrue(first["selected_options"][0]["is_correct"])
        option_flags = {opt["text"]: opt for opt in first["options"]}
        self.assertEqual(set(option_flags), {"4", "5"})
        self.assertTrue(option_flags[opt_a.text]["is_correct"])
        self.assertTrue(option_flags[opt_a.text]["is_selected"])
        self.assertFalse(option_flags[opt_b.text]["is_correct"])
        self.assertFalse(option_flags[opt_b.text]["is_selected"])
        # Second question is shown but flagged unanswered.
        self.assertFalse(snap["answers"][1]["is_answered"])
        self.assertEqual(snap["answered"], 1)

    def test_snapshot_uses_attempt_answer_order_and_omits_unassigned_questions(self):
        test_exam = Exam.objects.create(
            title="Randomized Test Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            exam_type="test",
        )
        q1 = ExamQuestion.objects.create(exam=test_exam, text="Bank first", order=1)
        ExamQuestion.objects.create(exam=test_exam, text="Not assigned", order=2)
        q3 = ExamQuestion.objects.create(exam=test_exam, text="Student first", order=3)

        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=test_exam,
            attempt_number=1,
            status="in_progress",
        )
        ExamAnswer.objects.create(attempt=attempt, question=q3)
        ExamAnswer.objects.create(attempt=attempt, question=q1)

        snap = get_attempt_live_snapshot(attempt)

        self.assertEqual([row["question_text"] for row in snap["answers"]], ["Student first", "Bank first"])
        self.assertEqual(snap["total_questions"], 2)

    def test_sweep_finishes_only_stale_locked_attempts(self):
        self._supervised_resumable_exam(resume_window_seconds=600)
        other_student = User.objects.create_user(
            username="supervision_student2",
            email="supervision_student2@example.com",
            password="pass123",
        )
        stale = self._locked_attempt(locked_minutes_ago=20, number=1)
        fresh = self._locked_attempt(locked_minutes_ago=2, number=1, user=other_student)

        expired = sweep_expired_resume_windows()

        self.assertEqual(expired, 1)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertTrue(stale.is_finished)
        self.assertFalse(fresh.is_finished)

    def test_copy_paste_rightclick_are_logged_but_do_not_count_as_violations(self):
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            violation_action="lock_exam",
            max_fullscreen_violations=2,
            block_copy_paste=True,
            disable_right_click=True,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        for event in ("copy_attempt", "paste_attempt", "cut_attempt", "right_click_attempt"):
            result = log_supervision_incident(attempt, event, {"source": "test"})
            self.assertEqual(result["violation_count"], 0, event)
            self.assertFalse(result["limit_exceeded"], event)

        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 0)
        self.assertEqual(attempt.supervision_status, "active")
        self.assertFalse(attempt.is_finished)
        # The attempts are still recorded for the teacher's audit trail.
        self.assertEqual(attempt.supervision_incidents.count(), 4)

    def test_fullscreen_exit_still_counts_as_violation(self):
        ExamSupervisionConfig.objects.create(
            exam=self.exam,
            enabled=True,
            violation_action="lock_exam",
            max_fullscreen_violations=3,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
        )

        result = log_supervision_incident(attempt, "fullscreen_exited", {"source": "test"})

        self.assertEqual(result["violation_count"], 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 1)

    def test_status_includes_resume_countdown(self):
        from apps.exams.services.supervision import get_attempt_supervision_status

        self._supervised_resumable_exam(resume_window_seconds=600)
        attempt = self._locked_attempt(locked_minutes_ago=2)

        status = get_attempt_supervision_status(attempt)

        self.assertEqual(status["resume_window_seconds"], 600)
        self.assertIsNotNone(status["resume_seconds_remaining"])
        # ~8 minutes left out of 10; allow a small margin.
        self.assertGreater(status["resume_seconds_remaining"], 400)
        self.assertLessEqual(status["resume_seconds_remaining"], 480)

    def test_lock_window_disabled_when_zero(self):
        self._supervised_resumable_exam(resume_window_seconds=0)
        attempt = self._locked_attempt(locked_minutes_ago=300)

        self.assertFalse(attempt.expire_if_resume_window_expired())
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_finished)

    def test_status_reports_manual_lock_even_when_exam_is_not_supervised(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=1,
            status="in_progress",
            supervision_status="locked",
            supervision_manual_lock=True,
        )

        status = get_attempt_supervision_status(attempt)

        self.assertFalse(status["supervised"])
        self.assertTrue(status["manual_lock"])
        self.assertEqual(status["supervision_status"], "locked")
        self.assertEqual(status["config"], {})


class ExamStatisticsAiSummaryServiceTest(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_returns_localized_missing_key_error_in_azerbaijani(self):
        with override("az"):
            result = generate_exam_statistics_summary(
                exam_title="Sınaq",
                exam_type="Test",
                stats={},
            )

        self.assertEqual(
            result,
            {"ok": False, "error": "GEMINI_API_KEY tənzimlənməyib."},
        )

    @override_settings(GEMINI_API_KEY="")
    def test_returns_localized_missing_key_error_in_english(self):
        with override("en"):
            result = generate_exam_statistics_summary(
                exam_title="Trial",
                exam_type="Test",
                stats={},
            )

        self.assertEqual(
            result,
            {"ok": False, "error": "GEMINI_API_KEY is not configured."},
        )


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
    def test_parse_bulk_mcq_supports_end_question_unlabeled_format(self):
        raw = """
        Təsdiq edirəm:
        “Proqramlaşdırma və informasiya təhlükəsizliyi” kafedrasının müdiri
        Semestr: 2025-2026(payız)
        Kibertəhlükəsizlik nəyi ifadə edir?
        İnformasiya sistemlərinin və şəbəkələrinin qorunması
        Rəqəmsal mühitdə xidmətlərin davamlılığının təmin olunması
        İnformasiya resurslarının təhlükəsizlik qaydaları ilə idarə edilməsi
        Elektron sistemlərdə risklərin azaldılmasına yönələn tədbirlər
        Şəbəkə fəaliyyətinin nəzarət mexanizmləri ilə qorunması
        END_QUESTION

        2. Kibercinayət anlayışı hansıdır?
        İnformasiya texnologiyalarından istifadə etməklə törədilən cinayət
        Polis tərəfindən həyata keçirilən əməliyyat
        İnternet üzərindən hüquqi sənədin göndərilməsi
        Elektron məktubun silinməsi
        Şifrənin dəyişdirilməsi
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["text"], "Kibertəhlükəsizlik nəyi ifadə edir?")
        self.assertEqual(parsed[0]["correct"], ["A"])
        self.assertEqual(
            parsed[0]["options"]["E"],
            "Şəbəkə fəaliyyətinin nəzarət mexanizmləri ilə qorunması",
        )
        self.assertEqual(parsed[1]["q_no"], "2")
        self.assertEqual(
            parsed[1]["options"]["A"], "İnformasiya texnologiyalarından istifadə etməklə törədilən cinayət"
        )

    def test_parse_bulk_mcq_end_question_keeps_e_option_separate(self):
        raw = """
        Aşağıdakılardan hansı kibertəhlükə hesab olunur?
        Şəbəkəyə icazəsiz müdaxilə
        Sosial şəbəkədə şəkil paylaşmaq
        Elektron kitab oxumaq
        Online oyun oynamaq
        Kompüterə antivirus yükləmək
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["options"]["E"], "Kompüterə antivirus yükləmək")
        self.assertNotIn("END_QUESTION", parsed[0]["options"]["E"])

    def test_parse_bulk_mcq_end_question_merges_wrapped_unlabeled_option(self):
        raw = """
        İnternet azadlığını qorumaq üçün hansı fəaliyyətlər görülməlidir?
        Hökumətlərin mətbuat və məlumat azadlığını təmin etməsi
        Sadəcə şifrə qoymaq
        Routeri dəyişmək
        Sosial şəbəkələrdə izləyici sayını artırmaq üçün sponsorlu reklamların
        verilməsi və media strategiyasının qurulması
        İnternet provayderlərinin tarif paketlərini yeniləməsi
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(
            parsed[0]["options"]["D"],
            "Sosial şəbəkələrdə izləyici sayını artırmaq üçün sponsorlu reklamların "
            "verilməsi və media strategiyasının qurulması",
        )
        self.assertEqual(parsed[0]["options"]["E"], "İnternet provayderlərinin tarif paketlərini yeniləməsi")

    def test_parse_bulk_mcq_end_question_splits_joined_missing_e_option(self):
        raw = """
        Kriptovalyutaların hüquqi çərçivəsində hansı əsas məsələ mövcuddur?
        Mərkəzsiz fəaliyyətin tənzimlənməsi və cinayətkar fəaliyyətin qarşısının alınması
        Elektron poçtların şifrələnməsi
        Sosial şəbəkələrdə təhqir yayılması
        Şəbəkə xidmətlərinin optimallaşdırılmasıCihazların şəbəkəyə qoşulması
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["options"]["D"], "Şəbəkə xidmətlərinin optimallaşdırılması")
        self.assertEqual(parsed[0]["options"]["E"], "Cihazların şəbəkəyə qoşulması")

    def test_parse_bulk_mcq_end_question_keeps_title_and_prompt_together(self):
        raw = """
        141. google.biz
        Bu tip feyk vebsaytin hazirlanaraq hucum teskil edilmesi hansi hucum novune aiddir:
        CyberSquaiting
        BitSquatting
        Paket manipulyasiyasi
        BitManipulating
        Heç biri
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(
            parsed[0]["text"],
            "google.biz Bu tip feyk vebsaytin hazirlanaraq hucum teskil edilmesi hansi hucum novune aiddir:",
        )
        self.assertEqual(parsed[0]["options"]["A"], "CyberSquaiting")
        self.assertEqual(parsed[0]["options"]["E"], "Heç biri")

    def test_parse_bulk_mcq_end_question_does_not_treat_ip_as_question_number(self):
        raw = """
        449. Aşağıdakı IP localhostun IP-sidir.
        127.0.0.1
        128.0.0.1
        127.1.0.1
        127.1.0.0
        Heç biri
        END_QUESTION
        """

        parsed = parsing.parse_bulk_mcq(raw)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["q_no"], "449")
        self.assertEqual(parsed[0]["text"], "Aşağıdakı IP localhostun IP-sidir.")
        self.assertEqual(parsed[0]["options"]["A"], "127.0.0.1")
        self.assertEqual(parsed[0]["options"]["D"], "127.1.0.0")

    def test_normalize_pdf_extracted_text_keeps_ip_option_intact(self):
        raw = "449. Aşağıdakı IP localhostun IP-sidir. A) 127.0.0.1 B) 128.0.0.1 C) 127.1.0.1 D) 127.1.0.0 Cavab: A"

        normalized = parsing.normalize_pdf_extracted_text(raw)

        self.assertIn("A) 127.0.0.1", normalized)
        self.assertNotIn("\n\n127.0.0.1", normalized)
        self.assertIn("\nB) 128.0.0.1", normalized)

    def test_extract_text_from_upload_reads_pdf_with_pypdf(self):
        uploaded = SimpleUploadedFile("questions.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        fake_page = Mock()
        fake_page.extract_text.return_value = "1) Sual A) Bir B) Iki C) Uc D) Dord Cavab: B"

        with (
            patch.object(parsing, "PdfReader", return_value=SimpleNamespace(pages=[fake_page])) as pdf_reader,
            patch("apps.exams.services.parsing.extraction.pipeline._pdf_safety_check") as safety_check,
        ):
            text = parsing.extract_text_from_upload(uploaded)

        self.assertEqual(text, "1) Sual\nA) Bir\nB) Iki\nC) Uc\nD) Dord\nCavab: B")
        safety_check.assert_called_once_with(uploaded)
        pdf_reader.assert_called_once_with(uploaded)

    def test_extract_text_from_upload_maps_malformed_pdf_to_safe_error(self):
        uploaded = SimpleUploadedFile("broken.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        with self.assertRaises(ValueError) as captured:
            parsing.extract_text_from_upload(uploaded)

        self.assertTrue(str(captured.exception))
        self.assertNotIn("Stream has ended", str(captured.exception))

    def test_extract_text_from_upload_fails_without_pypdf(self):
        uploaded = SimpleUploadedFile("questions.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        with patch.object(parsing, "PdfReader", None):
            with self.assertRaises(ValueError) as exc:
                parsing.extract_text_from_upload(uploaded)

        self.assertIn("pypdf", str(exc.exception))

    def test_extract_text_from_upload_routes_png_to_ocr(self):
        uploaded = SimpleUploadedFile("scan.png", _TINY_PNG_BYTES, content_type="image/png")

        with patch.object(parsing, "_ocr_image_text", return_value="1. Sual?\n*A) bir\nB) iki") as ocr_image:
            text = parsing.extract_text_from_upload(uploaded)

        self.assertIn("*A) bir", text)
        ocr_image.assert_called_once_with(uploaded)

    def test_extract_text_from_upload_rejects_fake_png(self):
        uploaded = SimpleUploadedFile("scan.png", b"not-a-png", content_type="image/png")

        with patch.object(parsing, "_ocr_image_text") as ocr_image:
            with self.assertRaises(ValueError):
                parsing.extract_text_from_upload(uploaded)

        ocr_image.assert_not_called()

    # ---- DOCX importu söndürülüb ------------------------------------------------

    def test_extract_text_from_upload_rejects_docx(self):
        uploaded = SimpleUploadedFile("q.docx", b"PK\x03\x04fake-zip")
        with self.assertRaises(ValueError) as exc:
            parsing.extract_text_from_upload(uploaded)
        self.assertIn("docx", str(exc.exception).lower())

    def test_extract_text_from_upload_rejects_legacy_doc_and_rtf(self):
        for name in ("old.doc", "rich.rtf", "macro.docm"):
            with self.assertRaises(ValueError):
                parsing.extract_text_from_upload(SimpleUploadedFile(name, b"whatever"))

    # ---- Bullet (•) / işarə (√) formatı ----------------------------------------

    def test_parse_bulk_mcq_bullet_and_check_markers(self):
        raw = (
            "1. CI/CD nəyi avtomatlaşdırır?\n"
            "• Sənəd yazılışını\n"
            "√ Build və yerləşdirmə prosesini\n"
            "• Müştəri dəstəyini\n"
            "• Dizayn prosesini\n"
            "• Satış prosesini\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["correct"], ["B"])
        self.assertEqual(parsed[0]["options"]["A"], "Sənəd yazılışını")
        self.assertEqual(parsed[0]["options"]["B"], "Build və yerləşdirmə prosesini")
        self.assertEqual(len(parsed[0]["options"]), 5)

    # ---- END_QUESTION marker variasiyaları (real PDF-lərdən) --------------------

    def test_parse_bulk_mcq_inline_end_question_marker(self):
        """PDF mətn qatında END_QUESTION sonuncu varianta yapışır — ayrılmalıdır."""
        raw = (
            "1. Birinci sual hansıdır?\n"
            "*A) Bir\n"
            "B) İki\n"
            "C) Üç\n"
            "D) Dörd\n"
            "E) Beş END_QUESTION\n"
            "2. İkinci sual hansıdır?\n"
            "A) Alma\n"
            "*B) Armud\n"
            "C) Gilas\n"
            "D) Üzüm\n"
            "E) Nar END_QUESTION\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["correct"], ["A"])
        self.assertEqual(parsed[0]["options"]["E"], "Beş")
        self.assertEqual(parsed[1]["correct"], ["B"])
        self.assertEqual(parsed[1]["options"]["E"], "Nar")

    def test_parse_bulk_mcq_missing_end_question_marker_between_questions(self):
        """Marker unudulmuş sual yeni "N." sətri ilə gizli sərhəddən ayrılır."""
        raw = (
            "1. Birinci sual hansıdır?\n"
            "*A) Bir\n"
            "B) İki\n"
            "C) Üç\n"
            "D) Dörd\n"
            "E) Beş\n"
            "2. Marker yoxdur, amma yeni sualdır?\n"
            "A) Alma\n"
            "*B) Armud\n"
            "C) Gilas\n"
            "D) Üzüm\n"
            "E) Nar\n"
            "END_QUESTION\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["text"], "Birinci sual hansıdır?")
        self.assertEqual(parsed[1]["text"], "Marker yoxdur, amma yeni sualdır?")
        self.assertEqual(parsed[1]["correct"], ["B"])

    # ---- Düzgün cavab işarəsi tapılmayanda default "A" xəbərdarlığı -------------

    def test_parse_bulk_mcq_defaulted_correct_emits_error_warning(self):
        raw = "1. Paytaxt hansıdır?\n" "A) Bakı\n" "B) Gəncə\n" "C) Sumqayıt\n" "D) Şəki\n" "E) Lənkəran\n"
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["correct"], ["A"])
        defaulted = [w for w in parsed[0]["warnings"] if w["type"] == "correct_defaulted"]
        self.assertEqual(len(defaulted), 1)
        self.assertEqual(defaulted[0]["severity"], "error")

    def test_parse_bulk_mcq_marked_correct_has_no_defaulted_warning(self):
        raw = "1. Paytaxt hansıdır?\n" "*A) Bakı\n" "B) Gəncə\n" "C) Sumqayıt\n" "D) Şəki\n" "E) Lənkəran\n"
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["correct"], ["A"])
        self.assertEqual([w for w in parsed[0]["warnings"] if w["type"] == "correct_defaulted"], [])

    def test_parse_bulk_mcq_bare_question_number_line_merged(self):
        raw = (
            "350.\n"
            "Bir çox veb proqramlar üçün hansı prinsip\n"
            "uyğundur?\n"
            "• Minimum güzəşt prinsipi\n"
            "√ Xidmətlərə etibar edilməməsi prinsipi\n"
            "• Dərinlik müdafiə prinsipi\n"
            "• Vəzifələrin bölünməsi prinsipi\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["q_no"], "350")
        self.assertIn("Bir çox veb proqramlar", parsed[0]["text"])
        self.assertEqual(parsed[0]["correct"], ["B"])

    # ---- Kiril (rus) variant etiketləri -----------------------------------------

    def test_parse_bulk_mcq_cyrillic_sequential_labels(self):
        raw = (
            "1. Что такое CI/CD?\n"
            "А) вариант один\n"
            "Б) вариант два\n"
            "В) вариант три\n"
            "Г) вариант четыре\n"
            "Ответ: Б\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(list(parsed[0]["options"]), ["A", "B", "C", "D"])
        self.assertEqual(parsed[0]["correct"], ["B"])

    def test_parse_bulk_mcq_cyrillic_lookalike_labels(self):
        raw = (
            "1. Какой язык программирования?\n"
            "А) Питон\n"
            "В) Ворд\n"
            "С) Эксель\n"
            "Д) Хром\n"
            "Е) Файрфокс\n"
            "Ответ: А\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(list(parsed[0]["options"]), ["A", "B", "C", "D", "E"])
        self.assertEqual(parsed[0]["correct"], ["A"])

    def test_parse_bulk_mcq_multilang_answer_lines(self):
        raw = (
            "1. Which is a language?\n"
            "A) Word\nB) Python\nC) Excel\nD) Chrome\n"
            "Answer: B\n"
            "\n"
            "2. Hangisi bir dildir?\n"
            "A) Word\nB) Python\nC) Excel\nD) Chrome\n"
            "Cevap: B\n"
        )
        parsed = parsing.parse_bulk_mcq(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["correct"], ["B"])
        self.assertEqual(parsed[1]["correct"], ["B"])

    def test_mark_correct_option_lines_label_match_no_false_positive(self):
        text = "1) Sual?\nA) hesabi nisbət\nB) nisbət\nC) hesabi\nD) indeks"
        # "B) nisbət" highlight olunub — yalnız B işarələnməli, A yox (mətn oxşardır)
        marked = parsing._mark_correct_option_lines(text, ["B) nisbət"])
        self.assertIn("*B) nisbət", marked)
        self.assertNotIn("*A)", marked)

    def test_mark_correct_option_lines_empty_fragments_unchanged(self):
        text = "A) bir\nB) iki"
        self.assertEqual(parsing._mark_correct_option_lines(text, []), text)

    def test_extract_pdf_highlights_safe_on_invalid_bytes(self):
        uploaded = SimpleUploadedFile("bad.pdf", b"%PDF-1.4 not-a-real-pdf")
        # Heç vaxt exception atmamalı — boş siyahı qaytarmalı
        self.assertEqual(parsing._extract_pdf_highlights(uploaded), [])

    @skipUnless(parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb")
    def test_extract_text_from_upload_marks_highlighted_pdf_option(self):
        fitz = parsing.fitz
        doc = fitz.open()
        page = doc.new_page()
        lines = [
            "1. Massivler uzerinde hansi emeliyyat?",
            "A) hesabi/nisbet",
            "B) nisbet",
            "C) hesabi",
            "D) indekslesme",
            "E) mentiqi",
        ]
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=12)
            y += 24
        for rect in page.search_for("D) indekslesme"):
            page.add_highlight_annot(rect)
        data = doc.tobytes()
        doc.close()

        text = parsing.extract_text_from_upload(SimpleUploadedFile("q.pdf", data))
        self.assertIn("*D) indekslesme", text)
        self.assertNotIn("*A)", text)

        parsed = parsing.parse_bulk_mcq(text)
        self.assertEqual(parsed[0]["correct"], ["D"])

    @skipUnless(parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb")
    def test_highlight_is_scoped_per_question_no_cross_contamination(self):
        """
        REQRESSİYA: əvvəllər highlight YALNIZ etiketə görə qlobal uyğunlaşdırılırdı,
        ona görə sənəddə bir yerdə "A)" düzgün olanda HƏR sualın A-sı işarələnirdi
        (parser default "A"-ya düşürdü). İndi mövqe əsaslıdır: Q1-də A, Q2-də C
        işarələnəndə Q2-yə A, Q1-ə C sızmamalıdır.
        """
        fitz = parsing.fitz
        doc = fitz.open()
        page = doc.new_page()
        rows = [
            "1. Birinci sual?",
            "A) duzgun bir",
            "B) yanlis bir",
            "C) yanlis iki",
            "D) yanlis uc",
            "2. Ikinci sual?",
            "A) yanlis dord",
            "B) yanlis bes",
            "C) duzgun iki",
            "D) yanlis alti",
        ]
        y = 72
        for line in rows:
            page.insert_text((72, y), line, fontsize=12)
            y += 22
        for rect in page.search_for("A) duzgun bir"):
            page.add_highlight_annot(rect)
        for rect in page.search_for("C) duzgun iki"):
            page.add_highlight_annot(rect)
        data = doc.tobytes()
        doc.close()

        text = parsing.extract_text_from_upload(SimpleUploadedFile("q.pdf", data))
        parsed = parsing.parse_bulk_mcq(text)
        self.assertEqual(parsed[0]["correct"], ["A"])
        self.assertEqual(parsed[1]["correct"], ["C"])
        # Q2 A işarələnməyib (qlobal sızma olmayıb)
        self.assertNotIn("*A) yanlis dord", text)

    # ---- Skan edilmiş (şəkil əsaslı) PDF + OCR --------------------------------

    @staticmethod
    def _build_scanned_pdf(lines):
        """Mətni şəkilə çevirib mətn qatı OLMAYAN (skan kimi) PDF qaytarır."""
        fitz = parsing.fitz
        # 1) Mətnli müvəqqəti səhifə → pixmap (şəkil)
        src = fitz.open()
        page = src.new_page()
        y = 60
        for line in lines:
            page.insert_text((50, y), line, fontsize=14)
            y += 26
        pix = page.get_pixmap(dpi=200)
        png = pix.tobytes("png")
        src.close()
        # 2) Şəkli yeni PDF-ə yerləşdir → mətn qatı yoxdur
        out = fitz.open()
        opage = out.new_page(width=pix.width, height=pix.height)
        opage.insert_image(opage.rect, stream=png)
        data = out.tobytes()
        out.close()
        return data

    @staticmethod
    def _ocr_available():
        if parsing.fitz is None:
            return False
        try:
            doc = parsing.fitz.open()
            page = doc.new_page()
            page.insert_text((20, 20), "test", fontsize=12)
            page.get_textpage_ocr(full=True, language="eng", dpi=72)
            doc.close()
            return True
        except Exception:
            return False

    @skipUnless(parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb")
    @override_settings(EXAM_PDF_OCR_ENABLED=False)
    def test_scanned_pdf_without_text_raises_clear_error_when_ocr_disabled(self):
        data = self._build_scanned_pdf(["1. Sual?", "A) bir", "B) iki", "C) uc", "D) dord"])
        # Mətn qatı yoxdur (skan); OCR deaktivdir → aydın xəta atılmalıdır.
        self.assertIs(parsing._pdf_has_text_layer(SimpleUploadedFile("scan.pdf", data)), False)
        with self.assertRaises(ValueError) as exc:
            parsing.extract_text_from_upload(SimpleUploadedFile("scan.pdf", data))
        # Tərcümədən asılı olmadan düzgün msgid-in (pdf_no_text_layer) atıldığını yoxlayırıq.
        # LANGUAGE_CODE="az" altında pgettext açarı tərcümə edir, ona görə literal açar
        # sözü deyil, msgid-in real dəyəri ilə müqayisə edirik.
        expected_message = pgettext("exams.service.parsing.error", "pdf_no_text_layer")
        self.assertEqual(str(exc.exception), expected_message)

    @override_settings(EXAM_PDF_OCR_ENABLED=True, EXAM_PDF_OCR_LANG="eng", EXAM_PDF_OCR_MAX_PAGES=2)
    def test_ocr_extracts_questions_from_scanned_pdf(self):
        if not self._ocr_available():
            self.skipTest("Tesseract OCR mövcud deyil (sistemdə tesseract-ocr quraşdırılmayıb)")
        data = self._build_scanned_pdf(
            [
                "1. Massivler uzerinde hansi emeliyyat?",
                "A) hesabi",
                "B) nisbet",
                "C) indeks",
                "D) mentiqi",
            ]
        )
        text = parsing.extract_text_from_upload(SimpleUploadedFile("scan.pdf", data))
        self.assertTrue(text.strip(), "OCR mətn qaytarmalıdır")
        parsed = parsing.parse_bulk_mcq(text)
        self.assertGreaterEqual(len(parsed), 1)
        self.assertIn("A", parsed[0]["options"])

    def test_yellow_highlight_mask_detects_region(self):
        """
        Skan PDF-də düz cavabın aşkarı üçün sarı maska məntiqi (OCR-dan asılı deyil).
        """
        from PIL import Image

        img = Image.new("RGB", (120, 80), (255, 255, 255))
        for x in range(20, 90):
            for y in range(15, 45):
                img.putpixel((x, y), (255, 235, 40))  # sarı highlight bloku

        mask = parsing._build_yellow_mask(img)
        # Sarı bloğun içində nisbət yüksək, ağ sahədə ~0 olmalıdır.
        self.assertGreater(parsing._line_yellow_ratio(mask, (20, 15, 90, 45)), 0.8)
        self.assertEqual(parsing._line_yellow_ratio(mask, (95, 50, 120, 80)), 0.0)
        self.assertEqual(parsing._line_yellow_ratio(mask, (5, 5, 5, 5)), 0.0)


class ExamParsingOcrHighlightHelperTest(SimpleTestCase):
    @staticmethod
    def _ocr_page_text_from_words(words, yellow_rects, *, width=260, height=160):
        import io

        from PIL import Image, ImageDraw

        img = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        for rect in yellow_rects:
            draw.rectangle(rect, fill=(255, 235, 40))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        class Pix:
            def tobytes(self, image_format):
                return png_bytes

        class Page:
            def get_text(self, mode=None, **kwargs):
                if mode == "words":
                    return words
                return ""

            def get_pixmap(self, dpi=None):
                return Pix()

        return parsing._ocr_page_text_with_highlights(Page(), object(), 1.0, True, 0.10, Image, 72)

    def test_ocr_page_text_marks_option_when_only_answer_word_is_yellow(self):
        words = [
            (10, 10, 20, 22, "1.", 0, 0, 0),
            (24, 10, 74, 22, "Sual?", 0, 0, 1),
            (10, 35, 24, 48, "A)", 0, 1, 0),
            (30, 35, 58, 48, "bir", 0, 1, 1),
            (10, 60, 24, 73, "D)", 0, 2, 0),
            (30, 60, 100, 73, "indekslesme", 0, 2, 1),
        ]

        text = self._ocr_page_text_from_words(words, [(30, 58, 100, 75)])

        self.assertIn("*D) indekslesme", text)
        self.assertNotIn("*A)", text)

    def test_ocr_page_text_marks_option_from_highlighted_continuation_line(self):
        words = [
            (10, 10, 20, 22, "1.", 0, 0, 0),
            (24, 10, 74, 22, "Sual?", 0, 0, 1),
            (10, 35, 24, 48, "A)", 0, 1, 0),
            (30, 35, 58, 48, "bir", 0, 1, 1),
            (10, 60, 24, 73, "B)", 0, 2, 0),
            (30, 60, 105, 73, "uzun", 0, 2, 1),
            (10, 85, 120, 98, "davam", 0, 3, 0),
            (126, 85, 170, 98, "hisse", 0, 3, 1),
            (10, 110, 24, 123, "C)", 0, 4, 0),
            (30, 110, 48, 123, "uc", 0, 4, 1),
            (10, 135, 24, 148, "D)", 0, 5, 0),
            (30, 135, 60, 148, "dord", 0, 5, 1),
        ]

        text = self._ocr_page_text_from_words(words, [(10, 82, 170, 101)], height=180)
        parsed = parsing.parse_bulk_mcq(text)

        self.assertIn("*B) uzun", text)
        self.assertEqual(parsed[0]["correct"], ["B"])


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

    def test_bulk_grade_answers_pairs_score_to_correct_answer(self):
        """Regression: hər bal id üzrə düzgün cavaba yazılmalıdır, DB sırasından asılı olmayaraq."""
        from apps.exams.services.grading import bulk_grade_answers

        answer2 = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=ExamQuestion.objects.create(exam=self.exam, text="Q2?", points=5, order=2),
        )
        # answer_ids-i qəsdən tərs sıra ilə veririk; xəritə əsaslı uyğunlaşdırma
        # hər balı öz id-sinə bağlamalıdır.
        bulk_grade_answers([answer2.id, self.answer.id], [7, 5])
        self.answer.refresh_from_db()
        answer2.refresh_from_db()
        self.assertEqual(self.answer.teacher_score, 5)
        self.assertEqual(answer2.teacher_score, 5)

    def test_grade_exam_answer_rounds_half_up_instead_of_truncating(self):
        """Kəsr bal səssizcə kəsilmir, ən yaxına yuvarlaqlaşdırılır (integer sahə)."""
        from decimal import Decimal

        from apps.exams.services.grading import grade_exam_answer

        result = grade_exam_answer(self.answer, Decimal("2.5"))
        self.assertEqual(result.teacher_score, 3)

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

    def test_calculate_test_attempt_result_uses_delivered_answers_only(self):
        from apps.exams.services.result_calculation import calculate_test_attempt_result

        for idx in range(4, 24):
            ExamQuestion.objects.create(exam=self.exam, text=f"Bank only {idx}", points=1, order=idx)

        ExamQuestionOption.objects.create(question=self.question, text="Yes", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, text="No", is_correct=False)

        correct_question = ExamQuestion.objects.create(exam=self.exam, text="Delivered correct", points=2, order=2)
        correct_answer_option = ExamQuestionOption.objects.create(
            question=correct_question,
            text="Correct",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(question=correct_question, text="Wrong", is_correct=False)
        correct_answer = ExamAnswer.objects.create(attempt=self.attempt, question=correct_question)
        correct_answer.selected_options.add(correct_answer_option)

        wrong_question = ExamQuestion.objects.create(exam=self.exam, text="Delivered wrong", points=3, order=3)
        ExamQuestionOption.objects.create(question=wrong_question, text="Correct", is_correct=True)
        wrong_answer_option = ExamQuestionOption.objects.create(question=wrong_question, text="Wrong", is_correct=False)
        wrong_answer = ExamAnswer.objects.create(attempt=self.attempt, question=wrong_question)
        wrong_answer.selected_options.add(wrong_answer_option)

        result = calculate_test_attempt_result(self.attempt)

        self.assertEqual(self.exam.questions.count(), 23)
        self.assertEqual(result.delivered_count, 3)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.wrong_count, 1)
        self.assertEqual(result.unanswered_count, 1)
        self.assertEqual(result.score, Decimal("2"))
        self.assertEqual(result.max_score, Decimal("15"))
        self.assertEqual(result.percentage, Decimal("13.3"))

        self.attempt.recalculate_score()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.correct_count, 1)
        self.assertEqual(self.attempt.wrong_count, 1)

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


class AttachTestResultSummariesQueryTests(TestCase):
    """Faza 4 (audit 2026-07-02): attach_test_result_summaries N+1 reqressiyası.

    Sorğu sayı attempt SAYINDAN ASILI OLMAMALIDIR: bütün cavablar tək
    queryset (base + 2 prefetch) ilə yığılır, bonus map onsuz da toplu idi.
    Köhnə davranış 3 attempt üçün ~9-10 sorğu edirdi.
    """

    def setUp(self):
        self.teacher = User.objects.create_user(username="attach_t", email="attach_t@example.com", password="pass123")
        self.student = User.objects.create_user(username="attach_s", email="attach_s@example.com", password="pass123")
        self.org = Organization.objects.create(
            name="Attach Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Attach Test Exam",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            exam_type="test",
        )
        self.questions = []
        self.correct_options = {}
        for i in range(2):
            question = ExamQuestion.objects.create(exam=self.exam, text=f"Q{i}", points=1)
            correct = ExamQuestionOption.objects.create(question=question, label="A", text="düz", is_correct=True)
            ExamQuestionOption.objects.create(question=question, label="B", text="səhv", is_correct=False)
            self.questions.append(question)
            self.correct_options[question.id] = correct

        self.attempts = []
        for attempt_number in range(1, 4):
            attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                attempt_number=attempt_number,
                status="submitted",
            )
            for question in self.questions:
                answer = ExamAnswer.objects.create(attempt=attempt, question=question)
                answer.selected_options.set([self.correct_options[question.id]])
            self.attempts.append(attempt)

    def test_query_count_is_independent_of_attempt_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.exams.services.result_calculation import attach_test_result_summaries

        attempts = list(ExamAttempt.objects.filter(exam=self.exam).select_related("exam").order_by("attempt_number"))
        self.assertEqual(len(attempts), 3)

        with CaptureQueriesContext(connection) as ctx:
            attach_test_result_summaries(attempts)

        # 1 answers + 2 prefetch + ≤2 bonus-map sorğusu — attempt sayına görə BÖYÜMÜR.
        self.assertLessEqual(len(ctx), 5, f"Gözləniləndən çox sorğu: {len(ctx)}")

        for attempt in attempts:
            self.assertEqual(attempt.test_result.correct_count, 2)
            self.assertEqual(attempt.test_result.delivered_count, 2)
            self.assertEqual(attempt.test_result.wrong_count, 0)

    def test_attempt_without_answers_falls_back_to_legacy(self):
        from apps.exams.services.result_calculation import attach_test_result_summaries

        bare_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            attempt_number=99,
            status="submitted",
        )
        bare_attempt.correct_count = 4
        bare_attempt.wrong_count = 1

        attach_test_result_summaries([bare_attempt])

        self.assertTrue(bare_attempt.test_result.used_legacy_fallback)
        self.assertEqual(bare_attempt.test_result.correct_count, 4)
