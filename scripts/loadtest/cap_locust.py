"""Tutum testi ssenariləri (Locust) — izolə test stack-inə (https://edge) vurur.

Rejimlər (`CAP_MODE`):
  login   — kütləvi giriş: hər VU giriş səhifəsi + POST + kabinet, sonra dayanır.
  exam    — əvvəlcə giriş ("[pre]"), sonra `CAP_GO_AT`-dan başlayaraq
            `CAP_START_WINDOW` saniyə ərzində hər tələbə imtahana BİR dəfə başlayır,
            hər sualdan sonra autosave (real klient kimi, `autosave_revision` ilə),
            sonda finish + nəticə səhifəsi. Gözlənilən cavablar JSONL-ə yazılır.
  journal — müəllim girişi ("[pre]"), jurnal siyahısı → jurnal → davamiyyət+bal
            yazısı → yenidən açılış → 3 xanalıq düzəliş → cədvəl.
  cabinet — tələbə kabineti: kabinet + bölmə fraqmentləri, düşünmə vaxtı ilə.
  mixed   — exam (60%) + cabinet (30%) + journal (10%).

Hesab zolağı: hər worker `CAP_OFFSET`/`CAP_SHARD` (tələbə indeksləri) və
`CAP_T_OFFSET`/`CAP_T_SHARD` (müəllim siyahısında) ilə ayrıca zolaq alır.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import re
import time
from pathlib import Path

import gevent
from locust import HttpUser, between, events, task
from locust.exception import StopUser

CAP = Path(os.environ.get("CAP_DIR", "/capacity"))
RUN_DIR = Path(os.environ.get("CAP_RUN_DIR", "/capacity/runs/local"))
CRED = json.loads((CAP / "credentials.json").read_text())
SEED = json.loads(Path(os.environ["CAP_SEED"]).read_text())
MODE = os.environ.get("CAP_MODE", "exam")
STAGE = os.environ.get("CAP_STAGE", "stage")
WORKER = os.environ.get("CAP_WORKER", "0")
PAD = int(os.environ.get("CAP_STUDENT_PAD", "3"))
GO_AT = float(os.environ.get("CAP_GO_AT", "0") or 0)
START_WINDOW = float(os.environ.get("CAP_START_WINDOW", "60") or 60)
THINK_MIN, THINK_MAX = (float(x) for x in os.environ.get("CAP_THINK", "8:20").split(":"))
ORIGIN = os.environ.get("CAP_ORIGIN", "https://localhost:18443")
CERT = str(CAP / "cert.pem")
SESSIONS = json.loads(Path(os.environ["CAP_SESSIONS"]).read_text()) if os.environ.get("CAP_SESSIONS") else None

_student_cursor = itertools.count(int(os.environ.get("CAP_OFFSET", "0")))
_student_limit = int(os.environ.get("CAP_OFFSET", "0")) + int(os.environ.get("CAP_SHARD", "1000000"))
_teacher_cursor = itertools.count(int(os.environ.get("CAP_T_OFFSET", "0")))
_teacher_limit = int(os.environ.get("CAP_T_OFFSET", "0")) + int(os.environ.get("CAP_T_SHARD", "1000000"))

INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
ATT_RE = re.compile(r'name="att__([0-9a-f-]+)__([0-9a-f-]+)"')

COUNTERS = {"logged_in": 0, "login_failed": 0, "exam_finished": 0, "journal_saved": 0, "pool_exhausted": 0}


def csrf(text: str) -> str:
    for tag in INPUT_RE.findall(text or ""):
        if "csrfmiddlewaretoken" in tag:
            found = re.search(r"value=[\"']([^\"']+)", tag)
            if found:
                return found.group(1)
    return ""


def fixture_error(user, name, message):
    user.environment.events.request.fire(
        request_type="FIXTURE",
        name=name,
        response_time=0,
        response_length=0,
        exception=RuntimeError(message),
    )


def append_jsonl(name, row):
    path = RUN_DIR / f"{name}-{STAGE}-w{WORKER}.jsonl"
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


class _Base(HttpUser):
    abstract = True
    host = "https://edge"

    def _park(self):
        """Bitmiş VU pillə sonuna qədər boş gözləyir (StopUser locust-da yenidən spawn edir)."""
        while True:
            gevent.sleep(3600)

    def _client_setup(self, index, referer_path):
        self.client.verify = CERT
        # Edge test nginx-i bu başlığı X-Forwarded-For kimi ötürür → hər VU ayrı
        # «IP» (real imtahan günü kimi); login/IP limitləri süni toqquşmasın.
        self.client.headers.update(
            {
                "X-Test-Client": f"10.{200 + index // 62500}.{(index // 250) % 250}.{index % 250 + 1}",
                "Referer": ORIGIN + referer_path,
            }
        )

    def _login(self, username, portal, prefix):
        path = f"/accounts/login/{portal}/"
        with self.client.get(path, name=f"{prefix}login page", catch_response=True, timeout=20) as page:
            token = csrf(page.text)
            ok = page.status_code == 200 and bool(token)
            if not ok:
                page.failure(f"login page: {page.status_code} {page.error}")
        if not ok:
            COUNTERS["login_failed"] += 1
            self._park()
        with self.client.post(
            path,
            data={"username": username, "password": CRED["password"], "csrfmiddlewaretoken": token},
            name=f"{prefix}login submit",
            allow_redirects=False,
            catch_response=True,
            timeout=20,
        ) as resp:
            location = resp.headers.get("Location", "")
            ok = resp.status_code in (302, 303) and "/login" not in location and bool(self.client.cookies.get("sessionid"))
            if not ok:
                resp.failure(f"login submit: {resp.status_code} {resp.error} → {location}")
        if not ok:
            COUNTERS["login_failed"] += 1
            self._park()
        COUNTERS["logged_in"] += 1
        return location

    def _preauth_student(self, index, username):
        """Sessiya hovuzu varsa login-siz (cookie), yoxdursa real login ilə."""
        if SESSIONS is None:
            self._login(username, "telebe", "[pre] ")
            return
        key = SESSIONS.get(str(index))
        if not key:
            COUNTERS["pool_exhausted"] += 1
            fixture_error(self, "session pool missing", f"student {index}")
            self._park()
        self.client.cookies.set("sessionid", key, domain=self.host.split("://", 1)[-1].split(":")[0], path="/")
        COUNTERS["logged_in"] += 1

    def _wait_for_go(self):
        go = GO_AT + random.uniform(0, START_WINDOW)
        delay = go - time.time()
        if delay > 0:
            gevent.sleep(delay)

    def _think(self, low=None, high=None):
        gevent.sleep(random.uniform(low if low is not None else THINK_MIN, high if high is not None else THINK_MAX))


def _next_student(user):
    index = next(_student_cursor)
    if index >= _student_limit or index >= int(CRED["count"]):
        COUNTERS["pool_exhausted"] += 1
        fixture_error(user, "student pool exhausted", f"index {index} ≥ {_student_limit}")
        user._park()
    return index + 1, f"stress_student_{index + 1:0{PAD}d}"


class LoginStudent(_Base):
    """Kütləvi giriş: login səhifəsi + POST + kabinetin özü."""

    wait_time = between(1, 2)
    weight = 1

    @task
    def login_once(self):
        index, username = _next_student(self)
        self._client_setup(index, "/accounts/login/telebe/")
        landing = self._login(username, "telebe", "")
        with self.client.get(landing or "/accounts/kabinet/", name="cabinet landing", catch_response=True, timeout=20) as r:
            if r.status_code != 200:
                r.failure(f"landing: {r.status_code} {r.error}")
        self._park()


class ExamStudent(_Base):
    """Bir imtahan: başla → hər sual üçün autosave → finish → nəticə."""

    wait_time = between(1, 2)
    weight = 6

    def on_start(self):
        self.index, self.username = _next_student(self)
        self._client_setup(self.index, "/accounts/login/telebe/")
        self._preauth_student(self.index, self.username)

    @task
    def take_exam(self):
        self._wait_for_go()
        slug = SEED["exam_slug"]
        start_path = f"/exams/{slug}/start/"
        self.client.headers["Referer"] = ORIGIN + start_path
        with self.client.get(start_path, name="exam confirm", catch_response=True, timeout=30) as r:
            token = csrf(r.text)
            if r.status_code != 200 or not token:
                r.failure(f"confirm: {r.status_code} {r.error}")
                self._park()
        with self.client.post(
            start_path,
            data={"csrfmiddlewaretoken": token},
            name="exam start",
            allow_redirects=False,
            catch_response=True,
            timeout=40,
        ) as r:
            found = re.search(r"/exams/[^/]+/attempt/\d+/", r.headers.get("Location", ""))
            if r.status_code not in (302, 303) or not found:
                r.failure(f"start: {r.status_code} {r.error} → {r.headers.get('Location', '')[:120]} {r.headers.get('Retry-After', '')}")
                self._park()
            url = found.group(0)
        self.client.headers["Referer"] = ORIGIN + url
        with self.client.get(url, name="exam questions page", catch_response=True, timeout=30) as r:
            html = r.text
            if r.status_code != 200:
                r.failure(f"questions page: {r.status_code} {r.error}")
                self._park()
        options = {}
        revision = "0"
        for tag in INPUT_RE.findall(html):
            name = re.search(r"name=.q_([0-9]+).", tag)
            value = re.search(r"value=.([a-zA-Z0-9_-]+)", tag)
            if name and value and "radio" in tag:
                options.setdefault(name.group(1), []).append(value.group(1))
            if 'name="autosave_revision"' in tag:
                found_rev = re.search(r'value="(\d+)"', tag)
                revision = found_rev.group(1) if found_rev else "0"
        token = csrf(html) or token
        if not options:
            fixture_error(self, "exam questions parse", "no MCQ inputs on attempt page")
            self._park()
        selected = {}
        headers = {"X-Requested-With": "XMLHttpRequest", "X-CSRFToken": token}
        order = list(options)
        # ~20% tələbə bir cavabı sonradan dəyişir (real davranış).
        changes = order + ([random.choice(order)] if random.random() < 0.2 else [])
        for qid in changes:
            self._think()
            selected[qid] = random.choice(options[qid])
            data = {
                "csrfmiddlewaretoken": token,
                "submit_action": "autosave",
                "autosave_revision": revision,
                f"q_{qid}": selected[qid],
                f"q_present_{qid}": "1",
                "changed_questions[]": [qid],
            }
            with self.client.post(url, data=data, headers=headers, name="exam autosave", catch_response=True, timeout=30) as r:
                try:
                    payload = r.json()
                except Exception:
                    payload = {}
                if r.status_code == 200 and payload.get("success") is True:
                    revision = str(payload.get("server_revision", revision))
                else:
                    r.failure(f"autosave: {r.status_code} {r.error} {str(payload)[:80]}")
                    # Real klient Retry-After/backoff ilə təkrarlayır — burada bir dəfə.
                    gevent.sleep(float(r.headers.get("Retry-After", "3") or 3))
        gevent.sleep(2)
        data = {"csrfmiddlewaretoken": token, "submit_action": "finish", "autosave_revision": revision}
        for qid, value in selected.items():
            data[f"q_{qid}"] = value
            data[f"q_present_{qid}"] = "1"
        data["changed_questions[]"] = list(selected)
        with self.client.post(url, data=data, headers=headers, name="exam finish", catch_response=True, timeout=40) as r:
            try:
                payload = r.json()
            except Exception:
                payload = {}
            if not (r.status_code == 200 and payload.get("finished") is True):
                r.failure(f"finish: {r.status_code} {r.error} {str(payload)[:80]}")
                self._park()
        attempt = int(url.rstrip("/").split("/")[-1])
        append_jsonl("expected-answers", {"attempt": attempt, "selected": selected})
        COUNTERS["exam_finished"] += 1
        with self.client.get(payload.get("redirect_url") or url + "result/", name="exam result", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"result: {r.status_code} {r.error}")
        self._park()


class JournalTeacher(_Base):
    """Müəllim: jurnal siyahısı → jurnal → davamiyyət+bal → yenidən açılış → düzəliş."""

    wait_time = between(1, 2)
    weight = 1

    def on_start(self):
        index = next(_teacher_cursor)
        journals = SEED.get("journals") or []
        if index >= _teacher_limit or index >= len(journals):
            COUNTERS["pool_exhausted"] += 1
            fixture_error(self, "teacher pool exhausted", f"index {index}")
            self._park()
        self.username, self.offering = journals[index]
        self._client_setup(60000 + index, "/accounts/login/muellim/")
        self._login(self.username, "muellim", "[pre] ")

    def _open(self, name):
        path = f"/jurnal/{self.offering}/"
        self.client.headers["Referer"] = ORIGIN + path
        with self.client.get(path, name=name, catch_response=True, timeout=30) as r:
            body = r.text
            if r.status_code != 200:
                r.failure(f"{name}: {r.status_code} {r.error}")
                self._park()
        return body

    def _save(self, name, cells, token, pattern):
        data = {"csrfmiddlewaretoken": token}
        expected = {}
        for i, (lesson, enrollment) in enumerate(cells):
            status, score = pattern(i)
            data[f"att__{lesson}__{enrollment}"] = status
            if score is not None:
                data[f"score__{lesson}__{enrollment}"] = str(score)
            expected[f"{lesson}:{enrollment}"] = [status, score]
        path = f"/jurnal/{self.offering}/"
        with self.client.post(path, data=data, name=name, allow_redirects=False, catch_response=True, timeout=40) as r:
            if r.status_code not in (302, 303) or path not in r.headers.get("Location", ""):
                r.failure(f"{name}: {r.status_code} {r.error}")
                self._park()
        return expected

    @task
    def work(self):
        self._wait_for_go()
        self.client.headers["Referer"] = ORIGIN + "/jurnal/"
        with self.client.get("/jurnal/", name="journal list", catch_response=True, timeout=30) as r:
            if r.status_code != 200 or self.offering not in r.text:
                r.failure(f"journal list: {r.status_code} {r.error} has_offering={self.offering in (r.text or '')}")
                self._park()
        body = self._open("journal open")
        cells = sorted(set(ATT_RE.findall(body)))
        token = csrf(body)
        if not cells or not token:
            fixture_error(self, "journal grid parse", f"cells={len(cells)} csrf={bool(token)}")
            self._park()
        self._think(10, 30)  # müəllim davamiyyəti işarələyir

        def first_pass(i):
            if i % 9 == 0:
                return "absent", None
            return "present", 5 + (i % 6)

        expected = self._save("journal save marks", cells, token, first_pass)
        body = self._open("journal reopen")
        token = csrf(body) or token
        self._think(10, 25)
        edit = random.sample(cells, min(3, len(cells)))

        def correction(i):
            return "present", 9

        expected.update(self._save("journal edit marks", edit, token, correction))
        append_jsonl("expected-marks", {"offering": self.offering, "marks": expected})
        COUNTERS["journal_saved"] += 1
        with self.client.get("/jurnal/cedvel/", name="journal schedule", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"schedule: {r.status_code} {r.error}")
        self._park()


class CabinetStudent(_Base):
    """Kabinetdə gəzən tələbə (imtahan/nəticə/cədvəl bölmələri)."""

    wait_time = between(5, 15)
    weight = 3
    SECTIONS = ("dashboard", "assigned-exams", "my-results", "profile-info")

    def on_start(self):
        self.index, self.username = _next_student(self)
        self._client_setup(self.index, "/accounts/login/telebe/")
        self._preauth_student(self.index, self.username)
        self._wait_for_go()

    @task(3)
    def section(self):
        name = random.choice(self.SECTIONS)
        with self.client.get(
            f"/accounts/profile/api/sections/{name}/", name="cabinet section", catch_response=True, timeout=30
        ) as r:
            try:
                good = r.status_code == 200 and r.json().get("ok") is True
            except Exception:
                good = False
            if not good:
                r.failure(f"section {name}: {r.status_code} {r.error} {(r.text or '')[:160]!r}")

    @task(1)
    def cabinet(self):
        with self.client.get("/accounts/kabinet/", name="cabinet page", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"cabinet: {r.status_code} {r.error}")

    @task(1)
    def schedule(self):
        with self.client.get("/jurnal/cedvel/", name="student schedule", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"student schedule: {r.status_code} {r.error}")


_CLASSES = {
    "login": [LoginStudent],
    "exam": [ExamStudent],
    "journal": [JournalTeacher],
    "cabinet": [CabinetStudent],
    "mixed": [ExamStudent, CabinetStudent, JournalTeacher],
}
for _name, _cls in list(globals().items()):
    if isinstance(_cls, type) and issubclass(_cls, _Base) and _cls is not _Base:
        _cls.abstract = _cls not in _CLASSES[MODE]


@events.quitting.add_listener
def _summary(environment, **kwargs):
    stats = environment.stats.total
    row = dict(COUNTERS, stage=STAGE, worker=WORKER, requests=stats.num_requests, failures=stats.num_failures)
    print("CAP_COUNTERS " + json.dumps(row), flush=True)
    append_jsonl("counters", row)
