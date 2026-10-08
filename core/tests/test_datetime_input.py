"""core.datetime_input — gün əvvəl, 24 saat tarix-saat sahəsi (müəllim rəyi E1, 2026-10-08).

Bug: imtahan sehrbazının native ``datetime-local`` sahəsi brauzer dilinə tabe idi
(en-US: mm/dd/yyyy + AM/PM; «06/10» iyun 10 oxunurdu; yazılan dəyər boş gedirdi).
Burada server tərəfi (parse + sahə + vidjet) və ``static/js/ems_datetime.js`` ilə
PARİTET yoxlanır: brauzer qəbul etdiyini server də eyni cür oxumalıdır.
"""

import datetime
import json
import shutil
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

from django import forms
from django.test import SimpleTestCase, override_settings
from django.utils import translation

from core.datetime_input import (
    DateTimeTextError,
    DayFirstDateTimeField,
    DayFirstDateTimeInput,
    parse_datetime_text,
)

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static" / "js" / "ems_datetime.js"
BAKU = ZoneInfo("Asia/Baku")

CASES = [
    "06.10.2026 09:30",
    "6.10.2026 9:30",
    "06/10/2026 09:30",
    "06-10-26 21.05",
    "06.10.2026T09:30",
    "06.10.2026, 09:30",
    "2026-10-06T09:30",
    "2026-10-06 09:30:15",
    "2026-10-06",
    "06.10.2026",
    "31.02.2026 09:00",
    "06.13.2026 09:00",
    "29.02.2028 23:59",
    "29.02.2027 10:00",
    "06.10.2026 24:00",
    "06.10.2026 09:60",
    "06.10.2026 9:30 PM",
    "10/06/2026 9:30 AM",
    "abc",
    "",
    "  06.10.2026 09:30  ",
]

HARNESS = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
globalThis.window = globalThis;
globalThis.document = { addEventListener() {} };
eval(fs.readFileSync(input.jsPath, "utf8"));
const out = input.cases.map((c) => {
  const r = globalThis.EMSDateTime.parse(c);
  return r.ok ? { ok: true, text: globalThis.EMSDateTime.format(r.parts) } : { ok: false, code: r.code };
});
process.stdout.write(JSON.stringify(out));
"""


def _python_result(text):
    try:
        value = parse_datetime_text(text)
    except DateTimeTextError as exc:
        return {"ok": False, "code": exc.code}
    if value is None:
        return {"ok": False, "code": "empty"}
    return {"ok": True, "text": value.strftime("%d.%m.%Y %H:%M")}


class ParseDateTimeTextTests(SimpleTestCase):
    def test_day_first_is_never_month_first(self):
        # «06/10» = 6 OKTYABR (en-US brauzerdə iyun 10 oxunurdu).
        self.assertEqual(parse_datetime_text("06/10/2026 09:30"), datetime.datetime(2026, 10, 6, 9, 30))
        self.assertEqual(parse_datetime_text("06.10.26 9.05"), datetime.datetime(2026, 10, 6, 9, 5))

    def test_iso_still_accepted(self):
        self.assertEqual(parse_datetime_text("2026-10-06T09:30"), datetime.datetime(2026, 10, 6, 9, 30))
        aware = parse_datetime_text("2026-10-06T05:30:00+00:00")
        self.assertEqual(aware.astimezone(BAKU).hour, 9)

    def test_error_codes(self):
        for text, code in (
            ("abc", "invalid"),
            ("06.10.2026 9:30 PM", "invalid"),
            ("31.02.2026 09:00", "invalid_date"),
            ("06.10.2026 24:00", "invalid_time"),
            ("06.10.2026", "missing_time"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(DateTimeTextError) as ctx:
                    parse_datetime_text(text)
                self.assertEqual(ctx.exception.code, code)
        self.assertIsNone(parse_datetime_text("   "))
        self.assertEqual(parse_datetime_text("06.10.2026", require_time=False), datetime.datetime(2026, 10, 6))

    def test_js_parity(self):
        node = shutil.which("node")
        if not node:  # pragma: no cover — CI-də node olmaya bilər
            self.skipTest("node tapılmadı")
        payload = json.dumps({"jsPath": str(JS), "cases": CASES})
        proc = subprocess.run([node, "-e", HARNESS], input=payload, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for text, js in zip(CASES, json.loads(proc.stdout)):
            with self.subTest(text=text):
                self.assertEqual(js, _python_result(text))


class _Form(forms.Form):
    when = DayFirstDateTimeField()


@override_settings(USE_TZ=True, TIME_ZONE="Asia/Baku")
class DayFirstFieldTests(SimpleTestCase):
    def test_naive_text_becomes_baku_aware(self):
        form = _Form(data={"when": "06.10.2026 09:30"})
        self.assertTrue(form.is_valid(), form.errors)
        value = form.cleaned_data["when"]
        self.assertEqual(value.utcoffset(), datetime.timedelta(hours=4))
        self.assertEqual(value.astimezone(BAKU).replace(tzinfo=None), datetime.datetime(2026, 10, 6, 9, 30))

    def test_clear_error_messages(self):
        with translation.override("az"):
            form = _Form(data={"when": "06.10.2026"})
            self.assertFalse(form.is_valid())
            self.assertIn("ss:dd", form.errors["when"][0])
            form = _Form(data={"when": "10/06/2026 9:30 AM"})
            self.assertFalse(form.is_valid())
            self.assertIn("gg.aa.iiii", form.errors["when"][0])

    def test_widget_renders_text_input_day_first(self):
        value = datetime.datetime(2026, 10, 6, 5, 30, tzinfo=datetime.timezone.utc)
        form = _Form(initial={"when": value})
        html = str(form["when"])
        self.assertIn('type="text"', html)
        self.assertNotIn("datetime-local", html)
        self.assertIn('value="06.10.2026 09:30"', html)  # 05:30 UTC = 09:30 Bakı
        self.assertIn("data-ems-dt-input", html)
        self.assertIn("data-ems-dt-toggle", html)
        self.assertIn('aria-describedby="id_when_hint"', html)
        self.assertIn('id="id_when_hint"', html)
        self.assertNotIn("<script", html)
        self.assertNotIn("style=", html)

    def test_widget_i18n_payload_is_valid_json(self):
        widget = DayFirstDateTimeInput()
        html = widget.render("x", None, attrs={"id": "id_x"})
        start = html.index('data-ems-dt-i18n="') + len('data-ems-dt-i18n="')
        raw = html[start : html.index('"', start)]
        import html as html_mod

        payload = json.loads(html_mod.unescape(raw))
        self.assertEqual(len(payload["months"]), 12)
        self.assertEqual(len(payload["weekdays"]), 7)
        self.assertEqual(set(payload["errors"]), {"invalid", "invalid_date", "invalid_time", "missing_time"})
