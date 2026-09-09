"""«Tədris planı» PDF idxalının UYĞUNLAŞDIRMA qatı (2026-09-09).

PDF oxunuşu (`extract_rows`) burada sınanmır — o, xarici fayl tələb edir.
Sınanan şey RİSKLİ hissədir: adların normallaşdırılması və sətirlərin
təsnifatı, çünki səhv uyğunluq planı sükutla korlayır.
"""

from django.test import SimpleTestCase

from apps.registrar.plan_import import is_elective_block, match_rows, normalize


class NormalizeTest(SimpleTestCase):
    def test_cyrillic_homoglyph_is_folded_to_latin(self):
        """Mənbə PDF-lərdə «Аzərbaycan» kiril «А» (U+0410) ilə başlayır."""
        cyrillic = "Аzərbaycanın tarixi"
        self.assertNotEqual(cyrillic[0], "A")
        self.assertEqual(normalize(cyrillic), normalize("Azərbaycanın tarixi"))

    def test_punctuation_and_case_do_not_break_matching(self):
        self.assertEqual(
            normalize("Xarici dildə  işgüzar-kommunikasiya"), normalize("xarici dildə işgüzar kommunikasiya")
        )


class ElectiveBlockTest(SimpleTestCase):
    def test_blocks_are_detected(self):
        for name in (
            "I blok: 1. Sosiologiya 2. AR Konstitusiyası",
            "IV blok: 1. Psixoloji xidmət",
            "Birinci blok 1. Sosiologiya",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_elective_block(name))

    def test_single_subject_is_not_a_block(self):
        self.assertFalse(is_elective_block("Ehtimal nəzəriyyəsi"))


class MatchRowsTest(SimpleTestCase):
    def _rows(self):
        return [
            {"no": 1, "code": "A", "name": "Riyaziyyat", "credits": 5, "total_hours": 150, "semester": "payız-1"},
            {
                "no": 2,
                "code": "B",
                "name": "I blok: 1. Sosiologiya",
                "credits": 3,
                "total_hours": 90,
                "semester": "yaz-2",
            },
            {"no": 3, "code": "C", "name": "Tanınmayan fənn", "credits": 4, "total_hours": 120, "semester": "payız-3"},
        ]

    def test_rows_are_split_into_matched_elective_and_unknown(self):
        catalogue = {normalize("Riyaziyyat"): object()}
        result = match_rows(self._rows(), catalogue)
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["electives"]), 1)
        self.assertEqual(len(result["unknown"]), 1)
        # Tanınmayan fənn UYDURULMUR — yalnız hesabata düşür.
        self.assertEqual(result["unknown"][0]["name"], "Tanınmayan fənn")

    def test_short_table_is_flagged_as_low_yield(self):
        result = match_rows(self._rows(), {})
        self.assertTrue(result["low_yield"])
