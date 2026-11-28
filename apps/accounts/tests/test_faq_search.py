"""The ranker reads only effective, visible FAQ entries, with no ORM access."""

from dataclasses import replace

from django.test import SimpleTestCase

from apps.accounts.views.profile.faq_catalog import BUILTIN_BY_KEY, Guide
from apps.accounts.views.profile.faq_editor_catalog import TenantGuide
from apps.accounts.views.profile.faq_search import rank_guides, search_words


def custom(key, title, topic="", *, chapters=(), steps=(), aliases=""):
    return TenantGuide(
        key=key,
        title=title,
        topic=topic,
        section="",
        destination="",
        video="",
        steps=steps,
        aliases=aliases,
        chapter_rows=tuple({"start": start, "title": text} for start, text in chapters),
    )


class FaqSearchTest(SimpleTestCase):
    def test_keyboard_spellings_diacritics_and_codes(self):
        for query, expected in (
            ("PİNKOD", ["pinkod"]),
            ("Pın kodu", ["pinkodu"]),
            ("PIN-kod", ["pinkod"]),
            ("Q/B, İ/Ə və I/E", ["qb", "ie", "ve", "ie"]),
            ("S\u0327ifrə SHIFRE", ["sifre", "sifre"]),
            ("C\u0327ıxış, chixish", ["cixis", "cixis"]),
        ):
            with self.subTest(query=query):
                self.assertEqual(search_words(query), expected)

    def test_expected_real_student_questions_rank_on_top(self):
        visible = [
            BUILTIN_BY_KEY[key] for key in ("exam-pin", "grades", "journal-limit", "quiz-start", "student-syllabus")
        ]
        for query, expected in (
            ("qiymetim", "grades"),
            ("qiymətlərimə", "grades"),
            ("netice", "grades"),
            ("pinkod", "exam-pin"),
            ("pin kodumu", "exam-pin"),
            ("Q/B", "journal-limit"),
            ("İ/E", "journal-limit"),
            ("qayib", "journal-limit"),
            ("sillabus", "student-syllabus"),
        ):
            with self.subTest(query=query):
                self.assertEqual(rank_guides(visible, query)[0].guide.key, expected)

    def test_exact_topic_and_phrase_beat_incidental_mentions(self):
        passing = custom("x", "Müraciətin nəticəsini necə yoxlayım?", steps=("Qrafik nəticələr",))
        subject = custom("y", "Hansı məlumatlar görünür?", "Nəticələrim")
        self.assertIs(rank_guides([passing, subject], "neticə")[0].guide, subject)
        reversed_terms = custom("reverse", "Cədvəl və dərs")
        ordered = custom("order", "Dərs cədvəli")
        self.assertIs(rank_guides([reversed_terms, ordered], "ders cedveli")[0].guide, ordered)

    def test_distinctive_chapter_has_exact_timestamp_and_beats_text(self):
        steps = custom("text", "Yardım", steps=("İmtahan protokolunu yüklə.",))
        clip = custom(
            "video", "Nəticələrlə iş", chapters=((0.0, "Hesaba daxil ol"), (84.375, "İmtahan protokolunu yüklə"))
        )
        first, second = rank_guides([steps, clip], "imtahan protokolunu yukle")
        self.assertIs(first.guide, clip)
        self.assertEqual((first.chapter_start, first.chapter_title), (84.375, "İmtahan protokolunu yüklə"))
        self.assertIs(second.guide, steps)
        self.assertIsNone(second.chapter_start)

    def test_title_can_supply_subject_of_a_specific_chapter(self):
        hit = rank_guides([BUILTIN_BY_KEY["syllabus"]], "sillabusu redakte")[0]
        chapter = next(c for c in hit.guide.chapters if "Redaktə" in c["title"])
        self.assertEqual((hit.chapter_start, hit.chapter_title), (chapter["start"], chapter["title"]))

    def test_false_chapter_from_unrelated_tour_stops_is_not_reported(self):
        guide = custom("tour", "Kabinetə baxış", chapters=((0, "Kitabxana"), (2.75, "Transkript")))
        self.assertEqual(rank_guides([guide], "kitabxana transkript"), [])
        first = rank_guides([guide], "kitabxana")[0]
        self.assertEqual(first.chapter_start, 0)

    def test_morphology_typo_transposition_and_typing_prefix(self):
        guide = custom("doc", "İmtahan nəticələrindən apellyasiya", "Sillabus")
        for query in ("neticem", "netice", "apelyasiya", "apellyasiyadan", "sillbaus", "sillab", "sllabus"):
            with self.subTest(query=query):
                self.assertIs(rank_guides([guide], query)[0].guide, guide)

    def test_unknown_code_short_substring_and_punctuation_have_no_hits(self):
        guide = custom("balance", "Balans və kod 12344")
        for query in ("bal", "12345", "123XYZ?", "!!!", "z" * 40, "abcXqz nəticə"):
            with self.subTest(query=query):
                self.assertEqual(rank_guides([guide], query), [])

    def test_hidden_and_replaced_guides_cannot_reenter_from_the_index(self):
        old = BUILTIN_BY_KEY["exam-pin"]
        self.assertTrue(rank_guides([old], "pinkod"))
        overlay = custom(old.key, "Pambıq təlimatı", chapters=((16.875, "Pambıq"),))
        self.assertEqual(rank_guides([overlay], "pinkod"), [])
        self.assertEqual(rank_guides([], "pinkod"), [])
        hit = rank_guides([overlay], "pambiq")[0]
        self.assertIs(hit.guide, overlay)
        self.assertEqual(hit.chapter_start, 16.875)

    def test_empty_search_and_ties_preserve_effective_catalog_order(self):
        first = Guide("a", "İmtahan balı", "", "", "", "", ())
        second = replace(first, key="b")
        for query in ("", " \t", "imtahan"):
            with self.subTest(query=query):
                self.assertEqual([h.guide for h in rank_guides([second, first], query)], [second, first])
