"""Kabinet bölmələrində başlıq TƏKRARI və inline `style` qadağası (audit P2-1 / P2-9).

2026-09-12. Kabinet qabığı (`accounts/profile/_header.html`) bölmə adını artıq
`<h1 id="profileSectionTitle">` kimi render edir. Buna baxmayaraq 13 bölmə
şablonu (`.section-title`, `.rim-title`, `.smx-title`, `.apx-head__title`,
`_my_courses` isə üstəlik QONŞU bölmənin adını) eyni başlığı kartın içində
İKİNCİ dəfə yazırdı — sahib: «titlelər 2 dəfə təkrarlanmasın». Bu test onu
kilidləyir: bölmə şablonu `<h1` YAZMIR (yalnız qabıq), köhnə başlıq sinifləri
işlətmir, `ems_ui/_content_header.html`-ə `header_title` ötürmür (müqavilə:
yalnız `header_subtitle` / əməllər). Kart İÇİNDƏKİ həqiqi alt-başlıq üçün ad
`.section-card__title`-dır (layout.css).

İkinci test (P2-9): CSP `style-src-attr` üçün `unsafe-inline` müvəqqətidir
(config/settings/components/csp.py) — hədəf şablonda SIFIR `style="…"`.
Yeganə icazəli forma CLAUDE.md-nin dinamik dəyər üçün nəzərdə tutduğu
`style="--pct:…%"` custom property-dir (fasiləsiz faiz — tərəqqi zolağı eni);
o da yalnız aşağıdakı açıq allow-list-də sayılan yerlərdə. Yeni tərəqqi
zolağı əlavə edən allow-list-i ŞÜURLU şəkildə genişləndirməlidir.

Üçüncü test (P2-4): `<script>` gövdəsinə `{{ … |safe }}` ilə xam JSON yazmaq
qadağandır (`</script>` / `<!--` qaçırılmır) — Django `json_script` işlədilir
(`_workload_distribution.html` `wl-catalog` nümunəsi).

Skan `test_template_comment_syntax.py` ilə eyni üsuldadır (fayl sistemi,
DB yox); şablon şərhləri (`{% comment %}…{% endcomment %}`, `{# … #}`)
əvvəlcə silinir ki, «niyə yazılmır» izahları yalançı tapıntı verməsin.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SECTIONS_DIR = Path(settings.BASE_DIR) / "apps" / "accounts" / "templates" / "accounts" / "profile" / "sections"

_BLOCK_COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
_LINE_COMMENT = re.compile(r"\{#.*?#\}")

#: (nümunə, izah) — şərhlər silindikdən sonra bölmə şablonunda OLMAMALIDIR.
FORBIDDEN_TITLE_PATTERNS = (
    ("<h1", 'yalnız qabıq `<h1 id="profileSectionTitle">` render edir'),
    ('class="section-title', "köhnə təkrar-başlıq sinfi; kart alt-başlığı üçün `.section-card__title`"),
    ("rim-title", "RİM mərkəzi başlığı qabıqdan gəlir"),
    ("smx-title", "Sistem monitorinqi başlığı qabıqdan gəlir"),
    ("apx-head__title", "Müraciətlər başlığı qabıqdan gəlir"),
    ("header_title=", "`_content_header.html`-ə kabinetdə yalnız `header_subtitle` ötürülür"),
)

#: Yeganə icazəli inline forma: `style="--pct:{{ … }}%"` və ya `style="--pct:{% widthratio … %}%"`.
_ALLOWED_STYLE = re.compile(r'style="--pct:(?:\{\{[^}]*\}\}|\{%\s*widthratio [^%]*%\})%"')

#: Açıq allow-list — fayl (sections/ kökünə nisbətən) → icazəli `--pct` sayı.
#: _my_subjects: kredit tərəqqisi + giriş balı + qayıb zolağı; _semester_opening: kafedra hazırlıq faizi.
ALLOWED_PCT_STYLES = {
    "_my_subjects.html": 3,
    "_semester_opening.html": 1,
}


def _strip_template_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _section_templates():
    return sorted(SECTIONS_DIR.rglob("*.html"))


def _line_of(text: str, index: int) -> int:
    return text[:index].count("\n") + 1


class CabinetNoDuplicateTitlesTest(SimpleTestCase):
    def test_sections_dir_exists(self):
        self.assertTrue(SECTIONS_DIR.is_dir(), SECTIONS_DIR)
        self.assertGreater(len(_section_templates()), 50)

    def test_no_duplicate_section_titles(self):
        offenders = []
        for path in _section_templates():
            text = _strip_template_comments(path.read_text(encoding="utf-8", errors="replace"))
            rel = path.relative_to(SECTIONS_DIR)
            for needle, why in FORBIDDEN_TITLE_PATTERNS:
                for match in re.finditer(re.escape(needle), text):
                    offenders.append(f"{rel}:{_line_of(text, match.start())} `{needle}` — {why}")
        self.assertEqual(
            offenders,
            [],
            "Kabinet bölməsi başlığı təkrarlayır (qabıq `#profileSectionTitle` onsuz da verir): "
            + "; ".join(offenders),
        )


class CabinetNoInlineStyleTest(SimpleTestCase):
    def test_no_inline_style_attributes(self):
        offenders = []
        pct_counts = {}
        for path in _section_templates():
            text = _strip_template_comments(path.read_text(encoding="utf-8", errors="replace"))
            rel = str(path.relative_to(SECTIONS_DIR))
            for match in re.finditer(r'style="', text):
                allowed = _ALLOWED_STYLE.match(text, match.start())
                if allowed and rel in ALLOWED_PCT_STYLES:
                    pct_counts[rel] = pct_counts.get(rel, 0) + 1
                    continue
                offenders.append(f"{rel}:{_line_of(text, match.start())}")
        self.assertEqual(
            offenders,
            [],
            'Kabinet şablonunda inline `style="…"` qadağandır (CSP: unsafe-inline yox) — '
            'statik dəyəri CSS sinfinə, dinamik faizi `style="--pct:…%"` + allow-list-ə köçürün: '
            + ", ".join(offenders),
        )
        # Allow-list ŞİŞMƏSİN də, ÖLÜ də qalmasın: saylar dəqiq üst-üstə düşür.
        self.assertEqual(pct_counts, ALLOWED_PCT_STYLES)


#: `<script …>{{ … |safe }}` — açılış teqindən sonra ilk şey `|safe`-li dəyişəndir.
_RAW_SAFE_SCRIPT = re.compile(r"<script\b[^>]*>\s*\{\{[^}]*\|\s*safe\b")


class CabinetNoRawSafeScriptBodyTest(SimpleTestCase):
    def test_no_safe_filter_inside_script_bodies(self):
        offenders = []
        for path in _section_templates():
            text = _strip_template_comments(path.read_text(encoding="utf-8", errors="replace"))
            for match in _RAW_SAFE_SCRIPT.finditer(text):
                offenders.append(f"{path.relative_to(SECTIONS_DIR)}:{_line_of(text, match.start())}")
        self.assertEqual(
            offenders,
            [],
            "`<script>` gövdəsinə `|safe` ilə xam JSON yazılmır — "
            '`{{ obj|json_script:"id" }}` işlədin: ' + ", ".join(offenders),
        )
