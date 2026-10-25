"""QA-1 P3 (2026-10-17): başlıqdakı «İmtahana qədər bal 10» bal bölgüsündəki 9,55 ilə ziddiyyətli görünürdü.

Qayda dəyişmir: giriş balı tam ədəddir (``gradebook_components.round_score``, yarım-yuxarı — sahib 2026-08-30).
Bal bölgüsü indi kəsirli cəmi və yuvarlaqlaşdırılmış yekunu birlikdə göstərir («Cəm 9,55 → 10»); cəm tam
ədəddirsə əlavə sətir yoxdur.
"""

from decimal import Decimal

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import translation

from apps.registrar import entry_standard

FLAGS = entry_standard.RuleFlags(selfwork=False, midterm_max=Decimal("30"), activity_split=False)


def _parts(attendance, activity="0", midterm="0", cap=50):
    return entry_standard.compose(
        attendance_score=Decimal(attendance),
        activity=Decimal(activity),
        midterm=Decimal(midterm),
        selfwork=Decimal("0"),
        cap=cap,
        flags=FLAGS,
    )


class EntryRoundingDisplayTest(SimpleTestCase):
    def test_total_uses_half_up_rule_and_exposes_raw_sum(self):
        parts = _parts("9.55")
        self.assertEqual(parts.total, Decimal("10"))
        self.assertEqual(parts.rounded_from, Decimal("9.55"))
        self.assertEqual(_parts("9.5").total, Decimal("10"))  # yarım-yuxarı (bankir yuvarlaqlaşdırması deyil)
        self.assertEqual(_parts("9.45").total, Decimal("9"))

    def test_whole_sum_has_no_rounding_line(self):
        parts = _parts("8", activity="2", midterm="20")
        self.assertEqual(parts.total, Decimal("30"))
        self.assertIsNone(parts.rounded_from)
        html = render_to_string("registrar/partials/_entry_parts.html", {"parts": parts})
        self.assertNotIn("data-entry-rounding", html)
        # Sahib 2026-10-26: cəm (midterm daxil) yuvarlaqlaşdırma olmasa da HƏMİŞƏ görünür.
        self.assertIn("data-entry-total", html)
        self.assertIn("<strong>30</strong>", html)

    def test_capped_sum_is_not_shown_as_rounding(self):
        parts = _parts("10", activity="10", midterm="25.5", cap=40)
        self.assertEqual(parts.total, Decimal("40"))
        self.assertIsNone(parts.rounded_from)
        html = render_to_string("registrar/partials/_entry_parts.html", {"parts": parts})
        self.assertNotIn("data-entry-rounding", html)

    def test_breakdown_shows_raw_sum_next_to_rounded_total(self):
        with translation.override("az"):
            html = render_to_string("registrar/partials/_entry_parts.html", {"parts": _parts("9.55")})
        self.assertIn("data-entry-rounding", html)
        self.assertIn("9,55 → <strong>10</strong>", html)
