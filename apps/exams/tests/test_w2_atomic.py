"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: sual bankı / imtahan
sualı view-lərinin çoxyazılı budaqları ``transaction.atomic`` içindədir.

* `question_bank_detail` toplu silmə: silmə + audit qeydi;
* `bank_question_add`: sual + variantlar;
* `add_exam_question`: sual + variantlar.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import BankQuestion, BankQuestionOption, Exam, ExamQuestion, ExamQuestionOption, QuestionBank
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
PW = "W2AtomicPass123!"


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w2ex_teacher", "w2ex_teacher@example.com", PW)
        self.org = Organization.objects.create(
            name="W2 Exams Org",
            slug="w2-exams-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.create(
            user=self.teacher, organization=self.org, role=self.org.roles.get(name="teacher"), is_primary=True
        )
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()


class QuestionBankBulkDeleteAtomicTest(_Base):
    def setUp(self):
        super().setUp()
        self.bank = QuestionBank.objects.create(name="W2 Bank", organization=self.org, created_by=self.teacher)
        self.question = BankQuestion.objects.create(bank=self.bank, text="Silinəcək sual", question_type="test")
        self.url = reverse("exams:question_bank_detail", kwargs={"bank_id": self.bank.id})

    def test_audit_failure_rolls_back_the_delete(self):
        with mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("audit boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, {"bulk_action": "delete", "selected_question_ids": [str(self.question.id)]})
        self.assertTrue(BankQuestion.objects.filter(pk=self.question.pk).exists())

    def test_language_delete_audit_failure_rolls_back(self):
        with mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("audit boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, {"bulk_action": "delete_language", "language": "az"})
        self.assertTrue(BankQuestion.objects.filter(pk=self.question.pk).exists())

    def test_happy_path_deletes_and_audits(self):
        response = self.client.post(
            self.url, {"bulk_action": "delete", "selected_question_ids": [str(self.question.id)]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BankQuestion.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(AuditLog.objects.filter(resource_type="exams.QuestionBank", action="delete").exists())


class BankQuestionAddAtomicTest(_Base):
    def setUp(self):
        super().setUp()
        self.bank = QuestionBank.objects.create(name="W2 Bank 2", organization=self.org, created_by=self.teacher)
        self.url = reverse("exams:bank_question_add", kwargs={"bank_id": self.bank.id})
        self.payload = {
            "q_format": "test",
            "text": "Variantlı sual?",
            "language": "az",
            "difficulty": "medium",
            "points": "1",
            "answer_mode": "single",
            "option1_text": "Doğru",
            "option1_is_correct": "on",
            "option2_text": "Yanlış",
        }

    def test_option_failure_rolls_back_the_question(self):
        with mock.patch.object(BankQuestionOption.objects, "create", side_effect=RuntimeError("option boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.payload)
        self.assertFalse(BankQuestion.objects.filter(bank=self.bank).exists())

    def test_happy_path_writes_question_and_options(self):
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        question = BankQuestion.objects.get(bank=self.bank)
        self.assertEqual(question.options.count(), 2)


class AddExamQuestionAtomicTest(_Base):
    def setUp(self):
        super().setUp()
        self.exam = Exam.objects.create(author=self.teacher, title="W2 Exam", is_active=True, organization=self.org)
        self.url = reverse("exams:add_exam_question", kwargs={"slug": self.exam.slug}) + "?modal=1"
        self.payload = {
            "modal": "1",
            "text": "İmtahan sualı?",
            "answer_mode": "single",
            "time_limit_seconds": "60",
            "option1_text": "Doğru",
            "option1_is_correct": "on",
            "option2_text": "Yanlış",
        }

    def _post(self):
        return self.client.post(self.url, self.payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_option_failure_rolls_back_the_question(self):
        with mock.patch.object(ExamQuestionOption.objects, "create", side_effect=RuntimeError("option boom")):
            with self.assertRaises(RuntimeError):
                self._post()
        self.assertFalse(ExamQuestion.objects.filter(exam=self.exam).exists())

    def test_happy_path_writes_question_and_options(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["success"])
        question = ExamQuestion.objects.get(exam=self.exam)
        self.assertEqual(question.options.count(), 2)
