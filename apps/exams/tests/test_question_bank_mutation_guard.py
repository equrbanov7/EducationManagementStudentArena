"""P0-2 reqressiya: sual bankının MƏZMUNUNU yalnız sahibi dəyişə bilər.

2026-09-02 auditi (`docs/audits/2026-09-02/PHASE23_SECURITY.md`) imtahan mərkəzi
işçisi ilə `POST /exams/question-bank/<id>/` + `bulk_action=delete` göndərib
BAŞQA müəllimin paylaşılmamış bankından sualı HARD-DELETE etdi (1 → 0), üstəlik
audit sətri də yazılmadı.  Səbəb: POST budağı yalnız OXU görünürlüyünə
(`accessible_banks`, mərkəzə bütün org banklarını göstərir) söykənirdi.

`accessible_banks` docstring-i onsuz da vəd edir: «Redaktə/silmə yenə yalnız
sahibə açıqdır (view qatında)» — bu testlər həmin vədi bağlayır.
"""

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.models import BankQuestion, QuestionBank
from apps.exams.tests.test_question_submission import _Base


class QuestionBankMutationGuardTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.bank = QuestionBank.objects.create(
            name="QA SEC Bank A",
            organization=self.org,
            created_by=self.teacher,
            is_shared=False,
        )
        self.question = BankQuestion.objects.create(
            bank=self.bank,
            text="Sahiblik qapısı sualı",
            question_type="test",
        )
        self.url = reverse("exams:question_bank_detail", kwargs={"bank_id": self.bank.id})

    def _post(self, user, **payload):
        return self._client_for(user).post(self.url, payload)

    # ── mərkəz OXUYUR, amma DƏYİŞMİR ────────────────────────────────────────
    def test_exam_center_keeps_read_access(self):
        response = self._client_for(self.exam_center).get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_exam_center_cannot_bulk_delete_foreign_bank_questions(self):
        response = self._post(
            self.exam_center,
            bulk_action="delete",
            selected_question_ids=[str(self.question.id)],
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(BankQuestion.objects.filter(pk=self.question.pk).exists())
        # Rədd audit olunur — səssiz uğursuzluq deyil.
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.exam_center,
                action="deny",
                resource_type="exams.QuestionBank",
                resource_id=str(self.bank.pk),
            ).exists()
        )

    def test_exam_center_cannot_deactivate_foreign_bank_questions(self):
        response = self._post(
            self.exam_center,
            bulk_action="deactivate",
            selected_question_ids=[str(self.question.id)],
        )
        self.assertEqual(response.status_code, 403)
        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)

    def test_exam_center_cannot_delete_whole_language(self):
        response = self._post(self.exam_center, bulk_action="delete_language", language="az")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(BankQuestion.objects.filter(pk=self.question.pk).exists())

    # ── sahib müəllim işini görür ───────────────────────────────────────────
    def test_owner_can_bulk_delete_and_the_delete_is_audited(self):
        response = self._post(
            self.teacher,
            bulk_action="delete",
            selected_question_ids=[str(self.question.id)],
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BankQuestion.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.teacher,
                action="delete",
                resource_type="exams.QuestionBank",
                resource_id=str(self.bank.pk),
            ).exists()
        )
