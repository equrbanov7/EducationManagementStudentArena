"""Tutum testi Locust ssenarilərinin ortaq hissəsi (konfiq, köməkçilər, `_Base`).

`cap_locust.py` (əsas rejimlər) və `cap_locust_extra.py` (əlavə rejimlər) bunu
import edir — modul bir dəfə yüklənir, sayğaclar (COUNTERS) və kursorlar ortaqdır.
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
from locust import HttpUser

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

COUNTERS = {
    "logged_in": 0,
    "login_failed": 0,
    "exam_finished": 0,
    "journal_saved": 0,
    "pool_exhausted": 0,
    "student_journal_views": 0,
    "midterm_saved": 0,
    "final_scores_saved": 0,
    "exports_done": 0,
    "export_bytes": 0,
    "final_finished": 0,
}


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


class _Abort(Exception):
    """Axın kəsildi — sorğu artıq hesabata yazılıb; VU pillə sonuna qədər park olur."""


def parks(fn):
    def wrapper(self, *a, **kw):
        try:
            return fn(self, *a, **kw)
        except _Abort:
            self._park()

    wrapper.__name__ = fn.__name__
    return wrapper


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
            raise _Abort()
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
            raise _Abort()
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
            raise _Abort()
        # Domen verilmir: cookiejar nöqtəsiz hostu («edge») «edge.local» kimi saxlayır,
        # domain="edge" olan kuki heç bir sorğuya uyğun gəlməzdi.
        self.client.cookies.set("sessionid", key, path="/")
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
        raise _Abort()
    return index + 1, f"stress_student_{index + 1:0{PAD}d}"


def _next_teacher(user):
    """Bu worker-in müəllim zolağından növbəti (müəllim, jurnal) cütü."""
    index = next(_teacher_cursor)
    journals = SEED.get("journals") or []
    if index >= _teacher_limit or index >= len(journals):
        COUNTERS["pool_exhausted"] += 1
        fixture_error(user, "teacher pool exhausted", f"index {index}")
        raise _Abort()
    username, offering = journals[index]
    return index, username, offering



def run_attempt(user, url, token, kind="exam", prefix="exam "):
    """Açılmış cəhd: suallar → hər sual üçün autosave → finish → nəticə. Nəticə URL-ini qaytarır.

    Gözlənilən cavablar `expected-answers` ledger-inə (`kind` ilə) yazılır (cap_reconcile)."""
    user.client.headers["Referer"] = ORIGIN + url
    with user.client.get(url, name=f"{prefix}questions page", catch_response=True, timeout=30) as r:
        html = r.text
        if r.status_code != 200:
            r.failure(f"questions page: {r.status_code} {r.error}")
            raise _Abort()
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
        fixture_error(user, f"{prefix}questions parse", "no MCQ inputs on attempt page")
        raise _Abort()
    selected = {}
    headers = {"X-Requested-With": "XMLHttpRequest", "X-CSRFToken": token}
    order = list(options)
    # ~20% tələbə bir cavabı sonradan dəyişir (real davranış).
    changes = order + ([random.choice(order)] if random.random() < 0.2 else [])
    for qid in changes:
        user._think()
        selected[qid] = random.choice(options[qid])
        data = {
            "csrfmiddlewaretoken": token,
            "submit_action": "autosave",
            "autosave_revision": revision,
            f"q_{qid}": selected[qid],
            f"q_present_{qid}": "1",
            "changed_questions[]": [qid],
        }
        with user.client.post(url, data=data, headers=headers, name=f"{prefix}autosave", catch_response=True, timeout=30) as r:
            try:
                payload = r.json()
            except Exception:
                payload = {}
            if r.status_code == 200 and payload.get("success") is True:
                revision = str(payload.get("server_revision", revision))
            else:
                r.failure(f"autosave: {r.status_code} {r.error} {str(payload)[:80]} body={(r.text or '')[:120]!r} srv={r.headers.get('Server', '')}")
                # Real klient Retry-After/backoff ilə təkrarlayır — burada bir dəfə.
                gevent.sleep(float(r.headers.get("Retry-After", "3") or 3))
    gevent.sleep(2)
    data = {"csrfmiddlewaretoken": token, "submit_action": "finish", "autosave_revision": revision}
    for qid, value in selected.items():
        data[f"q_{qid}"] = value
        data[f"q_present_{qid}"] = "1"
    data["changed_questions[]"] = list(selected)
    with user.client.post(url, data=data, headers=headers, name=f"{prefix}finish", catch_response=True, timeout=40) as r:
        try:
            payload = r.json()
        except Exception:
            payload = {}
        if not (r.status_code == 200 and payload.get("finished") is True):
            r.failure(f"finish: {r.status_code} {r.error} {str(payload)[:80]} body={(r.text or '')[:120]!r} srv={r.headers.get('Server', '')}")
            raise _Abort()
    attempt = int(url.rstrip("/").split("/")[-1])
    append_jsonl("expected-answers", {"attempt": attempt, "selected": selected, "kind": kind})
    COUNTERS["exam_finished" if kind == "exam" else "final_finished"] += 1
    result_url = payload.get("redirect_url") or url + "result/"
    with user.client.get(result_url, name=f"{prefix}result", catch_response=True, timeout=30) as r:
        if r.status_code != 200:
            r.failure(f"result: {r.status_code} {r.error}")
    return result_url
