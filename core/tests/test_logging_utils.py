"""Log injection reqressiyası — istifadəçi dəyəri log sətrini «uydura» bilməz.

CodeQL `py/log-injection` (2026-09-02 PR audit): kataloq/RİM/profil endpoint-ləri
istifadəçidən gələn `action` / `section` / keş açarını log mesajına qoyurdu.
`\\n` daşıyan dəyər log-aqreqatorda saxta ikinci hadisə kimi görünə bilər.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from core.logging_utils import safe_log_value


class SafeLogValueTests(SimpleTestCase):
    def test_newlines_cannot_forge_a_second_log_line(self):
        forged = "block\nCRITICAL root: hesab silindi (saxta sətir)"
        cleaned = safe_log_value(forged)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertIn("saxta", cleaned)

    def test_carriage_return_and_control_chars_are_removed(self):
        cleaned = safe_log_value("a\r\nb\x00c\x1b[31md")
        self.assertNotIn("\r", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x1b", cleaned)

    def test_long_value_is_capped(self):
        cleaned = safe_log_value("x" * 500, limit=20)
        self.assertEqual(len(cleaned), 21)  # 20 simvol + «…»
        self.assertTrue(cleaned.endswith("…"))

    def test_non_string_values_are_accepted(self):
        self.assertEqual(safe_log_value(42), "42")
        self.assertEqual(safe_log_value(None), "None")
