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
  Əlavə rejimlər (studentjournal, journalfinal, export, finalcenter) — bax
  `cap_locust_extra.py`.

Hesab zolağı: hər worker `CAP_OFFSET`/`CAP_SHARD` (tələbə indeksləri) və
`CAP_T_OFFSET`/`CAP_T_SHARD` (müəllim siyahısında) ilə ayrıca zolaq alır.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gevent  # noqa: E402
from locust import between, events, task  # noqa: E402

from cap_common import (  # noqa: E402
    ATT_RE,
    COUNTERS,
    INPUT_RE,
    MODE,
    ORIGIN,
    SEED,
    STAGE,
    WORKER,
    _Abort,
    _Base,
    _next_student,
    _teacher_cursor,
    _teacher_limit,
    append_jsonl,
    csrf,
    fixture_error,
    parks,
)


class LoginStudent(_Base):
    """Kütləvi giriş: login səhifəsi + POST + kabinetin özü."""

    wait_time = between(1, 2)
    weight = 1

    @task
    @parks
    def login_once(self):
        index, username = _next_student(self)
        self._client_setup(index, "/accounts/login/telebe/")
        landing = self._login(username, "telebe", "")
        with self.client.get(landing or "/accounts/kabinet/", name="cabinet landing", catch_response=True, timeout=20) as r:
            if r.status_code != 200:
                r.failure(f"landing: {r.status_code} {r.error}")
        raise _Abort()


class ExamStudent(_Base):
    """Bir imtahan: başla → hər sual üçün autosave → finish → nəticə."""

    wait_time = between(1, 2)
    weight = 6

    @parks
    def on_start(self):
        self.index, self.username = _next_student(self)
        self._client_setup(self.index, "/accounts/login/telebe/")
        self._preauth_student(self.index, self.username)

    @task
    @parks
    def take_exam(self):
        self._wait_for_go()
        slug = SEED["exam_slug"]
        start_path = f"/exams/{slug}/start/"
        self.client.headers["Referer"] = ORIGIN + start_path
        with self.client.get(start_path, name="exam confirm", catch_response=True, timeout=30) as r:
            token = csrf(r.text)
            if r.status_code != 200 or not token:
                r.failure(f"confirm: {r.status_code} {r.error}")
                raise _Abort()
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
                raise _Abort()
            url = found.group(0)
        self.client.headers["Referer"] = ORIGIN + url
        with self.client.get(url, name="exam questions page", catch_response=True, timeout=30) as r:
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
            fixture_error(self, "exam questions parse", "no MCQ inputs on attempt page")
            raise _Abort()
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
                    r.failure(f"autosave: {r.status_code} {r.error} {str(payload)[:80]} body={(r.text or '')[:120]!r} srv={r.headers.get('Server', '')}")
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
                r.failure(f"finish: {r.status_code} {r.error} {str(payload)[:80]} body={(r.text or '')[:120]!r} srv={r.headers.get('Server', '')}")
                raise _Abort()
        attempt = int(url.rstrip("/").split("/")[-1])
        append_jsonl("expected-answers", {"attempt": attempt, "selected": selected})
        COUNTERS["exam_finished"] += 1
        with self.client.get(payload.get("redirect_url") or url + "result/", name="exam result", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"result: {r.status_code} {r.error}")
        raise _Abort()


class JournalTeacher(_Base):
    """Müəllim: jurnal siyahısı → jurnal → davamiyyət+bal → yenidən açılış → düzəliş."""

    wait_time = between(1, 2)
    weight = 1

    @parks
    def on_start(self):
        index = next(_teacher_cursor)
        journals = SEED.get("journals") or []
        if index >= _teacher_limit or index >= len(journals):
            COUNTERS["pool_exhausted"] += 1
            fixture_error(self, "teacher pool exhausted", f"index {index}")
            raise _Abort()
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
                raise _Abort()
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
                raise _Abort()
        return expected

    @task
    @parks
    def work(self):
        self._wait_for_go()
        self.client.headers["Referer"] = ORIGIN + "/jurnal/"
        with self.client.get("/jurnal/", name="journal list", catch_response=True, timeout=30) as r:
            if r.status_code != 200 or self.offering not in r.text:
                r.failure(f"journal list: {r.status_code} {r.error} has_offering={self.offering in (r.text or '')}")
                raise _Abort()
        body = self._open("journal open")
        cells = sorted(set(ATT_RE.findall(body)))
        token = csrf(body)
        if not cells or not token:
            # cells=0 + today_cols>0 → bugünkü dərs var, amma xanalar kilidlidir (köhnə işarə,
            # 2 saat pəncərəsi); today_cols=0 → dərs tarixi Bakı «bu gün»ü deyil.
            fixture_error(
                self,
                "journal grid parse",
                f"cells={len(cells)} csrf={bool(token)} today_cols={body.count('is-today')} locked_ro={body.count('jd2-ro--')}",
            )
            raise _Abort()
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
        raise _Abort()


class CabinetStudent(_Base):
    """Kabinetdə gəzən tələbə (imtahan/nəticə/cədvəl bölmələri)."""

    wait_time = between(5, 15)
    weight = 3
    SECTIONS = ("dashboard", "assigned-exams", "my-results", "profile-info")

    @parks
    def on_start(self):
        self.index, self.username = _next_student(self)
        self._client_setup(self.index, "/accounts/login/telebe/")
        self._preauth_student(self.index, self.username)
        self._wait_for_go()

    @task(3)
    @parks
    def section(self):
        name = random.choice(self.SECTIONS)
        with self.client.get(
            f"/accounts/profile/api/sections/{name}/",
            name="cabinet section",
            headers={"X-Requested-With": "XMLHttpRequest"},
            catch_response=True,
            timeout=30,
        ) as r:
            try:
                good = r.status_code == 200 and r.json().get("ok") is True
            except Exception:
                good = False
            if not good:
                r.failure(f"section {name}: {r.status_code} {r.error} {(r.text or '')[:160]!r}")

    @task(1)
    @parks
    def cabinet(self):
        with self.client.get("/accounts/kabinet/", name="cabinet page", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"cabinet: {r.status_code} {r.error}")

    @task(1)
    @parks
    def schedule(self):
        with self.client.get("/jurnal/cedvel/", name="student schedule", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"student schedule: {r.status_code} {r.error}")


from cap_locust_extra import EXTRA_CLASSES  # noqa: E402

# Locust User siniflərini locustfile-ın öz adlar fəzasından tapır.
for _extra in EXTRA_CLASSES.values():
    globals().update({_c.__name__: _c for _c in _extra})

_CLASSES = {
    "login": [LoginStudent],
    "exam": [ExamStudent],
    "journal": [JournalTeacher],
    "cabinet": [CabinetStudent],
    "mixed": [ExamStudent, CabinetStudent, JournalTeacher],
    **EXTRA_CLASSES,
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
