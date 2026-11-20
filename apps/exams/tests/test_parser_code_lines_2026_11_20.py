"""Sahib 2026-11-20: idxalda kod nümunəsi bir sətrə birləşirdi — sətir sonu və girinti saxlanmalıdır."""

from django.test import SimpleTestCase

from apps.exams.services.parsing._core import parse_bulk_mcq
from core.code_text import render_code_text

RAW = """21. Aşağıdakı kodun nəticəsi nə olacaq?
a = 12
if a > 8:
    print(a - 8)
else:
    print(a + 8)

A) 4
B) 8
C) 12
D) 20

63. Hansı kod təkrarları silir?

A)
result = []
for x in values:
    if x not in result:
        result.append(x)

B)
result = []
for x in values:
    result.append(x)

C) result = values
D) result = set(values)
"""


class ParserCodeLinesTest(SimpleTestCase):
    def test_question_code_keeps_lines_and_indent(self):
        q = parse_bulk_mcq(RAW)[0]
        self.assertEqual(
            q["text"],
            "Aşağıdakı kodun nəticəsi nə olacaq?\na = 12\nif a > 8:\n    print(a - 8)\nelse:\n    print(a + 8)",
        )
        self.assertIn('<code class="ems-code"', render_code_text(q["text"]))

    def test_bare_label_option_holds_code_block(self):
        q = parse_bulk_mcq(RAW)[1]
        self.assertEqual(
            q["options"]["A"], "result = []\nfor x in values:\n    if x not in result:\n        result.append(x)"
        )
        self.assertEqual(q["options"]["C"], "result = values")
        self.assertEqual(sorted(q["options"]), ["A", "B", "C", "D"])
        self.assertNotIn("_block_options", q)


class ParserDotCodeLineTest(SimpleTestCase):
    def test_method_call_line_is_not_option(self):
        raw = (
            "2. Nəticə nə olacaq?\na = [1, 2]\nb = a\nb.append(3)\nprint(a)\n\nA) [1, 2, 3]\nB) [1, 2]\nC) [3]\nD) []\n"
        )
        q = parse_bulk_mcq(raw)[0]
        self.assertEqual(q["text"], "Nəticə nə olacaq?\na = [1, 2]\nb = a\nb.append(3)\nprint(a)")
        self.assertEqual(q["options"]["B"], "[1, 2]")

    def test_dot_label_with_space_still_option(self):
        q = parse_bulk_mcq("1. Sual?\nA. bir\nB. iki\nC. üç\nD. dörd\n")[0]
        self.assertEqual(q["options"], {"A": "bir", "B": "iki", "C": "üç", "D": "dörd"})
