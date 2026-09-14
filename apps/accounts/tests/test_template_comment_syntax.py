"""Çox-sətirli `{# … #}` şərhi Django-da ŞƏRH DEYİL — mətn kimi render olunur.

2026-09-11: «Profili redaktə et» səhifəsinin yuxarısında `{# Status İKİ
vəziyyətlidir … #}` yazısı çılpaq görünürdü (sahib: «açıq comment qalıb
görünən»). Django-nun `{# #}` sintaksisi YALNIZ tək sətir üçündür; sətir
keçidi olan şərh şablon mühərriki tərəfindən tanınmır və istifadəçiyə
göstərilir. Tarama daha iki belə yer tapdı (`register.html`,
`trial_exam_request.html`). Çox-sətirli şərh üçün `{% comment %}…{% endcomment %}`
işlədilməlidir — bu test onu kilidləyir.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

#: `{#` açılıb EYNİ sətirdə `#}` ilə bağlanmır.
_MULTILINE_HASH_COMMENT = re.compile(r"\{#(?![^\n]*#\})")


def _template_files():
    base = Path(settings.BASE_DIR)
    for root in ("apps", "templates"):
        yield from (base / root).rglob("*.html")


class TemplateCommentSyntaxTest(SimpleTestCase):
    def test_no_multiline_hash_comments(self):
        offenders = []
        for path in _template_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in _MULTILINE_HASH_COMMENT.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{line}")
        self.assertEqual(
            offenders,
            [],
            "Çox-sətirli `{# … #}` şərhi mətn kimi render olunur — "
            "`{% comment %}…{% endcomment %}` işlədin: " + ", ".join(offenders),
        )
