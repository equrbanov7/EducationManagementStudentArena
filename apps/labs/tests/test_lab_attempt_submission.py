"""UI-06: tələbənin gördüyü cavablar təsdiqlədiyi cəhdə bağlı qalır."""

import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.labs.models import LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.labs.tests.test_course_tasks_fix_2026_09_28 import _LabFixture
from apps.labs.tests.test_views import _login_with_org


class LabAttemptSubmissionTests(_LabFixture):
    def setUp(self):
        super().setUp()
        self.lab = self._lab(allow_file_upload=True)
        block = LabBlock.objects.create(lab=self.lab, title="İki sual", questions_to_pick=0)
        self.questions = [
            LabQuestion.objects.create(block=block, question_text=f"Sual {n}", question_number=n) for n in (1, 2)
        ]
        _login_with_org(self.client, self.a1, self.organization)
        self.detail = reverse("labs:lab_detail", args=[self.lab.pk])
        self.submit = reverse("labs:submit_lab", args=[self.lab.pk])
        self.autosave = reverse("labs:auto_save_answer", args=[self.lab.pk])
        page = self.client.get(self.detail)
        self.assertContains(page, 'name="attempt_number" value="1"')
        self.assignment = page.context["assignment"]
        self.first, self.second = [q.pk for q in self.questions]

    def save_text(self, question_id, text, **attempt):
        return self.client.post(
            self.autosave, {"question_id": question_id, "answer": text, **attempt}, content_type="application/json"
        )

    def test_immediate_submit_keeps_both_answers_and_late_autosaves_cannot_change_them(self):
        response = self.client.post(
            self.submit, {"attempt_number": 1, f"answer_{self.first}": "Bir", f"answer_{self.second}": "İki"}
        )
        self.assertTrue(response.json()["success"])
        for question in (self.first, self.second):
            self.assertEqual(self.save_text(question, "Köhnə", attempt_number=1).status_code, 409)
        # Əvvəlki versiya ilə açılmış səhifənin gecikmiş sorğusu da yeni qaralama yarada bilməz.
        self.assertEqual(self.save_text(self.second, "Köhnə").status_code, 409)
        submission = self.assignment.submissions.get()
        self.assertEqual(submission.attempt_number, 1)
        self.assertCountEqual(submission.answers.values_list("answer", flat=True), ["Bir", "İki"])
        self.assertFalse(LabAnswer.objects.filter(lab=self.lab, is_draft=True).exists())

    def test_double_submit_is_idempotent_and_explicit_second_attempt_is_independent(self):
        self.lab.max_attempts = 2
        self.lab.save(update_fields=["max_attempts"])
        payload = {"attempt_number": 1, f"answer_{self.first}": "Birinci"}
        for _ in range(2):
            self.assertTrue(self.client.post(self.submit, payload).json()["success"])
        self.assertEqual(self.assignment.submissions.count(), 1)
        self.assertEqual(self.save_text(self.first, "Gec", attempt_number=1).status_code, 409)
        self.assertContains(self.client.get(self.detail), 'name="attempt_number" value="2"')
        self.assertTrue(self.save_text(self.second, "Qaralama", attempt_number=2).json()["success"])
        self.assertTrue(
            self.client.post(self.submit, {"attempt_number": 2, f"answer_{self.second}": "Son"}).json()["success"]
        )
        self.assertCountEqual(
            LabAnswer.objects.filter(lab=self.lab).values_list("submission__attempt_number", "answer", "is_draft"),
            [(1, "Birinci", False), (2, "Son", False)],
        )

    def test_autosaved_file_survives_final_snapshot_and_new_file_can_arrive_with_text(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            saved = self.client.post(
                self.autosave,
                {"attempt_number": 1, "question_id": self.first, "answer_file": SimpleUploadedFile("a.txt", b"first")},
            )
            self.assertTrue(saved.json()["success"])
            self.assertTrue(self.save_text(self.second, "Köhnə", attempt_number=1).json()["success"])
            result = self.client.post(
                self.submit,
                {
                    "attempt_number": 1,
                    f"answer_{self.first}": "Faylla",
                    f"answer_{self.second}": "",
                    f"file_{self.second}": SimpleUploadedFile("b.txt", b"second"),
                },
            )
            self.assertTrue(result.json()["success"])
            answers = self.assignment.submissions.get().answers
            for question, text, content in [(self.first, "Faylla", b"first"), (self.second, "", b"second")]:
                answer = answers.get(question_id=question)
                self.assertEqual(answer.answer, text)
                self.assertEqual(Path(answer.answer_file.path).read_bytes(), content)

    def test_failed_final_file_validation_keeps_attempt_and_original_draft_for_retry(self):
        self.save_text(self.first, "Qaralama", attempt_number=1)
        response = self.client.post(
            self.submit,
            {
                "attempt_number": 1,
                f"answer_{self.first}": "Son",
                f"file_{self.second}": SimpleUploadedFile("unsupported.xyz", b"file"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LabSubmission.objects.filter(assignment=self.assignment).exists())
        self.assertEqual(LabAnswer.objects.get(lab=self.lab).answer, "Qaralama")
        self.assertTrue(self.client.post(self.submit, {"attempt_number": 1}).json()["success"])
        self.assertEqual(self.assignment.submissions.get().answers.get().answer, "Qaralama")

    def test_first_post_distributes_questions_on_precreated_empty_assignment(self):
        another = self._lab()
        block = LabBlock.objects.create(lab=another, title="Təyin edilməmiş blok")
        question = LabQuestion.objects.create(block=block, question_text="Sual", question_number=1)
        assignment = LabAssignment.objects.create(lab=another, student=self.a1)
        self.assertFalse(assignment.assigned_questions.exists())
        response = self.client.post(
            reverse("labs:submit_lab", args=[another.pk]),
            {"attempt_number": 1, f"answer_{question.pk}": "Birbaşa təhvil"},
        )
        self.assertTrue(response.json()["success"])
        self.assertEqual(assignment.submissions.get().answers.get().answer, "Birbaşa təhvil")

    def test_changed_question_set_rejects_stale_form_without_using_an_attempt(self):
        self.questions[1].delete()  # Müəllim hələ cavablanmamış sualı silib, tələbənin səhifəsi açıqdır.
        for stale_field in (
            {f"answer_{self.second}": "Səhifədəki cavab"},
            {f"file_{self.second}": SimpleUploadedFile("notes.txt", b"notes")},
        ):
            response = self.client.post(
                self.submit, {"attempt_number": 1, f"answer_{self.first}": "Bir", **stale_field}
            )
            self.assertEqual(response.status_code, 409)
            self.assertFalse(response.json()["success"])
        self.assertEqual(self.save_text(self.second, "Köhnə sual", attempt_number=1).status_code, 409)
        self.assertFalse(self.assignment.submissions.exists())
        self.assertFalse(LabAnswer.objects.filter(lab=self.lab).exists())
        self.assertContains(self.client.get(self.detail), 'name="attempt_number" value="1"')
        self.assertTrue(
            self.client.post(self.submit, {"attempt_number": 1, f"answer_{self.first}": "Bir"}).json()["success"]
        )

    def test_late_file_uses_final_form_and_delayed_upload_cannot_open_another_attempt(self):
        self.lab.end_datetime = timezone.now() - timedelta(minutes=1)
        self.lab.allow_late_submission = True
        self.lab.save(update_fields=["end_datetime", "allow_late_submission"])
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            data = {"attempt_number": 1, "question_id": self.first}
            self.assertEqual(
                self.client.post(self.autosave, {**data, "answer_file": SimpleUploadedFile("a.txt", b"a")}).status_code,
                409,
            )
            result = self.client.post(
                self.submit, {"attempt_number": 1, f"file_{self.first}": SimpleUploadedFile("a.txt", b"a")}
            )
            self.assertTrue(result.json()["success"])
            submission = self.assignment.submissions.get()
            self.assertEqual(submission.status, "late")
            self.assertEqual(Path(submission.answers.get().answer_file.path).read_bytes(), b"a")
            self.assertFalse(LabAnswer.objects.filter(lab=self.lab, is_draft=True).exists())
