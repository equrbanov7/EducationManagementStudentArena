"""W3 2026-09-14 — KaTeX vendor aktivləri, CSP uyğunluğu və `ems_math.js` başlatıcısı.

KaTeX `static/vendor/katex/0.16.47/`-də pin-lənib (README-də SHA256-lar).
Bu qapı: fayllar yerindədir və dəyişməyib; include partial-ı yalnız same-origin
`<link>`/`<script defer src>` istifadə edir (CSP: `unsafe-inline` yoxdur);
başlatıcı yalnız `[data-ems-math]` içində, `trust:false`/`throwOnError:false`
ilə işləyir və AJAX ilə gələn konteynerləri də render edir (node harness).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import unittest

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

ROOT = pathlib.Path(settings.BASE_DIR)
KATEX_DIR = ROOT / "static" / "vendor" / "katex" / "0.16.47"
EMS_MATH = ROOT / "static" / "js" / "ems_math.js"
PARTIAL = ROOT / "templates" / "partials" / "ems_ui" / "_math_assets.html"

# `katex.min.css` yuxarı axından fərqlənir: .woff/.ttf fallback `src` girişləri
# silinib (yalnız woff2 vendorlanır; manifest storage çatışmayan istinada görə
# collectstatic-i qırırdı — 2026-09-14). SHA bu düzəldilmiş faylındır.
PINNED_SHA256 = {
    "katex.min.js": "a29d2961d3146de5949d78ac7c1a9d93ae54955bad22a6db4fbe836e88e8bf48",
    "katex.min.css": "c9eac1c75c95f7dcbb6db0210cf0a49a150d07aaf599292e5f9ca099c596a119",
    "contrib/auto-render.min.js": "e5372d199bcdae8b4de71d0f7ceba72a4ba12774a27c60a6f1f77d03b3228ee4",
    "fonts/KaTeX_Main-Regular.woff2": "c2342cd8b869e01752a9321dc17213fc40d4d04c79688c1d43f2cf316abd7866",
    "fonts/KaTeX_Math-Italic.woff2": "7af58c5ec8f132a2ddde9027c6d7814decce4d3b822a11192a42a20e2e973264",
}

NODE_HARNESS = r"""
const fs = require("fs");
const [mathPath] = process.argv.slice(-1);
const rendered = [];
function el(attrs, text) {
  const node = {
    nodeType: 1, attrs: Object.assign({}, attrs), textContent: text || "", children: [],
    hasAttribute(n) { return n in this.attrs; },
    getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; },
    setAttribute(n, v) { this.attrs[n] = String(v); },
    querySelectorAll(sel) {
      const out = [];
      const walk = (x) => { x.children.forEach((c) => { if (c.hasAttribute("data-ems-math") && !c.hasAttribute("data-ems-math-done")) out.push(c); walk(c); }); };
      walk(this);
      return out;
    },
  };
  return node;
}
const first = el({ "data-ems-math": "" }, "Hesabla \\(\\frac{a}{b}\\)");
const plain = el({ "data-ems-math": "" }, "düstursuz mətn");
const money = el({ "data-ems-math": "" }, "Qiymət $5 və $10 arasındadır");
const body = el({}, "");
body.children.push(first, plain, money);
global.window = global;
global.document = { readyState: "complete", body, children: [body], nodeType: 9,
  querySelectorAll: body.querySelectorAll.bind(body), addEventListener() {} };
