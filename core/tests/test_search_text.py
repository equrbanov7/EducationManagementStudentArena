"""Kanonik dözümlü axtarış — ``core.search_text`` (sahib 2026-09-26).

Şikayət: kabinetin «Qruplar» səhifəsində «234k» 0 qrup qaytarırdı, halbuki
«234 K ing» var. Tələb: az hərfləri ilə yazanda en nəticə də gəlsin (və əksinə),
kod sahələrində («234king», «234-K-ing») ayırıcılar nəzərə alınmasın.

Təmiz (DB-siz) testlər şablonu və Python uyğunluğunu, DB testləri isə eyni
şablonun PostgreSQL ARE (``~*``) üzərində işlədiyini yoxlayır.
"""

import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from core.search_text import (
    MAX_TOKEN_LENGTH,
    MAX_TOKENS,
    fold_regex,
    tokens_of,
    tolerant_match,
    tolerant_q,
    tolerant_regex,
)

GROUP = "234 K ing"


class FoldRegexUnitTest(SimpleTestCase):
    def test_letter_classes_are_explicit(self):
        self.assertEqual(fold_regex("is"), "[iıİI][sSşŞ]")
        self.assertEqual(fold_regex("İ"), "[iıİI]")
        self.assertEqual(fold_regex("a"), "[aAəƏ]")
        self.assertEqual(fold_regex("ə"), "[əƏeEaA]")
        self.assertEqual(fold_regex("e"), "[eEəƏ]")
        self.assertEqual(fold_regex("K"), "[kK]")
        self.assertEqual(fold_regex("7"), "7")

    def test_digraphs(self):
        self.assertEqual(fold_regex("sh"), "(?:[sS][hH]|[şŞ])")
        self.assertEqual(fold_regex("Ch"), "(?:[cC][hH]|[çÇ])")
        self.assertEqual(fold_regex("gh"), "(?:[gG][hH]|[ğĞ])")
        self.assertEqual(fold_regex("kh"), "(?:[kK][hH]|[xX])")

    def test_metacharacters_escaped(self):
        self.assertEqual(fold_regex("1.2"), r"1\.2")
        for raw in ("(", "[a", "a|b", "^$", "a+*?", "\\", "{2}"):
            with self.subTest(raw=raw):
                re.compile(fold_regex(raw))  # sintaksis xətası yoxdur
                self.assertTrue(tolerant_match(raw, f"x{raw}y"))

    def test_compact_drops_separators_and_allows_them_between_chars(self):
        self.assertEqual(fold_regex("2-3", compact=True), r"2[\s._/-]*3")
        self.assertEqual(fold_regex("2 3", compact=False), r"2\ 3")
        self.assertEqual(tolerant_regex("2 3", loose_spaces=True), fold_regex("2 3", compact=True))

    def test_tokens_capped(self):
        self.assertEqual(tokens_of("  Aydan   Alyarova "), ["Aydan", "Alyarova"])
        self.assertEqual(len(tokens_of("a b c d e f")), MAX_TOKENS)
        self.assertEqual(len(tokens_of("x" * 500)[0]), MAX_TOKEN_LENGTH)
        self.assertEqual(tokens_of(None), [])

    def test_match_matrix(self):
        cases = (
            # (sorğu, mətn, compact, gözlənilən)
            ("234k", GROUP, True, True),
            ("234king", GROUP, True, True),
            ("234 king", GROUP, True, True),
            ("234 K ing", GROUP, True, True),
            ("234-K-ing", GROUP, True, True),
            ("234k ing", GROUP, True, True),
            ("234_k.ing", GROUP, True, True),
            ("234k1", "234 K-1", True, True),
            ("234king", GROUP, False, False),  # normal rejimdə ayırıcı tələb olunur
            ("235k", GROUP, True, False),
            ("Aliyev", "Əliyev", False, True),
            ("Eliyev", "Əliyev", False, True),
            ("Əliyev", "Aliyev", False, True),
            ("Aliyev", "Eliyev", False, False),  # e ↔ a YOX
            ("Sahzad", "Şahzad", False, True),
            ("Shahzad", "Şahzad", False, True),
            ("Şahzad", "Shahzad", False, True),
            ("Verilenler", "Verilənlər bazası", False, True),
            ("Chingiz", "Çingiz", False, True),
            ("Cingiz", "Çingiz", False, True),
            ("Aghayev", "Ağayev", False, True),
            ("Khalilov", "Xəlilov", False, True),
            ("Xəlilov", "Khalilov", False, True),
            ("ISMAYIL", "İsmayıl", False, True),
            ("ismayil", "İSMAYIL", False, True),
            ("Huseynov", "Hüseynov", False, True),
            ("Ozturk", "Öztürk", False, True),
            ("aydan alyarova", "Alyarova Aydan", False, True),
            ("aydan huseynov", "Alyarova Aydan", False, False),
            ("", "hər şey", False, True),
            # Qısa hərf tokeni kod rejimində də bitişik: «PA» «Qrup A»nı tapmır.
            ("PA", "Qrup A1-1", True, False),
            ("vb", "V B-1", True, False),
            ("vb1", "V B-1", True, True),
            ("sekidu", "seki-du", True, True),
            # Çox tokenli sorğu bitişdirilmiş halda da yoxlanır.
            ("234 kin g", GROUP, True, True),
            ("234 kin g", GROUP, False, False),
            # «İ».lower() → «i̇» (U+0307) — yaddaşda nöqtə atılır.
            ("ismayil", "İsmayıl".lower(), False, True),
        )
        for query, text, compact, expected in cases:
            with self.subTest(query=query, text=text, compact=compact):
                self.assertIs(tolerant_match(query, text, compact=compact), expected)

    def test_tolerant_match_any_text_per_token(self):
        self.assertTrue(tolerant_match("Aliyev 234k", "Əli Əliyev", GROUP, compact=True))
        self.assertFalse(tolerant_match("Aliyev 999", "Əli Əliyev", GROUP, compact=True))

    def test_tolerant_q_none_for_blank_or_no_fields(self):
        self.assertIsNone(tolerant_q("   ", ("first_name",)))
        self.assertIsNone(tolerant_q("abc", ()))

    def test_tolerant_q_shape(self):
        def leaves(node):
            for child in node.children:
                if isinstance(child, tuple):
                    yield child
                else:
                    yield from leaves(child)

        plain_only = tolerant_q("ab cd", ("first_name",))
        self.assertEqual(plain_only.connector, "AND")
        self.assertEqual(len(plain_only.children), 2)  # iki token VƏ ilə, bitişik alternativ YOX
        mixed = list(leaves(tolerant_q("ab cd", ("first_name",), compact_fields=("last_name",))))
        self.assertIn(("first_name__iregex", "[aAəƏ][bB]"), mixed)
        # «ab» qısa hərf tokenidir → kod sahəsində də bitişik; bitişdirilmiş «abcd» → kod rejimi.
        self.assertIn(("last_name__iregex", "[aAəƏ][bB]"), mixed)
        self.assertIn(("last_name__iregex", r"[aAəƏ][\s._/-]*[bB][\s._/-]*[cCçÇ][\s._/-]*[dD]"), mixed)
        coded = tolerant_q("ab12", (), compact_fields=("last_name",))
        self.assertEqual(list(leaves(coded)), [("last_name__iregex", r"[aAəƏ][\s._/-]*[bB][\s._/-]*1[\s._/-]*2")])


