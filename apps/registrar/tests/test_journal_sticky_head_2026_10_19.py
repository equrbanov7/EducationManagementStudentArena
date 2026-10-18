"""Jurnal başlıq sətri yapışqandır — daxili şaquli scroll OLMADAN (2026-10-19).

Sahib qərarı (2026-09-06): «jurnalın içində scroll olmasın» — `.jd2-grid-wrap`-ə `max-height`
verilmir. Başlıq `journal_sticky_head.js` + `thead th { translate }` ilə səhifə sürüşdükcə
ekranın yuxarısında qalır. Bu test qərarı və yükləmə müqaviləsini qoruyur.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

_CSS = Path(settings.BASE_DIR) / "apps/registrar/static/registrar/css"
_PAGE = Path(settings.BASE_DIR) / "apps/registrar/templates/registrar/journal_detail.html"


def _rules(text):
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", body)


class JournalStickyHeadContractTest(SimpleTestCase):
    def test_grid_box_never_gets_an_inner_vertical_scroll(self):
        for path in _CSS.glob("*.css"):
            for selector, block in _rules(path.read_text("utf-8")):
                if "grid-wrap" not in selector:
                    continue
                with self.subTest(file=path.name, selector=selector.strip()):
                    self.assertNotRegex(block, r"max-height|overflow-y:\s*(auto|scroll)")

    def test_page_loads_the_head_follower_and_its_css(self):
        page = _PAGE.read_text("utf-8")
        self.assertIn("registrar/js/journal_sticky_head.js", page)
        self.assertTrue(finders.find("registrar/js/journal_sticky_head.js"))
        layout = (_CSS / "journal_layout.css").read_text("utf-8")
        self.assertIn("translate: 0 var(--jd-head-y, 0px)", layout)

    def test_follower_only_writes_a_custom_property(self):
        """Klon yox, `max-height` yox — yalnız `thead`-ə `--jd-head-y` (CSSOM, CSP-dostu)."""
        js = finders.find("registrar/js/journal_sticky_head.js")
        source = Path(js).read_text("utf-8")
        self.assertIn('setProperty("--jd-head-y"', source)
        self.assertNotIn("cloneNode", source)
        self.assertNotIn("maxHeight", source)
        self.assertNotIn("innerHTML", source)
