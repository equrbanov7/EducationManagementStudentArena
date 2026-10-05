"""Təhlükəsizlik auditi 2026-10-05 — coding təhvili gizli test məlumatını sızdırmır.

``grade_files_against_tests`` sətir-başına ``input/expected/actual/error`` sahələrini
gizli testlər üçün boşaldırdı, amma ÜMUMİ ``output``/``error`` SON icranın (çox
vaxt gizli testin) nəticəsi idi. Tələbə kodu ``print(input())`` yazmaqla gizli
testin girişini təhvil cavabında görürdü (növbəti cəhd / digər tələbələr üçün açar).
Nəticəsi gizlədilmiş imtahanda isə təhvil cavabı bal və test nəticələrini qaytarırdı.
"""

import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.exams.models import CodingSubmission, CodingTestCase
from apps.exams.services.coding_runtime import ExecutionResult

from . import test_coding_exam as _coding_base

SECRET = "SECRET-HIDDEN-INPUT-42"
PAYLOAD = {
    "selected_language": "python",
    "files": [
        {"name": "main.py", "content": "import sys; print(sys.stdin.read())", "language": "python", "is_main": True}
    ],
    "stdin": "",
}


def _echo(**kwargs):
    stdin = kwargs.get("stdin", "")
    return ExecutionResult(
        status=CodingSubmission.STATUS_RUNTIME_ERROR, output=stdin, error=f"Traceback: {stdin}", execution_time_ms=3
    )


class CodingSubmitHiddenCaseLeakTests(TestCase):
    setUp = _coding_base.CodingExamSubmissionApiTests.setUp

    def _prepare(self):
        self.coding_question.enable_code_execution = True
        self.coding_question.save(update_fields=["enable_code_execution"])
        CodingTestCase.objects.create(
            coding_question=self.coding_question,
            input_data="visible\n",
            expected_output="visible\n",
            visibility=CodingTestCase.VISIBILITY_VISIBLE,
        )
        CodingTestCase.objects.create(
            coding_question=self.coding_question,
            input_data=SECRET,
            expected_output="x",
            visibility=CodingTestCase.VISIBILITY_HIDDEN,
        )

    def _submit(self):
        with patch("apps.exams.services.coding_runtime.execute_code", side_effect=_echo):
            return self.client.post(
                reverse("exams:coding_submit", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
                data=json.dumps(PAYLOAD),
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

    def test_submit_response_does_not_contain_hidden_case_output_or_error(self):
        self._prepare()
        response = self._submit()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SECRET, response.content.decode())
        final = CodingSubmission.objects.get(is_final=True)
        self.assertNotIn(SECRET, final.output or "")
        self.assertNotIn(SECRET, final.error_message or "")

    def test_submit_response_hides_score_when_results_hidden(self):
        self._prepare()
        self.exam.results_hidden_from_students = True
        self.exam.save(update_fields=["results_hidden_from_students"])
        body = self._submit().json()
        self.assertTrue(body["finished"])
        for item in [body.get("submission"), *body.get("submissions", [])]:
            if item:
                self.assertIsNone(item.get("score"))
                self.assertEqual(item.get("test_results"), [])

    def test_run_and_autosave_hide_score_when_results_hidden(self):
        """İkinci dalğa: «Run» (görünən testlər) və autosave cavabında da bal yoxdur."""
        self._prepare()
        self.exam.results_hidden_from_students = True
        self.exam.save(update_fields=["results_hidden_from_students"])
        kwargs = {"slug": self.exam.slug, "attempt_id": self.attempt.id}
        with patch("apps.exams.services.coding_runtime.execute_code", side_effect=_echo):
            run = self.client.post(
                reverse("exams:coding_run", kwargs=kwargs),
                data=json.dumps(PAYLOAD),
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(run.status_code, 200, run.content)
        self.assertIsNone(run.json()["submission"]["score"])
        autosave = self.client.post(
            reverse("exams:coding_autosave", kwargs=kwargs),
            data=json.dumps(PAYLOAD),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(autosave.status_code, 200, autosave.content)
        self.assertIsNone(autosave.json()["submission"]["score"])
