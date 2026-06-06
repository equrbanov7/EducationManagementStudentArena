"""
Çoxdilli imtahan testləri (Faza 6).

Əhatə edir:
- dil variantı yaratma / mövcud dillərin siyahısı,
- yalnız aktiv + sualı olan dillərin "mövcud" sayılması,
- attempt-in dilinə görə randomizer scope-u (yalnız seçilmiş dilin sualları),
- variant override ilə effektiv sual sayı.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamAttempt, ExamLanguageVariant, ExamQuestion, ExamQuestionOption
from apps.exams.services import language_variants as lv
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MultiLanguageExamTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("lv_teacher", "lv_teacher@example.com", "pw")
        self.student = User.objects.create_user("lv_student", "lv_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="LV Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.exam = Exam.objects.create(
            title="Multi-lang Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            random_question_count=10,
        )

    def _question(self, *, order, language, correct_label="A"):
        q = ExamQuestion.objects.create(exam=self.exam, order=order, text=f"Q{order}-{language}", language=language)
        for label in ("A", "B"):
            ExamQuestionOption.objects.create(
                question=q, label=label, text=f"opt-{label}", is_correct=(label == correct_label)
            )
        return q

    # ── available languages ────────────────────────────────────────────
    def test_available_languages_lists_only_active_variants_with_questions(self):
        ExamLanguageVariant.objects.create(exam=self.exam, language="az", is_active=True)
        ExamLanguageVariant.objects.create(exam=self.exam, language="ru", is_active=True)
        # 'en' variant exists but inactive → excluded.
        ExamLanguageVariant.objects.create(exam=self.exam, language="en", is_active=False)
        self._question(order=1, language="az")
        self._question(order=2, language="ru")
        # az + ru have questions and are active.

        options = lv.available_language_options(self.exam)
        languages = {opt["language"] for opt in options}
        self.assertEqual(languages, {"az", "ru"})
        self.assertTrue(lv.exam_is_multilingual(self.exam))

    def test_language_with_no_questions_is_not_offered(self):
        ExamLanguageVariant.objects.create(exam=self.exam, language="az", is_active=True)
        ExamLanguageVariant.objects.create(exam=self.exam, language="ru", is_active=True)
        self._question(order=1, language="az")  # only az has questions
        options = lv.available_language_options(self.exam)
        self.assertEqual([opt["language"] for opt in options], ["az"])
        self.assertFalse(lv.exam_is_multilingual(self.exam))

    def test_resolve_requested_language_validates_against_available(self):
        ExamLanguageVariant.objects.create(exam=self.exam, language="az", is_active=True)
        self._question(order=1, language="az")
        self.assertEqual(lv.resolve_requested_language(self.exam, "az"), "az")
        self.assertIsNone(lv.resolve_requested_language(self.exam, "ru"))
        self.assertIsNone(lv.resolve_requested_language(self.exam, ""))

    # ── randomizer scoping ─────────────────────────────────────────────
    def test_randomizer_delivers_only_selected_language_questions(self):
        ExamLanguageVariant.objects.create(exam=self.exam, language="az", is_active=True)
        variant_ru = ExamLanguageVariant.objects.create(exam=self.exam, language="ru", is_active=True)
        for i in range(1, 4):
            self._question(order=i, language="az")
        for i in range(4, 7):
            self._question(order=i, language="ru")

        attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", language="ru", language_variant=variant_ru
        )
        generate_random_questions_for_attempt(attempt)

        delivered_languages = set(attempt.answers.values_list("question__language", flat=True))
        self.assertEqual(delivered_languages, {"ru"})
        self.assertEqual(attempt.answers.count(), 3)

    def test_randomizer_without_language_delivers_all(self):
        # Tək-dilli/legacy: attempt.language boşdursa filtr yoxdur.
        for i in range(1, 4):
            self._question(order=i, language="az")
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        generate_random_questions_for_attempt(attempt)
        self.assertEqual(attempt.answers.count(), 3)

    # ── effective question count (variant override) ────────────────────
    def test_effective_needed_count_uses_variant_override(self):
        variant = ExamLanguageVariant.objects.create(
            exam=self.exam, language="az", is_active=True, question_count_override=2
        )
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", language="az", language_variant=variant
        )
        self.assertEqual(lv.effective_needed_count_for_attempt(attempt), 2)

    def test_effective_needed_count_falls_back_to_exam(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        # exam.random_question_count = 10
        self.assertEqual(lv.effective_needed_count_for_attempt(attempt), 10)
