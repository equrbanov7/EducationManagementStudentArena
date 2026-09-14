"""W4 2026-09-14 (w3sweep R3) — nəzarət rejimi status endpoint-inin yükü.

Əvvəl: tələbə səhifəsi `/exams/supervision/api/status/<attempt>/`-i WS bağlı
olanda da hər 1 s sorğulayırdı (300 tələbə = 300 sorğu/s); endpoint cəhd →
imtahan → nəzarət konfiqini 3 ayrı sorğu ilə oxuyurdu; limit yox idi.

İndi: klient WS-first (15 s heartbeat / WS yoxdursa 2→10 s backoff, görünürlük
və `online` hadisələrində dərhal yoxlama, 429-da Retry-After); server tərəfi
`select_related` (3 → 1 sorğu), zəif ETag + `If-None-Match` → 304, cəhd başına
`15/10s` limiti (429 + Retry-After), `Cache-Control: no-store` qalır.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamSupervisionConfig
from apps.exams.tests.test_views import _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rate_limit import clear_rate_limit

User = get_user_model()
JS_DIR = pathlib.Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "js" / "exam_supervision"

# Sorğuların sayı middleware-dən (sessiya, istifadəçi, RLS set_config) asılıdır;
# view-un öz payı 1 sorğudur (cəhd + imtahan + konfiq tək JOIN-də).
_VIEW_OWN_QUERIES = 1


def _attempt_query_count(queries):
    return sum(1 for q in queries if "exams_examattempt" in q["sql"] or "exams_examsupervisionconfig" in q["sql"])


class SupervisionStatusEndpointCostTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w4_status_teacher", "w4_status_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("w4_status_student", "w4_status_student@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="W4 Status Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="W4 status exam",
            exam_type="test",
            is_active=True,
            total_duration_minutes=60,
        )
        ExamSupervisionConfig.objects.create(exam=self.exam, enabled=True, recovery_policy="teacher_controlled")
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        self.url = reverse("exams:supervision_status_api", args=[self.attempt.id])
        self.client.force_login(self.student)
        self.addCleanup(clear_rate_limit, "supervision_status", self.student.id, self.attempt.id)

    def test_status_is_one_query_for_attempt_exam_and_config(self):
        self.client.get(self.url)  # sessiya/profil keşləri isinsin
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_attempt_query_count(ctx.captured_queries), _VIEW_OWN_QUERIES)
        # Cəhd/imtahan/konfiq tək SELECT-də gəlir — ayrıca exams_exam sorğusu yoxdur.
        exam_only = [
            q["sql"]
            for q in ctx.captured_queries
            if 'FROM "exams_exam"' in q["sql"] and "exams_examattempt" not in q["sql"]
        ]
        self.assertEqual(exam_only, [])
        payload = response.json()
        self.assertTrue(payload["supervised"])
        self.assertEqual(payload["supervision_status"], "active")
        self.assertFalse(payload["is_finished"])

    def test_no_store_and_etag_304_when_unchanged(self):
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertIn("no-store", first["Cache-Control"])
        etag = first["ETag"]
        self.assertTrue(etag.startswith('W/"'))

        second = self.client.get(self.url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second["ETag"], etag)
        self.assertEqual(second.content, b"")

        # Vəziyyət dəyişdi → yeni ETag, tam cavab.
        self.attempt.supervision_status = "locked"
        self.attempt.supervision_manual_lock = True
        self.attempt.save(update_fields=["supervision_status", "supervision_manual_lock"])
        third = self.client.get(self.url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(third.status_code, 200)
        self.assertNotEqual(third["ETag"], etag)
        self.assertTrue(third.json()["manual_lock"])

    def test_per_attempt_rate_limit_returns_429_with_retry_after_before_touching_db(self):
        for _ in range(15):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        with CaptureQueriesContext(connection) as ctx:
            blocked = self.client.get(self.url)
        self.assertEqual(blocked.status_code, 429)
        self.assertGreaterEqual(int(blocked["Retry-After"]), 1)
        self.assertEqual(_attempt_query_count(ctx.captured_queries), 0)

    def test_rate_limit_is_keyed_per_user_and_attempt(self):
        other = User.objects.create_user("w4_status_other", "w4_status_other@example.com", "StrongPass123!")
        _assign_user_to_org(other, self.org, ProfileRole.STUDENT)
        other_attempt = ExamAttempt.objects.create(user=other, exam=self.exam, status="in_progress", attempt_number=1)
        self.addCleanup(clear_rate_limit, "supervision_status", other.id, other_attempt.id)
        for _ in range(16):
            self.client.get(self.url)
        self.assertEqual(self.client.get(self.url).status_code, 429)

        # Başqa tələbənin öz cəhdi öz büdcəsini işlədir.
        self.client.force_login(other)
        response = self.client.get(reverse("exams:supervision_status_api", args=[other_attempt.id]))
        self.assertEqual(response.status_code, 200)


NODE_HARNESS = r"""
const fs = require("fs");
const dir = process.argv[process.argv.length - 1];
function load(name) {
  const src = fs.readFileSync(dir + "/" + name, "utf8")
    .replace(/^import .*$/mg, "")
    .replace(/^export default .*$/mg, "")
    .replace(/^export var /mg, "var ")
    .replace(/^export \{.*$/mg, "");
  return src;
}
// --- saxta taymerlər: gecikmələr qeyd olunur, `flush()` növbədəkini icra edir
const timers = [];
let timerId = 0;
const delays = [];
global.setTimeout = function (fn, ms) { timerId += 1; timers.push({ id: timerId, fn, ms }); delays.push(ms); return timerId; };
global.clearTimeout = function (id) { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); };
global.setInterval = function () { return 0; };
global.clearInterval = function () {};
function flush() { const t = timers.shift(); if (t) t.fn(); }
// --- saxta DOM
const listeners = {};
global.document = {
  visibilityState: "visible",
  cookie: "",
  getElementById() { return null; },
  addEventListener(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); },
};
global.window = { addEventListener(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); }, location: {} };
global.navigator = { userAgent: "node", platform: "node", maxTouchPoints: 0 };
// --- saxta fetch: hər sorğu qeyd olunur, cavab ssenarisi `nextResponse` ilə verilir
const requests = [];
let nextResponse = { status: 200, body: { supervised: true, supervision_status: "active", is_finished: false }, etag: 'W/"a"' };
global.fetch = function (url, opts) {
  requests.push({ url, ifNoneMatch: (opts.headers || {})["If-None-Match"] || null });
  const r = nextResponse;
  return Promise.resolve({
    status: r.status, ok: r.status >= 200 && r.status < 300,
    headers: { get(n) { if (n === "ETag") return r.etag || null; if (n === "Retry-After") return r.retryAfter || null; return null; } },
    json() { return Promise.resolve(r.body); },
  });
};
const code = load("state.js") + "\n" + load("api.js") + "\n" + load("scoring.js") + "\n" + load("websocket.js") + "\n;return ExamSupervision;";
const S = new Function(code)();
S.statusEndpoint = "/status/";
S._initialized = true;
S.isActive = true;
S.destroy = function () {};
const tick = () => new Promise((res) => setImmediate(res));
(async () => {
  const out = {};
  // 1) WS bağlı deyil → başlanğıc 2 s, sonra backoff 2,4,8,10,10
  S._startBackgroundStatusWatch();
  out.initialDelay = delays[delays.length - 1];
  const wsDown = [];
  for (let i = 0; i < 5; i++) { flush(); await tick(); await tick(); await tick(); wsDown.push(delays[delays.length - 1]); }
  out.wsDownDelays = wsDown;
  out.requestsWhileDown = requests.length;
  // 2) İkinci sorğudan etibarən If-None-Match göndərilir; 304 → son yük təkrar istifadə olunur
  out.secondIfNoneMatch = requests[1].ifNoneMatch;
  nextResponse = { status: 304 };
  let got = null;
  S._checkSupervisionStatus((d) => { got = d; });
  await tick(); await tick(); await tick();
  out.dataOn304 = got && got.supervision_status;
  nextResponse = { status: 200, body: { supervised: true, supervision_status: "active", is_finished: false }, etag: 'W/"a"' };
  // 3) WS açıldı → heartbeat 15 s
  S._wsSocket = { readyState: 1 };
  S._onTransportStateChange(false);
  flush(); await tick(); await tick(); await tick();
  out.wsOpenDelay = delays[delays.length - 1];
  flush(); await tick(); await tick(); await tick();
  out.wsOpenDelay2 = delays[delays.length - 1];
  // 4) Görünən oldu → dərhal (0 ms) sorğu; gizli olanda heç nə
  const before = requests.length;
  document.visibilityState = "hidden"; listeners.visibilitychange.forEach((fn) => fn());
  out.hiddenKick = delays[delays.length - 1];
  document.visibilityState = "visible"; listeners.visibilitychange.forEach((fn) => fn());
  out.visibleKickDelay = delays[delays.length - 1];
  flush(); await tick(); await tick(); await tick();
  out.visibleRequested = requests.length - before;
  // 5) WS qırıldı → dərhal yoxlama + backoff yenidən 2 s-dən
  S._wsSocket = null;
  S._onTransportStateChange(true);
  out.wsCloseKickDelay = delays[delays.length - 1];
  flush(); await tick(); await tick(); await tick();
  out.afterWsCloseDelay = delays[delays.length - 1];
  // 6) 429 + Retry-After: 7 → növbəti gecikmə ≥ 7000
  nextResponse = { status: 429, retryAfter: "7" };
  flush(); await tick(); await tick(); await tick();
  out.after429Delay = delays[delays.length - 1];
  // 7) İkinci start ikinci zəncir açmır; destroy hər şeyi dayandırır
  const timersBefore = timers.length;
  S._startBackgroundStatusWatch();
  out.timersAfterSecondStart = timers.length - timersBefore;
  S._stopBackgroundStatusWatch();
  out.timersAfterStop = timers.length;
  process.stdout.write(JSON.stringify(out));
})();
"""


@unittest.skipUnless(shutil.which("node"), "node yoxdur — brauzer JS harness testi ötürülür")
class SupervisionStatusPollHarnessTests(unittest.TestCase):
    def test_background_status_poll_is_ws_first_with_backoff_and_wakeups(self):
        proc = subprocess.run(
            ["node", "-e", NODE_HARNESS, str(JS_DIR)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["initialDelay"], 2000)
        self.assertEqual(out["wsDownDelays"], [2000, 4000, 8000, 10000, 10000])
        self.assertEqual(out["requestsWhileDown"], 5)
        self.assertEqual(out["secondIfNoneMatch"], 'W/"a"')
        self.assertEqual(out["dataOn304"], "active")
        self.assertEqual(out["wsOpenDelay"], 15000)
        self.assertEqual(out["wsOpenDelay2"], 15000)
        self.assertEqual(out["hiddenKick"], 15000)
        self.assertEqual(out["visibleKickDelay"], 0)
        self.assertEqual(out["visibleRequested"], 1)
        self.assertEqual(out["wsCloseKickDelay"], 0)
        self.assertEqual(out["afterWsCloseDelay"], 2000)
        self.assertGreaterEqual(out["after429Delay"], 7000)
        self.assertEqual(out["timersAfterSecondStart"], 0)
        self.assertEqual(out["timersAfterStop"], 0)


class SupervisionStatusJsContractTests(unittest.TestCase):
    def test_no_one_second_network_poll_remains(self):
        source = "\n".join(p.read_text(encoding="utf-8") for p in sorted(JS_DIR.glob("*.js")))
        self.assertNotIn("_bgStatusInterval", source)
        self.assertNotIn("_teacherLockPoll", source)
        self.assertIn("_bgHeartbeatMs: 15000", source)
        self.assertIn("_bgBackoffMinMs: 2000", source)
        self.assertIn("_bgBackoffMaxMs: 10000", source)
        self.assertIn('"If-None-Match"', source)
        self.assertIn("r.status === 429", source)
        self.assertIn('"visibilitychange"', source)
        self.assertIn('"online"', source)
        # Bütün modul importları eyni versiya sorğusunu daşıyır (keş partlatma).
        self.assertNotIn("?v=20260716-intervention", source)
