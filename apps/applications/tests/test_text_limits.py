"""Müraciət mətninin yuxarı hədləri — QA 2026-09-05 APPLICATIONS-02/03 reqressiya qapısı."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.applications.constants import MAX_BODY_LENGTH, MAX_SUBJECT_LENGTH, MIN_BODY_LENGTH, MIN_SUBJECT_LENGTH
from apps.applications.services.submit import validate_text


class ValidateTextLimitsTest(SimpleTestCase):
    def test_within_limits_has_no_errors(self):
        self.assertEqual(validate_text("Q" * MIN_SUBJECT_LENGTH, "b" * MIN_BODY_LENGTH), {})

    def test_oversized_body_is_rejected(self):
        errors = validate_text("Mövzu QA", "z" * (MAX_BODY_LENGTH + 1))
        self.assertIn("body", errors)
        self.assertIn(str(MAX_BODY_LENGTH), errors["body"][0])

    def test_oversized_subject_is_rejected_instead_of_silently_truncated(self):
        errors = validate_text("S" * (MAX_SUBJECT_LENGTH + 1), "b" * MIN_BODY_LENGTH)
        self.assertIn("subject", errors)
        self.assertIn(str(MAX_SUBJECT_LENGTH), errors["subject"][0])
