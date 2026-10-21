"""`data-tof-*` dialoqlarını işlədən hər kabinet bölməsi `teaching_office.js`-i yükləməlidir (2026-10-21).

Bölmə-xas asset-lərə keçiddən (2026-10-19) sonra «İmtahan zalları»nda «Kompüter əlavə et» / «Toplu əlavə»
düymələri ölmüşdü: `data-tof-open` mexanizmi `teaching_office.js`-dədir, o isə yalnız tədris şöbəsi
bölmələrində yüklənirdi. Bu test bölmə şablonunu (statik `{% include %}`-ləri ilə birlikdə) gəzir.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.accounts.views.profile.section_assets import JS_PHASES, section_js
from apps.accounts.views.profile.sections_api import SECTION_PARTIALS

_INCLUDE = re.compile(r"""{%\s*include\s+["']([^"']+)["']""")
_TOF = re.compile(r"data-tof-(?:open|form|root)\b")
_TOF_JS = "accounts/js/profile/teaching_office.js"
_COMMENT = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)


def _uses_tof(template_name: str, seen: set[str]) -> bool:
    if template_name in seen:
        return False
    seen.add(template_name)
    try:
        source = _COMMENT.sub("", Path(get_template(template_name).origin.name).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — dinamik/mövcud olmayan include
        return False
    if _TOF.search(source):
        return True
    return any(_uses_tof(name, seen) for name in _INCLUDE.findall(source))


class TofAssetCoverageTest(SimpleTestCase):
    def test_every_tof_section_loads_teaching_office_js(self):
        missing = []
        for key, template_name in SECTION_PARTIALS.items():
            if not _uses_tof(template_name, set()):
                continue
            scripts = [src for phase in JS_PHASES for src in section_js(frozenset({key}), {key}, phase)]
            if not any(_TOF_JS in src for src in scripts):
                missing.append(key)
        self.assertEqual(missing, [], f"teaching_office.js yüklənmir: {missing}")

    def test_exam_rooms_section_is_covered(self):
        scripts = [
            src
            for phase in JS_PHASES
            for src in section_js(frozenset({"superadmin-exam-rooms"}), {"superadmin-exam-rooms"}, phase)
        ]
        self.assertTrue(any(_TOF_JS in src for src in scripts))
        self.assertTrue(Path(settings.BASE_DIR, "apps/accounts/static", _TOF_JS).exists())
