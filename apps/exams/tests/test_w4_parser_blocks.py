"""W4 2026-09-14 (w3sweep R5) — sual göndərişi mətn parseri.

Hesabatdakı giriş: «1. sual?\\nA) bir\\nB) iki*\\nC) üç\\n\\n2. İkinci sual\\nA) x*\\nB) y»
→ 1 sual çıxırdı, 2-ci sual 1-cinin C variantına yapışırdı; sonluq `*` markeri
tanınmırdı (sənəddə yalnız `*B)` prefiksi).

İndi: boş sətirdən sonra `N.` ilə başlayan sətir ≥ 2 variantlı sualı bağlayıb
yeni sual açır; `B) iki*` sonluq `*` düz cavab markeridir (mətndən silinir);
END_QUESTION blok formatında da eyni.
"""

from django.test import SimpleTestCase

from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.question_submission import analyze_submission_text

REPORT_INPUT = "1. sual?\nA) bir\nB) iki*\nC) üç\n\n2. İkinci sual\nA) x*\nB) y"


class BlankLineQuestionBoundaryTests(SimpleTestCase):
    def test_report_input_yields_two_questions_with_trailing_star_answers(self):
        questions = parse_bulk_mcq(REPORT_INPUT)
        self.assertEqual([q["q_no"] for q in questions], ["1", "2"])
        first, second = questions
        self.assertEqual(first["text"], "sual?")
        self.assertEqual(first["options"], {"A": "bir", "B": "iki", "C": "üç"})
        self.assertEqual(first["correct"], ["B"])
        self.assertEqual(second["text"], "İkinci sual")
        self.assertEqual(second["options"], {"A": "x", "B": "y"})
        self.assertEqual(second["correct"], ["A"])
        for q in questions:
            self.assertNotIn("correct_defaulted", [w["type"] for w in q["warnings"]])

    def test_analyze_submission_text_counts_two_questions(self):
        parsed, counts = analyze_submission_text(REPORT_INPUT)
        self.assertEqual(counts["questions"], 2)
        self.assertEqual(len(parsed), 2)

    def test_blank_line_boundary_with_full_five_options_and_unmarked_last_option(self):
        text = (
            "1. Paytaxt?\nA) Bakı*\nB) Gəncə\nC) Şəki\nD) Quba\nE) Lənkəran\n\n"
            "2. Çay?\nA) Kür*\nB) Araz\nC) Tərtər\nD) Qanıx\nE) Pirsaat"
        )
        questions = parse_bulk_mcq(text)
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["options"]["E"], "Lənkəran")
        self.assertEqual(questions[1]["options"]["A"], "Kür")
        self.assertEqual([q["correct"] for q in questions], [["A"], ["A"]])

    def test_numbered_line_after_blank_with_single_option_stays_option_continuation(self):
        # Yalnız 1 variant var → «2.» sətri sual sərhədi deyil (köhnə davranış qorunur).
        text = "1. sual?\nA) bir\n\n2. davam\nB) iki\nC) üç\nD) dörd"
        questions = parse_bulk_mcq(text)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["options"]["A"], "bir 2. davam")

    def test_numbered_line_without_blank_and_fewer_than_four_options_is_unchanged(self):
        # Boş sətir yoxdur, 3 variant → köhnə davranış (variant davamı) saxlanılır.
        text = "1. sual?\nA) bir\n*B) iki\nC) üç\n2. İkinci sual\nD) dörd"
        questions = parse_bulk_mcq(text)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["options"]["C"], "üç 2. İkinci sual")


class TrailingStarMarkerTests(SimpleTestCase):
    def test_trailing_star_with_space_and_prefix_star_are_equivalent(self):
        for variant in ("*B) iki", "B) iki*", "B) iki *"):
            text = f"1. sual?\nA) bir\n{variant}\nC) üç\nD) dörd"
            q = parse_bulk_mcq(text)[0]
            self.assertEqual(q["options"]["B"], "iki", variant)
            self.assertEqual(q["correct"], ["B"], variant)
            self.assertEqual(q["answer_mode"], "single", variant)

    def test_multiple_trailing_stars_give_multiple_answer_mode(self):
        text = "1. sual?\nA) bir*\nB) iki\nC) üç*\nD) dörd"
        q = parse_bulk_mcq(text)[0]
        self.assertEqual(q["correct"], ["A", "C"])
        self.assertEqual(q["answer_mode"], "multiple")
        self.assertEqual(q["options"]["A"], "bir")
        self.assertEqual(q["options"]["C"], "üç")

    def test_lone_star_option_text_is_not_stripped_to_empty(self):
        text = "1. sual?\nA) *\nB) iki*\nC) üç\nD) dörd"
        q = parse_bulk_mcq(text)[0]
        self.assertEqual(q["options"]["A"], "*")
        self.assertEqual(q["correct"], ["B"])

    def test_trailing_star_in_end_question_block_format(self):
        text = "1. sual?\nA) bir\nB) iki*\nC) üç\nD) dörd\nEND_QUESTION\n2. ikinci?\nA) x\nB) y\nC) z *\nD) w\nEND_QUESTION"
        questions = parse_bulk_mcq(text)
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["correct"], ["B"])
        self.assertEqual(questions[0]["options"]["B"], "iki")
        self.assertEqual(questions[1]["correct"], ["C"])
        self.assertEqual(questions[1]["options"]["C"], "z")
