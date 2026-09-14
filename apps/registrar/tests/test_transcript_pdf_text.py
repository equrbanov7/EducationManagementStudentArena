"""Transkript PDF-də mətnin ÖLÇÜLƏRƏK sətirə bölünməsi (2026-09-11).

Sahib: «transkriptdə bəzi yazılar üst-üstə düşür — uzun olanda alt sətrə
keçsin».  Əvvəl fənn adı simvol sayı ilə kəsilirdi (`int(width / 4.4)`),
tələbə blokunda isə sabit 40 simvol — «ə/ü/ş» dolu azərbaycanca ad eyni simvol
sayında daha enli olduğu üçün qonşu sütunun üstünə minirdi, rəsmi sənəddə isə
məlumat kəsilib itirdi («…köhnə 050…»).
"""

from django.test import SimpleTestCase

from apps.registrar.transcript_pdf_text import row_height, wrap_lines


def _measure(text: str) -> float:
    """Sadə, deterministik ölçü: hər simvol 1pt — test şriftə asılı olmasın."""
    return float(len(text))


class WrapLinesTest(SimpleTestCase):
    def test_short_text_stays_on_one_line(self):
        self.assertEqual(wrap_lines("Məntiq", width=20, measure=_measure), ["Məntiq"])

    def test_long_text_wraps_at_word_boundaries_and_loses_nothing(self):
        text = "MYEDU-L1915 Xarici dildə işgüzar və akademik kommunikasiya"
        lines = wrap_lines(text, width=24, measure=_measure)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(_measure(line), 24, line)
        # Heç bir söz itmir, heç bir söz kəsilmir — rəsmi sənəddir.
        self.assertEqual(" ".join(lines), text)

    def test_single_overlong_token_is_broken_by_characters(self):
        lines = wrap_lines("ABCDEFGHIJKLMNOPQRSTUVWXYZ", width=10, measure=_measure)
        self.assertEqual(lines, ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ"])

    def test_whitespace_is_normalised(self):
        self.assertEqual(wrap_lines("  a   b  ", width=50, measure=_measure), ["a b"])

    def test_empty_value_yields_one_blank_line(self):
        """Hündürlük hesabı sıfıra düşməsin — boş dəyər də bir sətir tutur."""
        self.assertEqual(wrap_lines("", width=50, measure=_measure), [""])
        self.assertEqual(wrap_lines(None, width=50, measure=_measure), [""])


class RowHeightTest(SimpleTestCase):
    def test_single_line_keeps_the_12pt_rhythm(self):
        self.assertEqual(row_height(1), 12)
        self.assertEqual(row_height(0), 12)

    def test_each_extra_line_adds_one_line_height(self):
        self.assertGreater(row_height(2), row_height(1))
        self.assertAlmostEqual(row_height(3) - row_height(2), row_height(2) - row_height(1))