global.MutationObserver = function (cb) { this.observe = () => { global.__mo = cb; }; };
global.requestAnimationFrame = (fn) => fn();
global.renderMathInElement = function (node, options) { rendered.push([node.textContent, options.trust, options.throwOnError, options.strict, options.delimiters.map((d) => d.left).join(" ")]); };
new Function(fs.readFileSync(mathPath, "utf8"))();
// AJAX ilə gələn yeni konteyner → MutationObserver → yenidən render
const late = el({ "data-ems-math": "" }, "Sonradan $x^2$");
body.children.push(late);
global.__mo([{ addedNodes: [late] }]);
// İkinci keçid: artıq render olunanlar təkrar render olunmur
window.EMSMath.render(document);
process.stdout.write(JSON.stringify({ rendered, firstDone: first.getAttribute("data-ems-math-done"), plainDone: plain.getAttribute("data-ems-math-done") }));
"""


class KatexVendorAssetTests(SimpleTestCase):
    def test_pinned_files_are_present_and_unchanged(self):
        for relative, digest in PINNED_SHA256.items():
            path = KATEX_DIR / relative
            self.assertTrue(path.is_file(), f"{relative} yoxdur")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, f"{relative} dəyişib")
        self.assertTrue((KATEX_DIR / "LICENSE").is_file())
        self.assertTrue((KATEX_DIR.parent / "README.md").is_file())
        self.assertIn('version:"0.16.47"', (KATEX_DIR / "katex.min.js").read_text(encoding="utf-8")[:400000])

    def test_css_fonts_are_same_origin_woff2_files_that_exist(self):
        css = (KATEX_DIR / "katex.min.css").read_text(encoding="utf-8")
        urls = set(re.findall(r"url\(([^)]+\.woff2)\)", css))
        self.assertTrue(urls)
        for url in urls:
            self.assertFalse(url.startswith(("http", "//", "data:")), url)
            self.assertTrue((KATEX_DIR / url).is_file(), url)

    def test_include_partial_uses_only_same_origin_deferred_assets(self):
        html = render_to_string(PARTIAL.relative_to(ROOT / "templates").as_posix())
        self.assertNotIn("<script>", html)
        self.assertNotRegex(html, r"<script\b(?![^>]*\bsrc=)[^>]*>\s*\S", "inline script qadağandır (CSP)")
        scripts = re.findall(r"<script\b[^>]*>", html)
        self.assertEqual(len(scripts), 3)
        for tag in scripts:
            self.assertIn("defer", tag)
            self.assertIn(settings.STATIC_URL, tag)
            self.assertNotIn("http", tag.split("src=")[1][:8])
        self.assertIn("vendor/katex/0.16.47/katex.min.css", html)
        self.assertIn("js/ems_math.js", html)

    def test_csp_allows_vendored_assets_without_cdn(self):
        directives = settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]
        for name in ("script-src", "style-src", "font-src"):
            self.assertIn("'self'", directives[name], name)
            self.assertFalse(any("katex" in str(src) or "cdn" in str(src) for src in directives[name]), name)
        # KaTeX HTML çıxışı inline `style=""` atributları yazır — bu direktiv
        # silinərsə `ems_math.js`-də `output:"mathml"` rejiminə keçmək lazımdır.
        self.assertIn("'unsafe-inline'", directives["style-src-attr"])

    def test_initialiser_is_ajax_safe_and_hardened(self):
        source = EMS_MATH.read_text(encoding="utf-8")
        self.assertIn("trust: false", source)
        self.assertIn("throwOnError: false", source)
        self.assertIn('strict: "ignore"', source)
        self.assertIn("[data-ems-math]", source)
        self.assertIn("MutationObserver", source)
        self.assertIn("window.EMSReady", source)
        self.assertNotIn("EMSDelegate.on(", source)
        self.assertNotIn("innerHTML", source)


@unittest.skipUnless(shutil.which("node"), "node yoxdur — brauzer JS harness testi ötürülür")
class EmsMathNodeHarnessTests(unittest.TestCase):
    def test_renders_only_math_containers_once_and_after_dom_insertions(self):
        proc = subprocess.run(
            ["node", "-e", NODE_HARNESS, str(EMS_MATH)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        texts = [entry[0] for entry in result["rendered"]]
        self.assertEqual(texts, ["Hesabla \\(\\frac{a}{b}\\)", "Qiymət $5 və $10 arasındadır", "Sonradan $x^2$"])
        delimiters = {entry[0]: entry[4] for entry in result["rendered"]}
        # Valyuta konteynerində tək-`$` ayırıcısı söndürülür; düstur konteynerində qalır.
        self.assertEqual(delimiters["Qiymət $5 və $10 arasındadır"], "$$ \\[ \\(")
        self.assertEqual(delimiters["Sonradan $x^2$"], "$$ \\[ \\( $")
        for _text, trust, throw, strict, _delims in result["rendered"]:
            self.assertFalse(trust)
            self.assertFalse(throw)
            self.assertEqual(strict, "ignore")
        self.assertEqual(result["firstDone"], "1")
        self.assertEqual(result["plainDone"], "1")
