"""``static/js/search_fold.js`` (EMSSearch) ↔ ``core.search_text`` PARİTETİ (2026-09-26).

Klient süzgəcləri (kabinet menyusu, seçim komponentinin axtarışı, ⌘K vurğusu…)
server ilə EYNİ qaydanı işlətməlidir: eyni sorğu brauzerdə bir şey, serverdə
başqa şey tapmasın. Test göndərilən JS faylını node-da OLDUĞU KİMİ icra edir və
hər hal üçün nəticəni Python ``tolerant_match`` ilə tutuşdurur.
"""

import json
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

from core.search_text import fold_regex, tolerant_match

ROOT = Path(__file__).resolve().parents[2]
SEARCH_FOLD_JS = ROOT / "static" / "js" / "search_fold.js"

HARNESS = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
globalThis.window = globalThis;
eval(fs.readFileSync(input.jsPath, "utf8"));
const S = globalThis.EMSSearch;
const out = input.cases.map(([q, t, compact]) => ({
  match: S.matches(q, t, { compact }),
  pattern: S.pattern(q, { compact }),
}));
out.push({ fold: S.fold("İSMAYIL Şəhriyar Çağlar Öztürk ı") });
out.push({ tokens: S.tokens("  a  b c d e f ") });
process.stdout.write(JSON.stringify(out));
"""

CASES = [
    ("234k", "234 K ing", True),
    ("234king", "234 K ing", True),
    ("234 king", "234 K ing", True),
    ("234-K-ing", "234 K ing", True),
    ("234k ing", "234 K ing", True),
    ("234k1", "234 K-1", True),
    ("234king", "234 K ing", False),
    ("235k", "234 K ing", True),
    ("Aliyev", "Əliyev", False),
    ("Eliyev", "Əliyev", False),
    ("Aliyev", "Eliyev", False),
    ("Əliyev", "Aliyev", False),
    ("Sahzad", "Şahzad", False),
    ("Shahzad", "Şahzad", False),
    ("Şahzad", "Shahzad", False),
    ("Verilenler", "Verilənlər bazası", False),
    ("Chingiz", "Çingiz", False),
    ("Aghayev", "Ağayev", False),
    ("Khalilov", "Xəlilov", False),
    ("Xəlilov", "Khalilov", False),
    ("ISMAYIL", "İsmayıl", False),
    ("ismayil", "İSMAYIL", False),
    ("Ozturk", "Öztürk", True),
    ("aydan alyarova", "Alyarova Aydan", False),
    ("a.b", "axb", False),
    ("a|b", "a|b", False),
    ("(x", "(x)", True),
    ("", "hər şey", False),
    ("PA", "Qrup A1-1", True),
    ("vb1", "V B-1", True),
    ("sekidu", "seki-du", True),
    ("234 kin g", "234 K ing", True),
    ("234 kin g", "234 K ing", False),
    ("ismayil", "İsmayıl".lower(), False),
    ("ismayil", "İsmayıl".lower(), True),
]


class SearchFoldJsParityTest(SimpleTestCase):
    def test_js_matches_python(self):
        node = shutil.which("node")
        if not node:  # pragma: no cover — CI-də node olmaya bilər
            self.skipTest("node tapılmadı")
        payload = json.dumps({"jsPath": str(SEARCH_FOLD_JS), "cases": CASES})
        proc = subprocess.run([node, "-e", HARNESS], input=payload, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        results = json.loads(proc.stdout)
        for (query, text, compact), js in zip(CASES, results):
            with self.subTest(query=query, text=text, compact=compact):
                self.assertIs(js["match"], tolerant_match(query, text, compact=compact))
                if query and " " not in query:
                    # Tək token üçün şablon mətni də eynidir (qaçırma üslubu fərqli ola bilər → yalnız hərflər).
                    if query.isalnum() or compact:
                        self.assertEqual(js["pattern"], fold_regex(query, compact=compact).replace("\\-", "-"))
        self.assertEqual(results[-2]["fold"], "ismayil sehriyar caglar ozturk i")
        self.assertEqual(results[-1]["tokens"], ["a", "b", "c", "d"])
