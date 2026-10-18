"""Sual mətnindəki kod nümunəsi (sahib 2026-10-19) — ``core.code_text`` + ``exam_filters.code_text``.

Qaydalar canlı imtahanın JS əkizi ilə EYNİDİR (tests/js/live_code_text.test.js): sətirlər birləşmir,
girinti saxlanılır, ```…``` açıq blokdur, istifadəçi mətni HTML kimi şərh olunmur.
"""

from django.template import Context, Template
from django.test import SimpleTestCase

from core.code_text import has_code_block, render_code_text, split_code_segments


class SplitCodeSegmentsTest(SimpleTestCase):
    def test_plain_prose_is_one_text_segment(self):
        text = "Azərbaycanın paytaxtı hansıdır?\nVariantlardan birini seçin."
        self.assertEqual(split_code_segments(text), [{"type": "text", "text": text}])
        self.assertFalse(has_code_block(text))
        self.assertFalse(has_code_block(None))

    def test_fenced_block_with_language_and_dedent(self):
        segments = split_code_segments("Nəticə nədir?\n```python\n  for i in range(3):\n      print(i)\n```\nSeçin.")
        self.assertEqual([s["type"] for s in segments], ["text", "code", "text"])
        self.assertEqual(segments[1], {"type": "code", "text": "for i in range(3):\n    print(i)", "lang": "python"})
        self.assertEqual(segments[2]["text"], "Seçin.")

    def test_unclosed_fence_and_crlf(self):
        self.assertEqual(split_code_segments("```\nx++"), [{"type": "code", "text": "x++", "lang": ""}])
        segments = split_code_segments("S:\r\n```\r\na = 1;\r\nb = 2;\r\n```")
        self.assertEqual(segments[1], {"type": "code", "text": "a = 1;\nb = 2;", "lang": ""})

    def test_pasted_code_without_fences(self):
        c = split_code_segments(
            "Aşağıdakı kodun nəticəsi nədir:\n#include <stdio.h>\nint main() {\n    int x = 5;\n\n"
            '    printf("%d", x);\n    return 0;\n}'
        )
        self.assertEqual([s["type"] for s in c], ["text", "code"])
        self.assertTrue(c[1]["text"].startswith("#include <stdio.h>\nint main() {\n    int x = 5;\n\n    printf"))
        py = split_code_segments("x = 5\nfor i in range(3):\n    x += i\nprint(x)\nCavab neçədir?")
        self.assertEqual(py[0]["text"], "x = 5\nfor i in range(3):\n    x += i\nprint(x)")
        self.assertEqual(py[1], {"type": "text", "text": "Cavab neçədir?"})

    def test_prose_is_not_code(self):
        for text in (
            "x = 5 olarsa, 2x + 3 neçədir?",
            "Hansı doğrudur?\n  a) birinci\n  b) ikinci",
            "Ali (tələbə)\nVəli (müəllim)",
            "Cavab:\nBakı",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_code_block(text))


class RenderCodeTextTest(SimpleTestCase):
    def test_markup_is_escaped_inside_code(self):
        html = render_code_text('Nə çap olunur?\n```html\n<img src=x onerror="alert(1)">\n```')
        self.assertNotIn("<img", html)
        self.assertIn('<code class="ems-code" translate="no" data-lang="html">&lt;img src=x onerror=', html)
        self.assertIn('<span class="ems-code-text">Nə çap olunur?</span>', html)

    def test_plain_text_is_only_escaped(self):
        self.assertEqual(render_code_text("<b>a</b>\nb"), "&lt;b&gt;a&lt;/b&gt;\nb")
        self.assertEqual(render_code_text(None), "")

    def test_template_filter(self):
        out = Template("{% load exam_filters %}<div>{{ t|code_text }}</div>").render(
            Context({"t": "Kod:\n```\nif (a) {\n  b();\n}\n```\n<script>x</script>"})
        )
        self.assertIn('<code class="ems-code" translate="no">if (a) {\n  b();\n}</code>', out)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", out)
        self.assertNotIn("<script>", out)
