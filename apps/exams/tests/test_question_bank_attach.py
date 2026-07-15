"""
Sual bankı kitabxanası + snapshot attach testləri (Faza 6).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamLanguageVariant, QuestionBank
from apps.exams.services.question_bank_attach import (
    accessible_banks,
    attach_bank_questions_to_exam,
    create_bank_questions_from_parsed,
)
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _parsed(text, correct="B"):
    return {
        "text": text,
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "correct": [correct],
        "answer_mode": "single",
    }


class QuestionBankLibraryTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("qb_teacher", "qb_teacher@example.com", "pw")
        self.org = Organization.objects.create(
            name="QB Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        self.bank = QuestionBank.objects.create(
            name="Bank 1", created_by=self.teacher, organization=self.org, language="az"
        )
        self.exam = Exam.objects.create(
            title="QB Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )

    def test_create_bank_questions_from_parsed(self):
        created = create_bank_questions_from_parsed(
            self.bank, [_parsed("Q1"), _parsed("Q2", correct="A")], language="az", created_by=self.teacher
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(self.bank.library_questions.count(), 2)
        first = created[0]
        self.assertEqual(first.options.count(), 4)
        self.assertEqual(set(first.options.filter(is_correct=True).values_list("label", flat=True)), {"B"})

    def test_exam_center_user_sees_only_own_banks(self):
        """#10: imtahan mərkəzi istifadəçisi YALNIZ öz yaratdığı bankları görür —
        başqa istifadəçinin eyni təşkilatda paylaşdığı bankı yox."""
        from unittest.mock import patch

        other = User.objects.create_user("qb_other", "qb_other@example.com", "pw")
        shared_by_other = QuestionBank.objects.create(
            name="Shared", created_by=other, organization=self.org, language="az", is_shared=True
        )
        own_shared = QuestionBank.objects.create(
            name="Own", created_by=self.teacher, organization=self.org, language="az", is_shared=True
        )

        # Adi istifadəçi (teacher rolu): öz + paylaşılan hamısını görür.
        seen = set(accessible_banks(self.teacher, self.org).values_list("id", flat=True))
        self.assertIn(shared_by_other.id, seen)
        self.assertIn(own_shared.id, seen)

        # İmtahan mərkəzi istifadəçisi: yalnız öz banklarını görür.
        with patch("apps.exams.services.access_policy.is_exam_center_user", return_value=True):
            ec_seen = set(accessible_banks(self.teacher, self.org).values_list("id", flat=True))
        self.assertIn(own_shared.id, ec_seen)
        self.assertIn(self.bank.id, ec_seen)
        self.assertNotIn(shared_by_other.id, ec_seen)

    def test_attach_snapshots_questions_into_exam(self):
        bank_questions = create_bank_questions_from_parsed(
            self.bank, [_parsed("Q1"), _parsed("Q2")], language="ru", created_by=self.teacher
        )
        ids = [bq.id for bq in bank_questions]

        created = attach_bank_questions_to_exam(self.exam, ids, created_by=self.teacher)

        self.assertEqual(len(created), 2)
        self.assertEqual(self.exam.questions.count(), 2)
        eq = created[0]
        # Snapshot link + content copied.
        self.assertEqual(eq.source_bank_question_id, bank_questions[0].id)
        self.assertEqual(eq.language, "ru")
        self.assertEqual(eq.options.count(), 4)
        # Dilə uyğun variant avtomatik yaranmalıdır.
        self.assertTrue(ExamLanguageVariant.objects.filter(exam=self.exam, language="ru").exists())
        self.assertEqual(eq.language_variant.language, "ru")

    def test_attach_is_independent_of_bank_edits(self):
        bank_questions = create_bank_questions_from_parsed(self.bank, [_parsed("Original")], language="az")
        attach_bank_questions_to_exam(self.exam, [bank_questions[0].id])
        # Bank sualını dəyiş — imtahandakı snapshot DƏYIŞMƏMƏLİDİR.
        bank_questions[0].text = "Edited later"
        bank_questions[0].save(update_fields=["text"])

        exam_question = self.exam.questions.first()
        self.assertEqual(exam_question.text, "Original")


class AccessibleBanksTests(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user("ab_owner_a", "ab_a@example.com", "pw")
        self.other_a = User.objects.create_user("ab_other_a", "ab_o@example.com", "pw")
        self.owner_b = User.objects.create_user("ab_owner_b", "ab_b@example.com", "pw")
        self.org_a = Organization.objects.create(
            name="Org A", org_type=OrganizationType.UNIVERSITY, owner=self.owner_a, status="active", is_active=True
        )
        self.org_b = Organization.objects.create(
            name="Org B", org_type=OrganizationType.UNIVERSITY, owner=self.owner_b, status="active", is_active=True
        )
        self.own_bank = QuestionBank.objects.create(name="own", created_by=self.owner_a, organization=self.org_a)
        self.shared_a = QuestionBank.objects.create(
            name="shared-a", created_by=self.other_a, organization=self.org_a, is_shared=True
        )
        self.private_a = QuestionBank.objects.create(
            name="private-a", created_by=self.other_a, organization=self.org_a, is_shared=False
        )
        self.shared_b = QuestionBank.objects.create(
            name="shared-b", created_by=self.owner_b, organization=self.org_b, is_shared=True
        )

    def test_user_sees_own_and_shared_within_org_only(self):
        visible = set(accessible_banks(self.owner_a, self.org_a).values_list("name", flat=True))
        self.assertIn("own", visible)
        self.assertIn("shared-a", visible)
        # Başqasının paylaşılmamış bankı görünmür.
        self.assertNotIn("private-a", visible)
        # Başqa təşkilatın bankı görünmür (tenant izolyasiyası).
        self.assertNotIn("shared-b", visible)
