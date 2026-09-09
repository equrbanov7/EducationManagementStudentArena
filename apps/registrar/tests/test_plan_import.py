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


class ElectiveBlockLanguageTest(SimpleTestCase):
    """2026-09-10: bəzi planlar İNGİLİS dilində dərc olunub.

    Regionşünaslıq sənədində seçmə blok «I block 1. Philosophy …» şəklindədir.
    Əvvəl belə sətir «tapılmayan fənn» sayılırdı və hesabatda 41 uydurma
    «tanınmayan ad» yaradırdı — səhv siqnal idxal qərarını korlayır.
    """

    def test_english_blocks_are_detected(self):
        for name in (
            "I block 1. Philosophy 2. Sociology",
            "II block 1. Information Technologies (Specialized)",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_elective_block(name))

    def test_english_single_subject_is_not_a_block(self):
        self.assertFalse(is_elective_block("History of Azerbaijan"))


class PlaceholderRowTest(SimpleTestCase):
    """Magistr planında ixtisas hissəsi YER TUTUCU sətirlərlə verilir.

    «İxtisaslaşmaya ayrılan fənlər** — 42 kredit» konkret fənn deyil; onu
    `CurriculumSubject` kimi yazmaq planı uydurma fənnlə doldurardı.
    """

    def test_placeholders_never_reach_the_catalogue_match(self):
        rows = [
            {"no": 1, "code": "MİF – B03", "name": "Ali məktəb tərəfindən müəyyən edilən fənn",
             "credits": 4, "total_hours": None, "semester": ""},
            {"no": 2, "code": "MİF – B04", "name": "İxtisaslaşmaya ayrılan fənlər**",
             "credits": 42, "total_hours": None, "semester": ""},
        ]
        result = match_rows(rows, {})
        # Kataloqda yoxdur → uydurulmur, hesabata düşür; `--apply` onları yazmır.
        self.assertEqual(len(result["matched"]), 0)


class QuoteIdempotencyTest(SimpleTestCase):
    """Mənbə cədvəlindəki URL-lərin bir hissəsi ARTIQ faiz-kodlanmış yığılıb.

    İkinci dəfə kodlansa (`%20` → `%2520`) sayt 200 ilə HTML səhv səhifəsi
    qaytarır — 11 plan məhz buna görə «PDF deyil» olurdu.
    """

    def test_already_encoded_url_is_not_encoded_twice(self):
        from apps.registrar.management.commands.import_curriculum_plans import _quote

        encoded = "https://wcu.edu.az/uploads/files/050405%20%C4%B0qtisadiyyat%202023.pdf"
        raw = "https://wcu.edu.az/uploads/files/050405 İqtisadiyyat 2023.pdf"
        self.assertEqual(_quote(encoded), _quote(raw))
        self.assertNotIn("%2520", _quote(encoded))
