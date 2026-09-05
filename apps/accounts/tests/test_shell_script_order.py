"""Kabinet qabığında skript sırası — QA 2026-09-05 P1-1 reqressiya qapısı.

Bölmə partial-larının ``<script src>``-ləri ``{% block content %}`` içində,
``ems_ajax_init.js`` isə body-nin sonunda yüklənir. Tam səhifə render-də partial
skripti ``window.EMSReady(...)`` çağıranda funksiya hələ yox idi →
``TypeError: window.EMSReady is not a function`` (rol təyinatı, bildiriş göndərmə,
kontakt cavabı bölmələrinin JS-i ölü qalırdı).

Üç qat qorunur:
1. ``static/js/ems_early.js`` <head>-də, ``ems_ajax_init.js``-dən və content-dən ƏVVƏL gəlir;
2. ``ems_ajax_init.js`` stub-u əvəz edib növbəni boşaldır (node ilə icra olunur);
3. kabinet partial-larının hər ``<script src>``-i ``defer`` daşıyır (statik qapı).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

ROOT = pathlib.Path(settings.BASE_DIR)
PARTIAL_DIRS = (
    ROOT / "apps" / "accounts" / "templates" / "accounts" / "profile" / "sections",
    ROOT / "apps" / "accounts" / "templates" / "accounts" / "partials",
)
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc=[^>]*>", re.I)

NODE_HARNESS = r"""
const fs = require("fs");
const [earlyPath, initPath] = process.argv.slice(-2);
const listeners = {};
global.window = global;
global.document = {
  readyState: "complete",
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  contains() { return true; },
};
const calls = [];
new Function(fs.readFileSync(earlyPath, "utf8"))();
if (!window.EMSReady || !window.EMSReady.__emsStub) { throw new Error("stub yoxdur"); }
// Partial skripti kimi — əsl implementasiyadan ƏVVƏL qeydiyyat.
window.EMSReady(function () { calls.push("ready"); });
window.EMSReady.once("k", function () { calls.push("once"); });
window.EMSDelegate.on("click", ".x", function () { calls.push("on"); });
new Function(fs.readFileSync(initPath, "utf8"))();
if (window.EMSReady.__emsStub) { throw new Error("stub əvəz olunmayıb"); }
// Əsl implementasiya: ready dərhal işlədi (readyState=complete), once dərhal işlədi,
// delegate `document` listener-ə çevrildi.
const result = {
  calls,
  earlyQueueCleared: window.__emsEarlyQueue === null,
  clickListeners: (listeners["click"] || []).length,
  sectionLoadedListeners: (listeners["profile:section:loaded"] || []).length,
};
process.stdout.write(JSON.stringify(result));
"""


class ShellScriptOrderTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="script-order-user", email="script-order@example.com", password="StrongPass123!"
        )
        self.client.force_login(self.user)

    def test_ems_early_loaded_in_head_before_init_and_content(self):
        response = self.client.get("/accounts/profile/", follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        early = html.find("js/ems_early.js")
        init = html.find("js/ems_ajax_init.js")
        body = html.find("<body")
        self.assertGreater(early, 0, "ems_early.js qabıqda yoxdur")
        self.assertGreater(init, 0, "ems_ajax_init.js qabıqda yoxdur")
        self.assertLess(early, body, "ems_early.js <head>-də olmalıdır")
        self.assertLess(early, init, "ems_early.js ems_ajax_init.js-dən əvvəl gəlməlidir")

    def test_profile_partials_scripts_are_deferred(self):
        offenders = []
        for base in PARTIAL_DIRS:
            for path in base.rglob("*.html"):
                for match in _SCRIPT_SRC_RE.findall(path.read_text(encoding="utf-8")):
                    if "defer" not in match:
                        offenders.append(f"{path.relative_to(ROOT)}: {match[:90]}")
        self.assertEqual(
            offenders, [], "Partial <script src> `defer`-siz (bax test docstring):\n" + "\n".join(offenders)
        )


@unittest.skipUnless(shutil.which("node"), "node yoxdur — brauzer JS növbə testi ötürülür")
class EarlyQueueDrainTest(unittest.TestCase):
    def test_stub_calls_are_replayed_by_real_implementation(self):
        early = ROOT / "static" / "js" / "ems_early.js"
        init = ROOT / "static" / "js" / "ems_ajax_init.js"
        proc = subprocess.run(
            ["node", "-e", NODE_HARNESS, str(early), str(init)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(sorted(result["calls"]), ["once", "ready"])
        self.assertTrue(result["earlyQueueCleared"])
        self.assertEqual(result["clickListeners"], 1)
        self.assertGreaterEqual(result["sectionLoadedListeners"], 1)
