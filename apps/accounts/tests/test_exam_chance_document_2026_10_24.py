"""«Yenidən imtahan cəhdi» — məcburi əsas sənəd, ata adı + qrup, «Son verilən» sətrindən ön-doldurma (2026-10-24)."""

from __future__ import annotations

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole, UserProfile
from apps.exams.models import Exam, StudentExamAttemptGrant
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.registrar.models import ExamChanceGrant
from apps.registrar.models.retake_log import EXAM_CHANCE_DOCUMENT_PREFIX
from apps.registrar.retake_media import check_chance_document_access
from apps.registrar.tests.retake_fixture import RetakeBase, User, pdf
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True)
class ExamChanceDocumentTest(RetakeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.center = User.objects.create_user("rt_center", "rt_center@qku.edu.az", "pw")
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        now = timezone.now()
        cls.exam = Exam.objects.create(
            title="INF101 midterm",
            author=cls.center,
            organization=cls.org,
            subject=cls.subject,
            exam_type="test",
            exam_type_extended="midterm",
            is_active=True,
            is_public=False,
            max_attempts_per_user=1,
            total_duration_minutes=60,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=3),
        )
        # Eyni ad-soyad, fərqli ata adı — sahibin şikayəti («İlkin Orucov» iki dəfə).
        for user, father in ((cls.student, "Elçin"), (cls.other, "Vüqar")):
            user.first_name, user.last_name = "İlkin", "Orucov"
            user.save(update_fields=["first_name", "last_name"])
            UserProfile.objects.filter(user=user).update(patronymic=father)

    def _post(self, **data):
        payload = {
            "exam_id": str(self.exam.pk),
            "extra_attempts": "1",
            "reason": "technical",
            "note": "Kompüter imtahan zamanı söndü",
            **data,
        }
        return self.client_for(self.center).post(reverse("accounts:exam_chance"), payload)

    def _section(self, query=""):
        url = f"{reverse('accounts:profile')}?section=exam-chance&chance_reason=technical{query}"
        return self.client_for(self.center).get(url).content.decode()

    # ── məcburi sənəd ────────────────────────────────────────────────────────────────────────
    def test_grant_without_document_is_rejected(self):
        response = self._post(student_ids=[str(self.student.pk)])
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"chance_student={self.student.pk}", response["Location"])  # seçim itmir
        self.assertFalse(ExamChanceGrant.objects.exists())
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=self.exam).exists())

    def test_grant_with_disallowed_document_is_rejected(self):
        bad = SimpleUploadedFile("emr.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        self._post(student_ids=[str(self.student.pk)], document=bad)
        self.assertFalse(ExamChanceGrant.objects.exists())
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=self.exam).exists())

    def test_grant_with_document_succeeds_and_shares_one_file(self):
        response = self._post(student_ids=[str(self.student.pk), str(self.other.pk)], document=pdf("emr-45.pdf"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudentExamAttemptGrant.objects.filter(exam=self.exam).count(), 2)
        with bypass_rls():
            logs = list(ExamChanceGrant.objects.order_by("student_id"))
        self.assertEqual(len(logs), 2)
        self.assertTrue(logs[0].document.name.startswith(f"{EXAM_CHANCE_DOCUMENT_PREFIX}{self.org.pk}/"))
        self.assertEqual(logs[0].document.name, logs[1].document.name)  # bir fayl, iki qeyd
        self.assertEqual(logs[0].document_name, "emr-45.pdf")

        page = self._section()
        self.assertIn(logs[0].document.url, page)  # «Son verilən» cədvəlində sənəd linki
        self.assertIn("emr-45.pdf", page)

    def test_document_access_policy(self):
        self._post(student_ids=[str(self.student.pk)], document=pdf())
        with bypass_rls():
            path = ExamChanceGrant.objects.get().document.name
            self.assertTrue(check_chance_document_access(self.student, path))
            self.assertTrue(check_chance_document_access(self.center, path))
            self.assertFalse(check_chance_document_access(self.far, path))
            self.assertFalse(check_chance_document_access(self.teacher, path))
            self.assertFalse(check_chance_document_access(self.student, f"{EXAM_CHANCE_DOCUMENT_PREFIX}yoxdur.pdf"))

    def test_form_marks_document_required(self):
        page = self._section()
        self.assertIn('enctype="multipart/form-data"', page)
        self.assertIn('name="document"', page)
        self.assertRegex(page, r'<input type="file"[^>]*name="document"[^>]*required')

    # ── ata adı + qrup ──────────────────────────────────────────────────────────────────────
    def test_chips_show_patronymic_and_group(self):
        page = self._section("&chance_student_q=Orucov")
        self.assertIn("Elçin", page)
        self.assertIn("Vüqar", page)
        self.assertIn("Ata adı", page)
        self.assertIn("G1", page)
        self.assertIn(f'name="student_ids" value="{self.student.pk}"', page)
        self.assertIn(f'name="student_ids" value="{self.other.pk}"', page)

    def test_search_by_patronymic(self):
        page = self._section("&chance_student_q=Vüqar")
        self.assertIn(f'name="student_ids" value="{self.other.pk}"', page)
        self.assertNotIn(f'name="student_ids" value="{self.student.pk}"', page)

    # ── ön-doldurma ─────────────────────────────────────────────────────────────────────────
    def test_prefill_checks_student_and_selects_exam(self):
        page = self._section(f"&chance_exam={self.exam.pk}&chance_student={self.other.pk}&chance_focus=grant")
        self.assertRegex(page, rf'name="student_ids" value="{self.other.pk}"[^>]*checked')
        self.assertNotIn(f'name="student_ids" value="{self.student.pk}"', page)
        self.assertRegex(page, rf'<option value="{self.exam.pk}"[^>]*selected')
        self.assertIn("data-exch-focus", page)
        self.assertIn(f'name="chance_student" value="{self.other.pk}"', page)  # süzgəc dəyişəndə qalır

    def test_prefill_ignores_foreign_student(self):
        outsider = User.objects.create_user("rt_outsider", "rt_outsider@qku.edu.az", "pw")
        page = self._section(f"&chance_student={outsider.pk}")
        self.assertNotIn(f'name="student_ids" value="{outsider.pk}"', page)
        self.assertIn('name="chance_student" value=""', page)

    def test_recent_row_prefills_grant_form(self):
        self._post(student_ids=[str(self.other.pk)], document=pdf())
        page = self._section()
        self.assertIn("data-exch-prefill=", page)
        self.assertIn(f"chance_student={self.other.pk}", page)
        self.assertIn(f"chance_exam={self.exam.pk}", page)
        self.assertIn("chance_reason=technical", page)
        self.assertIn("Vüqar", page)  # cədvəldə ata adı
