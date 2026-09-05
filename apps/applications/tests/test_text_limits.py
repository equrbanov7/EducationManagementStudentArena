"""Müraciət mətninin yuxarı hədləri — QA 2026-09-05 APPLICATIONS-02/03 reqressiya qapısı."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

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


class DuplicateSubmissionTest(TestCase):
    """İkiqat klik iki müraciət yaratmamalıdır — QA 2026-09-05 P3-18."""

    def test_second_identical_submission_is_refused(self):
        from apps.applications.services.submit import submit_application
        from apps.applications.state_machine import TransitionDenied
        from apps.applications.tests.factories import kind_of, make_world

        world = make_world("app-dup")
        payload = {
            "organization": world["organization"],
            "user": world["student"],
            "kind": kind_of(world, "diger"),
            "subject": "QA- ikiqat klik",
            "body": "Eyni mətnlə iki dəfə göndərilən müraciət mətni.",
        }
        first = submit_application(**payload)
        with self.assertRaises(TransitionDenied) as ctx:
            submit_application(**payload)
        self.assertEqual(ctx.exception.code, "duplicate.recent")
        self.assertEqual(first.organization.applications.count(), 1)
