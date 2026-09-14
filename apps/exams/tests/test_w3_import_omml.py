"""W3 2026-09-14 — OMML → LaTeX çevirici və LaTeX sanitizasiya (vahid testlər).

Binar DOCX lazım deyil: OMML XML əl ilə qurulur, hər konstruksiya ayrıca yoxlanır.
"""

from django.test import SimpleTestCase

from lxml import etree

from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.parsing.math_text import (
    FORMULA_MAX_LEN,
    find_formulas,
    math_summary,
    sanitize_math_text,
)
from apps.exams.services.parsing.media_markers import extract_media_refs, split_media_markers
from apps.exams.services.parsing.omml import omml_to_latex

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _omath(inner: str):
    return etree.fromstring(f'<m:oMath xmlns:m="{M}">{inner}</m:oMath>')


def _r(text: str) -> str:
    return f"<m:r><m:t>{text}</m:t></m:r>"


class OmmlToLatexTests(SimpleTestCase):
    def _latex(self, inner: str):
        latex, warnings = omml_to_latex(_omath(inner))
        return latex, warnings

    def test_fraction_variants(self):
        latex, warnings = self._latex(f"<m:f><m:num>{_r('a')}</m:num><m:den>{_r('b')}</m:den></m:f>")
        self.assertEqual(latex, "\\frac{a}{b}")
        self.assertEqual(warnings, [])
        latex, _ = self._latex(
            f'<m:f><m:fPr><m:type m:val="noBar"/></m:fPr><m:num>{_r("n")}</m:num><m:den>{_r("k")}</m:den></m:f>'
        )
        self.assertEqual(latex, "{n \\atop k}")
        latex, _ = self._latex(
            f'<m:f><m:fPr><m:type m:val="lin"/></m:fPr><m:num>{_r("1")}</m:num><m:den>{_r("2")}</m:den></m:f>'
        )
        self.assertEqual(latex, "{1}/{2}")

    def test_sub_sup_and_pre(self):
        latex, _ = self._latex(f"<m:sSup><m:e>{_r('x')}</m:e><m:sup>{_r('2')}</m:sup></m:sSup>")
        self.assertEqual(latex, "{x}^{2}")
        latex, _ = self._latex(f"<m:sSub><m:e>{_r('a')}</m:e><m:sub>{_r('i')}</m:sub></m:sSub>")
        self.assertEqual(latex, "{a}_{i}")
        latex, _ = self._latex(
            f"<m:sSubSup><m:e>{_r('x')}</m:e><m:sub>{_r('i')}</m:sub><m:sup>{_r('2')}</m:sup></m:sSubSup>"
        )
        self.assertEqual(latex, "{x}_{i}^{2}")
        latex, _ = self._latex(f"<m:sPre><m:sub>{_r('a')}</m:sub><m:sup>{_r('b')}</m:sup><m:e>{_r('X')}</m:e></m:sPre>")
        self.assertEqual(latex, "{}_{a}^{b}{X}")

    def test_radical_with_and_without_degree(self):
        latex, _ = self._latex(f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{_r("x")}</m:e></m:rad>')
        self.assertEqual(latex, "\\sqrt{x}")
        latex, _ = self._latex(f"<m:rad><m:deg>{_r('3')}</m:deg><m:e>{_r('x')}</m:e></m:rad>")
        self.assertEqual(latex, "\\sqrt[3]{x}")

    def test_nary_sum_and_integral_limits(self):
        latex, _ = self._latex(
            '<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr>'
            f"<m:sub>{_r('i=1')}</m:sub><m:sup>{_r('n')}</m:sup><m:e>{_r('i')}</m:e></m:nary>"
        )
        self.assertEqual(latex, "\\sum\\limits_{i=1}^{n} i")
        latex, _ = self._latex(
            f"<m:nary><m:naryPr/><m:sub>{_r('0')}</m:sub><m:sup>{_r('1')}</m:sup><m:e>{_r('x')}</m:e></m:nary>"
        )
        self.assertEqual(latex, "\\int_{0}^{1} x")
        latex, _ = self._latex(
            '<m:nary><m:naryPr><m:chr m:val="∏"/><m:subHide m:val="1"/><m:supHide m:val="1"/></m:naryPr>'
            f"<m:sub>{_r('k')}</m:sub><m:sup>{_r('n')}</m:sup><m:e>{_r('a')}</m:e></m:nary>"
        )
        self.assertEqual(latex, "\\prod a")

    def test_delimiters_matrix_and_function(self):
        latex, _ = self._latex(f"<m:d><m:e>{_r('a+b')}</m:e></m:d>")
        self.assertEqual(latex, "\\left( a+b \\right)")
        latex, _ = self._latex(
            '<m:d><m:dPr><m:begChr m:val="{"/><m:endChr m:val=""/></m:dPr>'
            f"<m:e>{_r('x')}</m:e><m:e>{_r('y')}</m:e></m:d>"
        )
        self.assertEqual(latex, "\\left\\{ x | y \\right.")
        latex, _ = self._latex(
            f"<m:m><m:mr><m:e>{_r('1')}</m:e><m:e>{_r('0')}</m:e></m:mr>"
            f"<m:mr><m:e>{_r('0')}</m:e><m:e>{_r('1')}</m:e></m:mr></m:m>"
        )
        self.assertEqual(latex, "\\begin{matrix} 1 & 0 \\\\ 0 & 1 \\end{matrix}")
        latex, _ = self._latex(f"<m:func><m:fName>{_r('sin')}</m:fName><m:e>{_r('x')}</m:e></m:func>")
        self.assertEqual(latex, "\\sin x")
        latex, _ = self._latex(f"<m:func><m:fName>{_r('sinc')}</m:fName><m:e>{_r('x')}</m:e></m:func>")
        self.assertEqual(latex, "\\operatorname{sinc} x")

    def test_limit_accent_bar_group_eqarr_boxed(self):
        latex, _ = self._latex(
            f"<m:func><m:fName><m:limLow><m:e>{_r('lim')}</m:e><m:lim>{_r('x→0')}</m:lim></m:limLow></m:fName>"
            f"<m:e>{_r('f(x)')}</m:e></m:func>"
        )
        self.assertEqual(latex, "\\underset{x\\to 0}{\\lim } f(x)")
        latex, _ = self._latex(f'<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr><m:e>{_r("v")}</m:e></m:acc>')
        self.assertEqual(latex, "\\vec{v}")
        latex, _ = self._latex(f"<m:acc><m:e>{_r('x')}</m:e></m:acc>")
        self.assertEqual(latex, "\\hat{x}")
        latex, _ = self._latex(f"<m:bar><m:e>{_r('z')}</m:e></m:bar>")
        self.assertEqual(latex, "\\overline{z}")
        latex, _ = self._latex(f"<m:groupChr><m:e>{_r('abc')}</m:e></m:groupChr>")
        self.assertEqual(latex, "\\underbrace{abc}")
        latex, _ = self._latex(f"<m:eqArr><m:e>{_r('x=1')}</m:e><m:e>{_r('y=2')}</m:e></m:eqArr>")
        self.assertEqual(latex, "\\begin{aligned} x=1 \\\\ y=2 \\end{aligned}")
        latex, _ = self._latex(f"<m:borderBox><m:e>{_r('E=mc^2')}</m:e></m:borderBox>")
        self.assertEqual(latex, "\\boxed{E=mc\\wedge 2}")

    def test_unicode_greek_and_operators_become_macros(self):
        latex, warnings = self._latex(_r("α+β≤π×2"))
        self.assertEqual(latex, "\\alpha +\\beta \\le \\pi \\times 2")
        self.assertEqual(warnings, [])

    def test_normal_text_run_wrapped_in_text(self):
        latex, _ = self._latex("<m:r><m:rPr><m:nor/></m:rPr><m:t>if x</m:t></m:r>")
        self.assertEqual(latex, "\\text{if x}")

    def test_unknown_node_falls_back_to_text_with_warning(self):
        latex, warnings = self._latex(f"<m:foo><m:e>{_r('qq')}</m:e></m:foo>")
        self.assertEqual(latex, "\\text{qq}")
        self.assertEqual(warnings, ["foo"])

    def test_omath_para_joins_multiple_formulas(self):
        element = etree.fromstring(
            f'<m:oMathPara xmlns:m="{M}"><m:oMath>{_r("a")}</m:oMath><m:oMath>{_r("b")}</m:oMath></m:oMathPara>'
        )
        latex, warnings = omml_to_latex(element)
        self.assertEqual(latex, "a b")
        self.assertEqual(warnings, [])


class MathTextSanitizerTests(SimpleTestCase):
    def test_finds_all_standard_delimiters(self):
        found = find_formulas("a $x$ b $$y$$ c \\(z\\) d \\[w\\]")
        self.assertEqual([(f.body, f.display) for f in found], [("x", False), ("y", True), ("z", False), ("w", True)])

    def test_currency_like_dollars_are_not_formulas(self):
        self.assertEqual(find_formulas("Qiymət $5 və $10 arasındadır"), [])
        text, issues = sanitize_math_text("Qiymət $5 və $10 arasındadır")
        self.assertEqual(text, "Qiymət $5 və $10 arasındadır")
        self.assertEqual(issues, [])

    def test_canonicalises_delimiters_and_collapses_newlines(self):
        text, issues = sanitize_math_text("Hesabla $\\frac{a}{b}$ və $$x\n+y$$")
        self.assertEqual(text, "Hesabla \\(\\frac{a}{b}\\) və \\[x +y\\]")
        self.assertEqual(issues, [])

    def test_denied_commands_are_neutralised_with_issue(self):
        for command in (
            "\\href{http://x}{y}",
            "\\url{http://x}",
            "\\includegraphics{a}",
            "\\def\\x{1}",
            "\\newcommand{\\a}{b}",
        ):
            text, issues = sanitize_math_text(f"Bax $ {command} $ burada")
            self.assertNotIn("$", text, command)
            self.assertNotIn("\\(", text, command)
            self.assertEqual(issues[0]["type"], "formula_denied", command)
            self.assertTrue(issues[0]["command"].startswith("\\"), command)

    def test_over_long_formula_is_neutralised(self):
        text, issues = sanitize_math_text("$" + "x" * (FORMULA_MAX_LEN + 1) + "$")
        self.assertNotIn("$", text)
        self.assertEqual(issues[0]["type"], "formula_too_long")

    def test_summary_counts(self):
        self.assertEqual(math_summary("$a$ $$b$$ plain"), {"count": 2, "display": 1})
        self.assertEqual(math_summary("plain"), {"count": 0, "display": 0})


class MediaMarkerTests(SimpleTestCase):
    def test_split_markers(self):
        self.assertEqual(split_media_markers("Sual [[img:1]] mətni [[img:2]]"), ("Sual mətni", [1, 2]))
        self.assertEqual(split_media_markers("marker yoxdur"), ("marker yoxdur", []))

    def test_extract_refs_from_question_and_options(self):
        question = {"text": "Şəkli izah edin [[img:1]]", "options": {"A": "[[img:2]]", "B": "mətn"}}
        refs = extract_media_refs(question)
        self.assertEqual(refs, {"stem": [1], "A": [2]})
        self.assertEqual(question["text"], "Şəkli izah edin")
        self.assertEqual(question["options"], {"A": "—", "B": "mətn"})
        self.assertNotIn("media_refs", {"text": "x", "options": {}}.keys())

    def test_parser_strips_markers_and_sanitises_math(self):
        raw = "\n".join(
            [
                "1. Kəsri hesablayın: $\\frac{a}{b}$",
                "[[img:1]]",
                "A) 1",
                "*B) [[img:2]]",
                "C) 3",
                "D) $\\href{x}{y}$",
                "E) 5",
            ]
        )
        [question] = parse_bulk_mcq(raw)
        self.assertEqual(question["text"], "Kəsri hesablayın: \\(\\frac{a}{b}\\)")
        self.assertEqual(question["media_refs"], {"stem": [1], "B": [2]})
        self.assertEqual(question["options"]["B"], "—")
        self.assertEqual(question["options"]["D"], "href{x}{y}")
        self.assertEqual(question["correct"], ["B"])
        self.assertIn("formula_denied", [w["type"] for w in question["warnings"]])
