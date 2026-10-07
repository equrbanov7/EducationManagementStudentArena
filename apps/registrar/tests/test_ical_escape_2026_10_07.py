"""Təhlükəsizlik auditi 2026-10-07 — iCal TEXT qaçışı tək CR-i də tutur (RFC 5545).

``_escape`` yalnız ``\\r\\n`` və ``\\n``-i ``\\n``-ə çevirirdi; tək ``\\r`` olduğu kimi
qalırdı. CR-i sətir sonu sayan parser-lərdə otaq/fənn adı ilə yeni xüsusiyyət
sətri (``X-…:``, ``END:VEVENT`` / ``BEGIN:VEVENT``) yeridilə bilərdi.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.registrar import ical
from apps.registrar.models import WeekType


def _slot(*, room="", subject_name="Proqramlaşdırma"):
    teacher = SimpleNamespace(get_full_name=lambda: "Müəllim Bir", username="m.bir")
    offering = SimpleNamespace(
        subject=SimpleNamespace(code="CS101", name=subject_name),
        group=SimpleNamespace(name="G1"),
        instructor=teacher,
        instructor_id=1,
    )
    return SimpleNamespace(
        pk=7,
        offering=offering,
        instructor_id=None,
        instructor=None,
        weekday=3,
        week_type=WeekType.ALL,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(11, 30),
        room=room,
    )


PERIOD = SimpleNamespace(start_date=datetime.date(2024, 9, 2), end_date=datetime.date(2025, 1, 31))


class IcalEscapeTest(SimpleTestCase):
    def test_bare_cr_is_escaped_like_a_newline(self):
        self.assertEqual(ical._escape("a\rb"), "a\\nb")
        self.assertEqual(ical._escape("a\r\nb\nc"), "a\\nb\\nc")
        self.assertEqual(ical._escape("a\r\rb"), "a\\n\\nb")

    def test_unicode_line_separators_and_controls(self):
        self.assertEqual(ical._escape("a b c\x85d"), "a\\nb\\nc\\nd")
        self.assertEqual(ical._escape("a\x00b\x1bc\x7fd\te"), "abcd\te")

    def test_existing_escapes_unchanged(self):
        self.assertEqual(ical._escape("a;b,c\\d\ne"), "a\\;b\\,c\\\\d\\ne")
        self.assertEqual(ical._escape(None), "")

    def test_cr_in_room_cannot_inject_properties(self):
        payload = ical.build_schedule_ics(
            slots=[_slot(room="A-204\rEND:VEVENT\rBEGIN:VEVENT\rX-INJECTED:1", subject_name="Fənn\rX-EVIL:2")],
            period=PERIOD,
            calendar_name="G1\rX-WR-TIMEZONE:Evil",
        )
        # Yeganə sətir ayırıcısı CRLF-dir; CRLF-siz CR və CR-siz LF qalmır.
        self.assertNotIn("\r", payload.replace("\r\n", ""))
        self.assertNotIn("\n", payload.replace("\r\n", ""))
        lines = payload.split("\r\n")
        self.assertEqual(lines.count("BEGIN:VEVENT"), 1)
        self.assertEqual(lines.count("END:VEVENT"), 1)
        self.assertFalse([line for line in lines if line.startswith(("X-INJECTED", "X-EVIL", "X-WR-TIMEZONE"))])
        self.assertIn("LOCATION:A-204\\nEND:VEVENT\\nBEGIN:VEVENT\\nX-INJECTED:1", payload)
