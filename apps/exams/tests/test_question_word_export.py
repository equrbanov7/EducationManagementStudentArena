"""
Sual bankı və imtahan suallarının Word (.docx) export testləri.

Yoxlanılır:
* Export servisi düz cavabı `*` prefiksi ilə işarələyir (round-trip format).
* Bank export view-u sahib müəllim üçün .docx qaytarır.
* Başqa təşkilatın müəllimi bankı export edə bilmir (tenant izolyasiyası).
* İmtahan suallarının exportu yalnız imtahan müəllifinə açıqdır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import Exam, QuestionBank
from apps.exams.services.question_bank_attach import create_bank_questions_from_parsed
from apps.exams.services.question_word_export import (
    _question_lines,
    bank_questions_payload,
    build_questions_docx,
)
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _parsed(text, correct="B"):
    return {
        "text": text,
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
        "correct": [correct],
        "answer_mode": "single",
    }


def _login_with_org(client, username, org, password="pw"):
    assert client.login(username=username, password=password)
    session = client.session
    session["active_organization"] = org.slug
    session.save()


class QuestionWordExportServiceTests(TestCase):
    def test_question_lines_mark_correct_with_star(self):
        lines = _question_lines(1, "Sual?", [("A", "yanlış", False), ("B", "düz", True)])
        self.assertEqual(lines[0], "1. Sual?")
        self.assertEqual(lines[1], "A) yanlış")
        self.assertEqual(lines[2], "*B) düz")

    def test_build_docx_returns_nonempty_buffer(self):
        buffer = build_questions_docx(
            title="Test",
            questions=[{"text": "Q1", "options": [("A", "a", True), ("B", "b", False)]}],
        )
        data = buffer.read()
        self.assertGreater(len(data), 0)
        # .docx faylı zip arxividir — PK imzası ilə başlayır.
        self.assertTrue(data.startswith(b"PK"))


class BankWordExportViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("we_teacher", "wet@example.com", "pw")
        self.org = Organization.objects.create(
            name="WE Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        teacher_role = self.org.roles.get(name="teacher")
        Membership.objects.create(user=self.teacher, organization=self.org, role=teacher_role, is_primary=True)

        self.bank = QuestionBank.objects.create(
            name="Export Bank", created_by=self.teacher, organization=self.org, language="az"
        )
        create_bank_questions_from_parsed(
            self.bank,
            [_parsed("Birinci sual"), _parsed("İkinci sual", correct="A")],
            language="az",
            created_by=self.teacher,
        )

    def test_owner_can_export_bank_docx(self):
        client = Client()
        _login_with_org(client, "we_teacher", self.org)
        response = client.get(reverse("exams:question_bank_word_export", kwargs={"bank_id": self.bank.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], DOCX_CONTENT_TYPE)
        self.assertTrue(response.content.startswith(b"PK"))

    def test_foreign_org_teacher_cannot_export(self):
        outsider = User.objects.create_user("we_outsider", "weo@example.com", "pw")
        other_org = Organization.objects.create(
            name="Other WE Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=outsider,
            status="active",
            is_active=True,
        )
        teacher_role = other_org.roles.get(name="teacher")
        Membership.objects.create(user=outsider, organization=other_org, role=teacher_role, is_primary=True)

        client = Client()
        _login_with_org(client, "we_outsider", other_org)
        response = client.get(reverse("exams:question_bank_word_export", kwargs={"bank_id": self.bank.id}))
        self.assertEqual(response.status_code, 404)

    def test_payload_respects_language_filter(self):
        payload_az = bank_questions_payload(self.bank, language="az")
        payload_ru = bank_questions_payload(self.bank, language="ru")
        self.assertEqual(len(payload_az), 2)
        self.assertEqual(len(payload_ru), 0)


class ExamWordExportViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("we_exam_teacher", "weet@example.com", "pw")
        self.org = Organization.objects.create(
            name="WE Exam Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        teacher_role = self.org.roles.get(name="teacher")
        Membership.objects.create(user=self.teacher, organization=self.org, role=teacher_role, is_primary=True)

        self.exam = Exam.objects.create(
            title="Export Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        bank = QuestionBank.objects.create(
            name="Tmp Bank", created_by=self.teacher, organization=self.org, language="az"
        )
        bank_questions = create_bank_questions_from_parsed(
            bank, [_parsed("İmtahan sualı")], language="az", created_by=self.teacher
        )
        from apps.exams.services.question_bank_attach import attach_bank_questions_to_exam

        attach_bank_questions_to_exam(self.exam, [bq.id for bq in bank_questions], created_by=self.teacher)

    def test_author_can_export_exam_questions(self):
        client = Client()
        _login_with_org(client, "we_exam_teacher", self.org)
        response = client.get(reverse("exams:exam_questions_word_export", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], DOCX_CONTENT_TYPE)
        self.assertTrue(response.content.startswith(b"PK"))

    def test_non_author_cannot_export_exam_questions(self):
        other = User.objects.create_user("we_other_teacher", "weot@example.com", "pw")
        teacher_role = self.org.roles.get(name="teacher")
        Membership.objects.create(user=other, organization=self.org, role=teacher_role, is_primary=True)

        client = Client()
        _login_with_org(client, "we_other_teacher", self.org)
        response = client.get(reverse("exams:exam_questions_word_export", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 404)
