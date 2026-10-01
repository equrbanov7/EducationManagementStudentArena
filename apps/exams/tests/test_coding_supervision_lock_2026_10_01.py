"""EXAMQA R9 (2026-10-01): nəzarət kilidi praktik (kod) imtahanında da serverdə tətbiq olunur.

Kilid əvvəl yalnız klient overlay-i idi; overlay-i silən tələbə kilid altında kodu saxlaya, işlədə və
təhvil verə bilirdi. İndi autosave/run/submit 423 qaytarır; kilid açılanda (resumed) yazı yenə işləyir.
"""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import CodingSubmission

from .test_coding_exam import CodingExamSubmissionApiTests

PAYLOAD = {
    "selected_language": "python",
    "files": [{"name": "main.py", "content": "print('hi')\n", "language": "python", "is_main": True}],
    "stdin": "",
}


@override_settings(EXAM_SUPERVISION_ENABLED=True)
class CodingSupervisionLockTests(TestCase):
    def setUp(self):
        CodingExamSubmissionApiTests.setUp(self)

    def _lock(self):
        self.attempt.supervision_status = "locked"
        self.attempt.supervision_locked_at = timezone.now()
        self.attempt.save(update_fields=["supervision_status", "supervision_locked_at"])

    def _post(self, name):
        return self.client.post(
            reverse(f"exams:{name}", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
            data=json.dumps(PAYLOAD),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_locked_attempt_rejects_autosave_run_and_submit(self):
        self._lock()
        for name in ("coding_autosave", "coding_run", "coding_submit"):
            response = self._post(name)
            self.assertEqual(response.status_code, 423, name)
            self.assertTrue(response.json()["locked"], name)
        self.assertFalse(CodingSubmission.objects.exists())
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_finished)

    @patch("apps.exams.views.student.coding.record_autosave")
    def test_resumed_attempt_writes_again(self, _record):
        self._lock()
        self.attempt.supervision_status = "resumed"
        self.attempt.save(update_fields=["supervision_status"])
        self.assertEqual(self._post("coding_autosave").status_code, 200)
        self.assertEqual(self._post("coding_submit").status_code, 200)
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_finished)

    @override_settings(EXAM_SUPERVISION_ENABLED=False)
    @patch("apps.exams.views.student.coding.record_autosave")
    def test_lock_ignored_when_supervision_feature_off(self, _record):
        self._lock()
        self.assertEqual(self._post("coding_autosave").status_code, 200)
