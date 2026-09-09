"""«Tədris planı» PDF idxalının UYĞUNLAŞDIRMA qatı (2026-09-09).

PDF oxunuşu (`extract_rows`) burada sınanmır — o, xarici fayl tələb edir.
Sınanan şey RİSKLİ hissədir: adların normallaşdırılması və sətirlərin
təsnifatı, çünki səhv uyğunluq planı sükutla korlayır.
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import Organization
from apps.registrar.models import Subject
from apps.registrar.plan_import import is_elective_block, is_placeholder, match_rows, normalize
from apps.registrar.plan_manual import SITE_CODE_PREFIX, SubjectCreator, load_manual_plans
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


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
            {
                "no": 1,
                "code": "MİF – B03",
                "name": "Ali məktəb tərəfindən müəyyən edilən fənn",
                "credits": 4,
                "total_hours": None,
                "semester": "",
            },
            {
                "no": 2,
                "code": "MİF – B04",
                "name": "İxtisaslaşmaya ayrılan fənlər**",
                "credits": 42,
                "total_hours": None,
                "semester": "",
            },
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


class RealWorldPlaceholderSpellingTest(SimpleTestCase):
    """2026-09-10: sənədlər eyni YER TUTUCUnu bir neçə cür yazır.

    Bu üç yazılış `unknown` səbətinə düşürdü, yəni `--create-subjects` onları
    kataloqa UYDURMA fənn kimi yazardı. Adlar hesabatdakı real sətirlərdir.
    """

    def test_every_spelling_seen_in_the_documents_is_a_placeholder(self):
        for name in (
            "Ali məktəbin müəyyən etdiyi fənn",  # «etdiyi» — «edilən» deyil
            "Ali məktəbin müəyyən etdiyi fənn:",
            "Ali təhsil müəssisəsi tərəfindən müəyyən edilən fənlər",
            "Seçmə fənlər*",  # tək «n» ilə
            "Ali məktəb tərəfindən müəyyən edilən fənn",
            "İxtisaslaşmaya ayrılan fənlər**",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_placeholder(name))

    def test_real_subjects_are_not_swallowed(self):
        """Genişlədilmiş qayda ƏSL fənni udmamalıdır (yoxsa plan sətir itirər)."""
        for name in ("Ali riyaziyyat", "Ali cəbr", "Seçim nəzəriyyəsi", "Ekologiya mühəndisliyi"):
            with self.subTest(name=name):
                self.assertFalse(is_placeholder(name))


class NumberedElectiveBlockTest(SimpleTestCase):
    """«blok» sözündən sonra NÖMRƏLƏNMİŞ siyahı gəlirsə — bir neçə fənndir.

    Bu yazılışlar nə rum rəqəmi ilə başlayır, nə də «blok»dan sonra iki nöqtə
    gəlir; köhnə qayda onları tutmurdu və 16 sətir «tapılmayan fənn» sayılırdı.
    """

    def test_numbered_blocks_are_detected(self):
        for name in (
            "I Seçmə fənn bloku: 1.Bioloji müxtəliflik 2.Hüceyrənin molekulyar biologiyası",
            "III seçmə fənn bloku 1.Canlı orqanizmlər 2.Balıqların stresi",
            "ÜFS I blok 1.Fəlsəfə 2. Multikulturalizmə giriş",
            "ÜFS-2 blok 1.İnformasiya texnologiyaları (ixtisas üzrə)",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_elective_block(name))

    def test_subject_named_after_a_block_word_is_not_a_block(self):
        self.assertFalse(is_elective_block("Blokçeyn texnologiyaları"))


class ManualPlanFileTest(SimpleTestCase):
    """Skan PDF-lərin əl ilə köçürülmüş cədvəli (`--manual`).

    Sətirlər PDF sətirləri ilə EYNİ formada olmalıdır, yoxsa `_write_plan`
    `KeyError` verər — axın mənbənin növünü bilməməlidir.
    """

    def test_rows_carry_the_same_keys_as_pdf_rows(self):
        entries = load_manual_plans()
        self.assertTrue(entries, "manual_plans.json boşdur")
        for entry in entries:
            for key in ("seviyye", "proqram", "sayt_adi", "senet", "url", "niye_elle"):
                self.assertIn(key, entry)
            for row in entry["rows"]:
                self.assertEqual({"no", "code", "name", "credits", "total_hours", "semester"} - set(row), set())


class CreateSubjectsSafetyTest(TestCase):
    """`--create-subjects` NƏYİ yaratmır — bu rejimin ƏN RİSKLİ hissəsi.

    Sahib (2026-09-10): «əsas məsələ onların burada olmasıdır» — yəni rəsmi
    planda olan fənn kataloqda da olmalıdır. Amma planın hər sətri fənn DEYİL:
    seçmə bloklar bir xanada bir neçə fənndir, yer tutucular isə sonradan
    doldurulan boş yerdir. Onlardan `Subject` yaratmaq kataloqu UYDURMA
    yazılarla doldurar və geri qaytarmaq əl işi olar.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("plan_owner", "plan_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Plan Univ",
                slug="plan-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    @staticmethod
    def _row(no, name, credits=5):
        return {"no": no, "code": "", "name": name, "credits": credits, "total_hours": None, "semester": ""}

    def _rows(self):
        return [
            self._row(1, "Ekoloji monitorinq", 6),  # ƏSL fənn — yaradılmalıdır
            self._row(2, "I blok: 1. Sosiologiya 2. AR Konstitusiyası", 3),
            self._row(3, "ÜFS I blok 1.Fəlsəfə 2. Multikulturalizmə giriş", 3),
            self._row(4, "Ali məktəbin müəyyən etdiyi fənn", 4),
            self._row(5, "Ali təhsil müəssisəsi tərəfindən müəyyən edilən fənlər", 60),
            self._row(6, "Seçmə fənlər*", 3),
        ]

    def _absorb(self, rows, catalogue, **kwargs):
        with bypass_rls():
            result = match_rows(rows, catalogue)
            created = SubjectCreator(self.org, catalogue, **kwargs).absorb(result, {"sayt_adi": "Sınaq"})
        return result, created

    def test_only_the_real_subject_is_created(self):
        catalogue = {}
        result, created = self._absorb(self._rows(), catalogue, dry_run=False)

        self.assertEqual(created, 1)
        with bypass_rls():
            names = list(Subject.objects.filter(organization=self.org).values_list("name", flat=True))
        self.assertEqual(names, ["Ekoloji monitorinq"])
        # Sətir `matched`-ə keçir ki, plan onu göstərə bilsin.
        self.assertEqual([row["name"] for row in result["matched"]], ["Ekoloji monitorinq"])
        self.assertEqual(result["unknown"], [])
        # Blok və yer tutucu ÖZ səbətlərində qalır — heç vaxt `unknown`-a düşmür.
        self.assertEqual(len(result["electives"]), 2)
        self.assertEqual(len(result["placeholders"]), 3)

    def test_created_subject_carries_code_credits_and_provenance(self):
        catalogue = {}
        self._absorb(self._rows(), catalogue, dry_run=False)
        with bypass_rls():
            subject = Subject.objects.get(organization=self.org, name="Ekoloji monitorinq")
        self.assertTrue(subject.code.startswith(f"{SITE_CODE_PREFIX}-"))
        self.assertEqual(subject.ects, 6)
        self.assertIn("Sınaq", subject.description)

    def test_absurd_credit_falls_back_to_the_model_default(self):
        """Kredit sütunu bəzən sürüşür — 240 kreditli «fənn» kataloqu korlayar."""
        catalogue = {}
        self._absorb([self._row(1, "Sürüşmüş sətir", 240)], catalogue, dry_run=False)
        with bypass_rls():
            subject = Subject.objects.get(organization=self.org, name="Sürüşmüş sətir")
        self.assertEqual(subject.ects, Subject._meta.get_field("ects").default)

    def test_same_name_in_a_later_plan_is_reused_not_duplicated(self):
        """Kataloq lüğəti YERİNDƏ yenilənir — eyni icrada təkrar yaradılmır."""
        catalogue = {}
        with bypass_rls():
            creator = SubjectCreator(self.org, catalogue, dry_run=False)
            first = match_rows([self._row(1, "Ekoloji monitorinq", 6)], catalogue)
            self.assertEqual(creator.absorb(first, {}), 1)
            second = match_rows([self._row(1, "Ekoloji  monitorinq", 6)], catalogue)
            self.assertEqual(creator.absorb(second, {}), 0)
            self.assertEqual(Subject.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(second["matched"][0]["subject"], first["matched"][0]["subject"])

    def test_report_mode_writes_nothing(self):
        """`--apply`-siz icra QURU olmalıdır — hesabat bazaya toxunmur."""
        catalogue = {}
        _, created = self._absorb(self._rows(), catalogue, dry_run=True)
        self.assertEqual(created, 1)
        with bypass_rls():
            self.assertEqual(Subject.objects.filter(organization=self.org).count(), 0)