class TolerantQPostgresTest(TestCase):
    """Eyni şablonlar PostgreSQL ``~*`` ilə — collation-dan asılı olmadan."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.users = {
            key: User.objects.create_user(username=key, email=f"{key}@example.com", first_name=first, last_name=last)
            for key, first, last in (
                ("g_king", GROUP, "Qrup"),
                ("g_k1", "234 K-1", "Qrup"),
                ("aliyev", "Rəşad", "Əliyev"),
                ("sahzad", "Şahzad", "Məmmədov"),
                ("xalilov", "Xəyal", "Xəlilov"),
                ("ismayil", "İsmayıl", "Hüseynov"),
            )
        }

    def _find(self, query, **kwargs):
        User = get_user_model()
        q = tolerant_q(query, **kwargs)
        return set(User.objects.filter(q).values_list("username", flat=True))

    def test_compact_group_names(self):
        for query in ("234k", "234king", "234 king", "234 K ing", "234-K-ing", "234k ing"):
            with self.subTest(query=query):
                self.assertIn("g_king", self._find(query, fields=("first_name",), compact=True))
        self.assertEqual(self._find("234k1", fields=("first_name",), compact=True), {"g_k1"})
        self.assertEqual(self._find("234king", fields=("first_name",), compact=True), {"g_king"})
        self.assertEqual(self._find("234 kin g", fields=("first_name",), compact=True), {"g_king"})
        # Qısa hərf tokeni bitişik axtarılır: «Kİ» «K ing»i («K i») tapmır.
        self.assertEqual(self._find("ki", fields=("first_name",), compact=True), set())

    def test_person_names_transliteration(self):
        fields = ("first_name", "last_name", "username")
        for query, expected in (
            ("Aliyev", "aliyev"),
            ("Eliyev", "aliyev"),
            ("Resad Aliyev", "aliyev"),
            ("Sahzad", "sahzad"),
            ("Shahzad", "sahzad"),
            ("Khalilov", "xalilov"),
            ("ISMAYIL HUSEYNOV", "ismayil"),
            ("İsmayıl", "ismayil"),
        ):
            with self.subTest(query=query):
                self.assertEqual(self._find(query, fields=fields), {expected})

    def test_mixed_fields(self):
        found = self._find("qrup 234king", fields=("last_name",), compact_fields=("first_name",))
        self.assertEqual(found, {"g_king"})

    def test_hostile_input_is_literal(self):
        for raw in ("(", "[", "a|b", ".*", "\\", "^", "$", "{1,999}", "(?:x)"):
            with self.subTest(raw=raw):
                self.assertEqual(self._find(raw, fields=("first_name",)), set())
                self.assertEqual(self._find(raw, fields=("first_name",), compact=True), set())

    def test_longest_allowed_query_is_not_too_complex_for_postgres(self):
        """Ən uzun icazəli sorğu (4 × 40 simvol, ən «ağır» siniflər) ARE limitinə düşmür."""
        heavy = " ".join(("ş" * 40, "ç" * 40, "sh" * 20, "x" * 40, "ə" * 40))
        for compact in (False, True):
            with self.subTest(compact=compact):
                self.assertEqual(self._find(heavy, fields=("first_name", "last_name", "email"), compact=compact), set())
