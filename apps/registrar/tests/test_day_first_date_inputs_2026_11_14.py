"""Jurnal tarix sahələri «gg.aa.iiii» (sahib 2026-11-14: «bizdə Azərbaycanda standart tarix gün ay il olaraqdır»).

Bug: «Yeni dərs» modalının native ``<input type="date">`` sahəsi brauzer dilinə tabe idi (en-US → mm/dd/yyyy) —
müəllim keçmiş tarixə dərs açanda günü ay yerinə yazırdı. İndi görünən sahə HƏMİŞƏ «gg.aa.iiii» (EMSDateTime date
rejimi), forma dəyəri isə gizli ISO sahəsindədir (server parseri və köhnə JS-lər dəyişmir).

Nəyi qoruyur
------------
* vidcet: görünən «gg.aa.iiii», gizli ``name`` = ISO, ``data-ems-dt-min/max`` ISO, qarmaq atributları yalnız ``data-*``;
* JS (node): yalnız-tarix formatı/ISO, aralıq kodları və mesajda aralıq «gg.aa.iiii» ilə;
* jurnal səhifəsi: modal native date vermir, min/max yazma pəncərəsinin özüdür, ipucu aralığı «gg.aa.iiii» deyir;
  gizli sahənin ISO dəyəri POST-da qəbul olunur (bu gün və pəncərə daxilində keçmiş tarix).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.registrar import journal_edit_windows
from apps.registrar.models import Lesson
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.date_input import as_date, date_picker_i18n, render_day_first_date_input
from core.rls import bypass_rls

ROOT = Path(__file__).resolve().parents[3]
JS = ROOT / "static" / "js" / "ems_datetime.js"
TIME = "08:30|10:00"

HARNESS = r"""
const fs = require("fs");
globalThis.window = globalThis;
globalThis.document = { addEventListener() {} };
eval(fs.readFileSync(process.argv[1], "utf8"));
const api = globalThis.EMSDateTime;
function field(value, attrs) {
  const wrapper = { getAttribute: (name) => (name in attrs ? attrs[name] : null) };
  return { value: value, closest: () => wrapper };
}
const range = { "data-ems-dt-mode": "date", "data-ems-dt-min": "2026-11-07", "data-ems-dt-max": "2026-11-14" };
const onlyMax = { "data-ems-dt-mode": "date", "data-ems-dt-max": "2026-11-14" };
const free = { "data-ems-dt-mode": "date" };
const pick = (r) => ({ ok: r.ok, empty: r.empty, code: r.code || "", message: r.message || "" });
const out = {
  formatDate: api.formatDate({ year: 2026, month: 3, day: 5 }),
  toIso: api.toIso({ year: 2026, month: 3, day: 5 }),
  isoBad: api.isoParts("05.03.2026"),
  inRange: pick(api.validate(field("10.11.2026", range))),
  dayFirst: pick(api.validate(field("7/11/2026", range))),
  tooOld: pick(api.validate(field("01.11.2026", range))),
  future: pick(api.validate(field("15.11.2026", onlyMax))),
  monthFirst: pick(api.validate(field("11/30/2026", free))),
  garbage: pick(api.validate(field("abc", free))),
  empty: pick(api.validate(field("", free))),
};
process.stdout.write(JSON.stringify(out));
"""


class WidgetTest(SimpleTestCase):
    def test_visible_day_first_hidden_iso_and_range(self):
        html = str(
            render_day_first_date_input(
                "lesson_date",
                date(2026, 11, 14),
                input_id="jd-lesson-date",
                required=True,
                min_value=date(2026, 11, 7),
                max_value="2026-11-14",
                iso_attrs='data-jd-lesson-date onclick="x()" data-x"y',
            )
        )
        self.assertNotIn('type="date"', html)
        self.assertIn('data-ems-dt-mode="date"', html)
        self.assertIn('data-ems-dt-min="2026-11-07"', html)
        self.assertIn('data-ems-dt-max="2026-11-14"', html)
        visible = re.search(r'<input type="text" id="jd-lesson-date"[^>]*>', html).group(0)
        self.assertIn('value="14.11.2026"', visible)
        self.assertIn(" required", visible)
        self.assertNotIn("name=", visible)
        hidden = re.search(r'<input type="text" name="lesson_date"[^>]*>', html).group(0)
        self.assertIn('value="2026-11-14"', hidden)
        self.assertIn(" hidden", hidden)
        self.assertIn("data-ems-dt-iso data-jd-lesson-date>", hidden)
        self.assertNotIn("onclick", html)  # qarmaqlar yalnız data-* adlarıdır
        self.assertTrue(html.startswith("<span ") and html.endswith("</span>"))  # <label> içində də düzgün

    def test_no_range_and_empty_value(self):
        html = str(render_day_first_date_input("doc_date", None, input_id="d"))
        self.assertNotIn("data-ems-dt-min", html)
        self.assertNotIn("data-ems-dt-max", html)
        self.assertIn('name="doc_date" value=""', html)
        self.assertNotIn(" required", html)

    def test_i18n_payload_is_date_only(self):
        data = date_picker_i18n()
        self.assertNotIn("hour", data)
        self.assertIn("{min}", data["errors"]["out_of_range"])
        self.assertIn("{max}", data["errors"]["out_of_range"])
        self.assertIn("gg.aa.iiii", data["errors"]["invalid"])
        html = str(render_day_first_date_input("d", None, input_id="d"))
        payload = re.search(r'data-ems-dt-i18n="([^"]*)"', html).group(1).replace("&quot;", '"')
        self.assertEqual(json.loads(payload)["errors"]["before_min"], data["errors"]["before_min"])

    def test_as_date(self):
        self.assertEqual(as_date("2026-11-07"), date(2026, 11, 7))
        self.assertEqual(as_date("07.11.2026"), date(2026, 11, 7))
        self.assertIsNone(as_date("11/30/2026"))
        self.assertIsNone(as_date(""))


class JsDateModeTest(SimpleTestCase):
    def test_js_date_mode(self):
        node = shutil.which("node")
        if not node:  # pragma: no cover — CI-də node olmaya bilər
            self.skipTest("node tapılmadı")
        proc = subprocess.run([node, "-e", HARNESS, str(JS)], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["formatDate"], "05.03.2026")
        self.assertEqual(out["toIso"], "2026-03-05")
        self.assertIsNone(out["isoBad"])
        self.assertTrue(out["inRange"]["ok"])
        self.assertTrue(out["dayFirst"]["ok"])  # 7/11 = 7 noyabr, iyul yox
        self.assertEqual(out["tooOld"]["code"], "out_of_range")
        self.assertIn("07.11.2026", out["tooOld"]["message"])
        self.assertIn("14.11.2026", out["tooOld"]["message"])
        self.assertEqual(out["future"]["code"], "after_max")
        self.assertIn("14.11.2026", out["future"]["message"])
        self.assertEqual(out["monthFirst"]["code"], "invalid_date")  # 30-cu ay yoxdur
        self.assertEqual(out["garbage"]["code"], "invalid")
        self.assertIn("gg.aa.iiii", out["garbage"]["message"])
        self.assertTrue(out["empty"]["empty"])


class JournalLessonDateTest(TestCase):
    prefix = "jdfd"

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, cls.prefix)

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _detail(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])

    def _modal(self, html):
        start = html.index("data-jd-lesson-modal")
        return html[start : html.index("</form>", start)]

    def test_modal_renders_day_first_field_with_window(self):
        today = timezone.localdate()
        ctx = journal_edit_windows.template_context(today)
        low = ctx["lesson_date_min"]
        response = self._client().get(self._detail())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        modal = self._modal(html)
        self.assertNotIn('type="date"', modal)
        self.assertIn(f'data-ems-dt-min="{low.isoformat()}"', modal)
        self.assertIn(f'data-ems-dt-max="{today.isoformat()}"', modal)
        self.assertIn(f'value="{today.strftime("%d.%m.%Y")}"', modal)
        hidden = re.search(r'<input type="text" name="lesson_date"[^>]*>', modal).group(0)
        self.assertIn(f'value="{today.isoformat()}"', hidden)
        self.assertIn("data-jd-lesson-date", hidden)
        # İpucu aralığı «gg.aa.iiii» ilə deyir (defolt: 7 gün geriyə, keçmiş tarix başlanğıcı söndürülü).
        self.assertIn(low.strftime("%d.%m.%Y"), modal)
        self.assertIn('id="jd-lesson-date-hint"', modal)
        self.assertIn("js/ems_datetime.js", html)
        self.assertIn("js/ems_datetime_picker.js", html)
        self.assertIn("css/ems_datetime.css", html)

    def test_server_accepts_hidden_iso_value(self):
        client = self._client()
        today = timezone.localdate()
        html = self._modal(client.get(self._detail()).content.decode())
        posted = re.search(r'name="lesson_date" value="([^"]*)"', html).group(1)
        for day in (posted, (today - timedelta(days=3)).isoformat()):
            client.post(
                self._detail(),
                {"action": "add_lesson", "lesson_date": day, "lesson_kind": "lecture", "lesson_time": TIME},
            )
            with bypass_rls():
                self.assertTrue(
                    Lesson.objects.filter(offering=self.offering, date=date.fromisoformat(day)).exists(), day
                )
