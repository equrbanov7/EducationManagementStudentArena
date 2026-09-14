"""Filtr paneli panelin VƏZİYYƏT parametrlərini (aktiv tab) silməməlidir.

Sahib şikayəti (2026-09-10): «Registrar (kataloq)» → «Tələbə təyinatları»
tabında ad-soyad yazanda qısa loading gedir və ekran BİRİNCİ taba
(«İxtisaslar») atır.

ƏSL SƏBƏB: ``static/js/ems_ui/filter_bar.js`` URL-i yenidən qurarkən
prefiksli (``rc_``) BÜTÜN parametrləri «köhnəlmiş süzgəc» sayıb silirdi.
Aktiv tab da ``rc_tab``-dır — yəni axtarış sorğusu tabı URL-dən atırdı və
server defolt tabı (``programs``) qaytarırdı. Eyni tələ ``wc_view`` /
``wc_tab`` / ``th_tab`` / ``sr_sort`` açarlarında da vardı.

Test JS-i NODE-da işlədir (kiçik DOM stub-ı ilə) — davranış qapısı statik
mətn axtarışı deyil, funksiyanın ÖZ nəticəsidir. Node yoxdursa test atlanır.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

FILTER_BAR = Path(settings.BASE_DIR) / "static" / "js" / "ems_ui" / "filter_bar.js"

# Formanın ÖZ sahələri + panelin vəziyyət parametrləri eyni prefiksdədir;
# harness hər ikisini verib nəticəni JSON kimi qaytarır.
HARNESS = r"""
const fs = require("fs");
const vm = require("vm");

const spec = JSON.parse(process.argv[3]);

function stubHost() {
    return { querySelectorAll: () => [], querySelector: () => null };
}

function stubForm() {
    const nodes = spec.fields.map((name) => ({
        name: name,
        type: "search",
        value: spec.draft[name] || "",
        dataset: {},
        hasAttribute: () => false,
        getAttribute: () => null,
    }));
    const form = {
        id: "filters",
        dataset: { section: spec.section, paramPrefix: spec.prefix, baseUrl: spec.baseUrl },
        parentElement: stubHost(),
        classList: { toggle: () => {}, add: () => {}, remove: () => {} },
        closest: () => null,
        contains: () => false,
        querySelector: () => null,
        querySelectorAll: (sel) => (sel === "[data-ems-filter]" ? nodes : []),
        getAttribute: (name) => (name === "data-ems-filters-auto" ? (spec.auto ? "1" : null) : null),
    };
    return form;
}

const handlers = {};
const loaded = [];
const sandbox = { console, setTimeout, clearTimeout, URL, URLSearchParams };
sandbox.window = {
    location: { origin: "https://ems.test", pathname: spec.path, search: spec.search },
    EMSDelegate: { on: (evt, sel, fn) => { handlers[evt + "|" + sel] = fn; } },
    EMSReady: () => {},
    EMSProfileLoadSection: (section, url) => loaded.push(url),
    setTimeout,
    clearTimeout,
};
sandbox.document = {
    addEventListener: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    contains: () => true,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);

const form = stubForm();
const out = { built: sandbox.window.EMSFilterBar.buildUrl(form) };

if (spec.reset) {
    const reset = handlers["click|[data-ems-filters-reset]"];
    reset({ preventDefault: () => {} }, { closest: () => form });
    out.reset = loaded[loaded.length - 1];
}
process.stdout.write(JSON.stringify(out));
"""


def _query(url: str) -> dict:
    from urllib.parse import parse_qs, urlsplit

    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


class FilterBarKeepsPanelStateTest(SimpleTestCase):
    maxDiff = None

    def _run(self, **spec):
        node = shutil.which("node")
        if not node:  # pragma: no cover — CI-də node olmaya bilər
            self.skipTest("node tapılmadı")
        spec.setdefault("auto", True)
        spec.setdefault("reset", False)
        spec.setdefault("path", "/accounts/profile/")
        spec.setdefault("baseUrl", "/accounts/profile/")
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / "harness.js"
            harness.write_text(HARNESS, encoding="utf-8")
            result = subprocess.run(
                [node, str(harness), str(FILTER_BAR), json.dumps(spec)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout)

    def _catalog(self, **overrides):
        spec = {
            "section": "registrar-catalog",
            "prefix": "rc_",
            "fields": ["rc_q", "rc_status", "rc_program"],
            "draft": {"rc_q": "Aysel"},
            "search": "?section=registrar-catalog&rc_tab=students",
        }
        spec.update(overrides)
        return self._run(**spec)

    def test_search_keeps_the_active_tab(self):
        """Sahib şikayətinin birbaşa qapısı: `rc_tab` sorğudan DÜŞMÜR."""
        params = _query(self._catalog()["built"])
        self.assertEqual(params.get("rc_tab"), "students", msg="axtarış istifadəçini birinci taba atır")
        self.assertEqual(params.get("rc_q"), "Aysel")
        self.assertEqual(params.get("section"), "registrar-catalog")

    def test_reset_keeps_the_active_tab_and_drops_only_the_filters(self):
        out = self._catalog(reset=True, search="?section=registrar-catalog&rc_tab=students&rc_q=Aysel")
        params = _query(out["reset"])
        self.assertEqual(params.get("rc_tab"), "students")
        self.assertNotIn("rc_q", params)

    def test_the_forms_own_field_is_still_cleared_when_emptied(self):
        """Vəziyyət parametrini qorumaq süzgəcin təmizlənməsini POZMUR."""
        params = _query(
            self._catalog(draft={}, search="?section=registrar-catalog&rc_tab=students&rc_q=Aysel")["built"]
        )
        self.assertNotIn("rc_q", params)
        self.assertEqual(params.get("rc_tab"), "students")

    def test_paging_still_resets_on_a_filter_change(self):
        params = _query(self._catalog(search="?section=registrar-catalog&rc_tab=students&rc_page=4&page=4")["built"])
        self.assertNotIn("rc_page", params)
        self.assertNotIn("page", params)
        self.assertEqual(params.get("rc_tab"), "students")

    def test_other_panels_keep_their_view_state_too(self):
        """`wc_view` / `wc_tab` eyni tələyə düşürdü — onlar da qorunur."""
        params = _query(
            self._run(
                section="workload-center",
                prefix="wc_",
                fields=["wc_q", "wc_year"],
                draft={"wc_q": "Məmmədov"},
                search="?section=workload-center&wc_view=tasks&wc_tab=tracking&wc_q=köhnə",
            )["built"]
        )
        self.assertEqual(params.get("wc_view"), "tasks")
        self.assertEqual(params.get("wc_tab"), "tracking")
        self.assertEqual(params.get("wc_q"), "Məmmədov")
