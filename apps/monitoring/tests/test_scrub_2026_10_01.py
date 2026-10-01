"""Monitorinq mətn süzgəcləri (2026-10-01): sirr gizlətmə + şəxsi məlumat təmizləmə."""

from django.test import SimpleTestCase

from apps.monitoring.scrub import redact_secrets, scrub_path, scrub_personal


class RedactSecretsTests(SimpleTestCase):
    def test_hides_credentials_tokens_and_keys(self):
        line = (
            "DATABASE_URL=postgres://ems:S3cr3t!@db:5432/ems password=hunter2 "
            "Authorization: Bearer abcdefghijklmnop key=AIzaSyA1234567890abcdefghijklmnop "
            '{"api_key": "sk-abcdefghijklmnopqrstuv"} sessionid=q1w2e3r4t5'
        )
        cleaned = redact_secrets(line)
        for secret in ("S3cr3t!", "hunter2", "abcdefghijklmnop", "AIzaSyA1234567890", "sk-abcdef", "q1w2e3r4t5"):
            self.assertNotIn(secret, cleaned)
        self.assertIn("postgres://***@db:5432/ems", cleaned)

    def test_leaves_normal_text_alone(self):
        text = "GET /exams/12/ 200 in 35 ms at 12:30:45"
        self.assertEqual(redact_secrets(text), text)
        self.assertEqual(redact_secrets(""), "")
        self.assertEqual(redact_secrets(None), "")


class ScrubPersonalTests(SimpleTestCase):
    def test_removes_emails_ips_and_usernames(self):
        text = "anar.memmedov (anar@wcu.edu.az) from 203.0.113.7 / fe80::1 at 12:30:45 id 12345678"
        cleaned = scrub_personal(text)
        for needle in ("anar.memmedov", "anar@wcu.edu.az", "203.0.113.7", "fe80::1", "12345678"):
            self.assertNotIn(needle, cleaned)
        self.assertIn("12:30:45", cleaned)  # vaxt IPv6 sayılmır

    def test_scrub_path_masks_whole_segment(self):
        self.assertEqual(scrub_path("/accounts/u/anar.memmedov/edit/"), "/accounts/u/<x>/edit/")
        self.assertEqual(scrub_path("/exams/<id>/take/"), "/exams/<id>/take/")
