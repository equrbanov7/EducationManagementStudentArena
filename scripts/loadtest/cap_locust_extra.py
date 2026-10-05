"""Əlavə tutum rejimləri (Locust) — `cap_locust.py` bunları import edir.

  studentjournal — tələbə öz elektron jurnalını açır: «Elektron jurnal» bölməsi
                   (siyahı → fənn detalı `?subject=<enrollment>`), «Fənlərim»,
                   «Ümumi akademik», «Nəticələrim» və tam kabinet səhifəsi.
                   Tələbələr cap jurnallarındandır (seed `CAP_JOURNAL_STUDENT_OFFSET`).
  journalfinal   — müəllim: «Aralıq qiymətləndirmə» tabı (midterm/kollokvium, İM
                   pəncərəsi seed-də açıqdır) → bal yazısı → yenidən açılış (DB-dən
                   oxunan dəyər yoxlanır) → 3 xanalıq düzəliş → «Yekun» tabı.
                   + İmtahan Mərkəzi aktoru (`cap_examcenter_NNN`, `final_score.entry`):
                   «İmtahan balı» səhifəsi → yekun imtahan balları (ilk daxiletmə).
                   Gözləntilər `expected-midterm-*.jsonl` / `expected-finals-*.jsonl`.
"""

from __future__ import annotations

import itertools
import os
import random
import re

from locust import between, task

from cap_common import (
    COUNTERS,
    ORIGIN,
    SEED,
    WORKER,
    _Abort,
    _Base,
    _next_student,
    _next_teacher,
    _teacher_limit,
    append_jsonl,
    csrf,
    fixture_error,
    parks,
)

XHR = {"X-Requested-With": "XMLHttpRequest"}
SUBJECT_RE = re.compile(r"[?&]amp;subject=([0-9a-f-]{36})|[?&]subject=([0-9a-f-]{36})")
PERIOD_RE = re.compile(r"[?&](?:amp;)?period=([0-9a-f-]{36}|\d+)")


def _section(user, name, query="", label=None):
    """Kabinet bölməsi (AJAX JSON {ok, html}); uğursuzluq hesabata yazılır, html qaytarılır."""
    with user.client.get(
        f"/accounts/profile/api/sections/{name}/{query}",
        name=label or f"section {name}",
        headers=XHR,
        catch_response=True,
        timeout=30,
    ) as r:
        try:
            payload = r.json()
        except Exception:
            payload = {}
        if r.status_code != 200 or payload.get("ok") is not True:
            r.failure(f"section {name}: {r.status_code} {r.error} {(r.text or '')[:160]!r}")
            return ""
        return payload.get("html") or ""


class StudentJournal(_Base):
    """Tələbə: öz jurnalı (siyahı + fənn detalı), fənlər, akademik xülasə, nəticələr."""

    wait_time = between(5, 15)
    weight = 1

    @parks
    def on_start(self):
        self.index, self.username = _next_student(self)
        self._client_setup(self.index, "/accounts/login/telebe/")
        self._preauth_student(self.index, self.username)
        self.subjects = []
        self.period = ""
        self._wait_for_go()

    @task(3)
    @parks
    def journal(self):
        html = _section(self, "my-journal", label="sj journal list")
        found = [a or b for a, b in SUBJECT_RE.findall(html)]
        if found:
            self.subjects = sorted(set(found))
            period = PERIOD_RE.search(html)
            self.period = period.group(1) if period else ""
        COUNTERS["student_journal_views"] += 1
        if not self.subjects:
            return
        self._think(2, 6)
        subject = random.choice(self.subjects)
        query = f"?subject={subject}" + (f"&period={self.period}" if self.period else "")
        _section(self, "my-journal", query, label="sj journal subject")

    @task(2)
    @parks
    def subjects_section(self):
        _section(self, "my-subjects", label="sj my-subjects")

    @task(1)
    @parks
    def academic(self):
        _section(self, "overall-academic", label="sj overall-academic")

    @task(1)
    @parks
    def results(self):
        _section(self, "my-results", label="sj my-results")

    @task(1)
    @parks
    def full_page(self):
        with self.client.get(
            "/accounts/profile/?section=my-journal", name="sj cabinet page (my-journal)", catch_response=True, timeout=30
        ) as r:
            if r.status_code != 200:
                r.failure(f"cabinet my-journal: {r.status_code} {r.error}")


KSELECT_RE = re.compile(r'<select\b[^>]*name="kscore__([0-9a-f-]+)__([0-9a-f-]+)"[^>]*>(.*?)</select>', re.S)
OPTION_RE = re.compile(r'<option value="(\d+)"')
SELECTED_RE = re.compile(r'<option value="(\d*)"\s*selected')


def _kscore_cells(html):
    """{(component, enrollment): (seçilmiş dəyər, [mümkün ballar])} — redaktə oluna bilən xanalar."""
    cells = {}
    for component, enrollment, body in KSELECT_RE.findall(html or ""):
        chosen = SELECTED_RE.search(body)
        cells[(component, enrollment)] = (chosen.group(1) if chosen else "", OPTION_RE.findall(body))
    return cells


class JournalFinalTeacher(_Base):
    """Müəllim: midterm/kollokvium balları (İM pəncərəsi) + yekun tab."""

    wait_time = between(1, 2)
    weight = 10

    @parks
    def on_start(self):
        index, self.username, self.offering = _next_teacher(self)
        self._client_setup(61000 + index, "/accounts/login/muellim/")
        self._login(self.username, "muellim", "[pre] ")

    def _tab(self, name, tab):
        path = f"/jurnal/{self.offering}/?jt={tab}"
        self.client.headers["Referer"] = ORIGIN + path
        with self.client.get(path, name=name, catch_response=True, timeout=30) as r:
            body = r.text
            if r.status_code != 200:
                r.failure(f"{name}: {r.status_code} {r.error}")
                raise _Abort()
        return body

    def _post_scores(self, name, token, values):
        path = f"/jurnal/{self.offering}/kollokvium/"
        data = {"csrfmiddlewaretoken": token}
        data.update({f"kscore__{c}__{e}": v for (c, e), v in values.items()})
        with self.client.post(path, data=data, name=name, allow_redirects=False, catch_response=True, timeout=40) as r:
            if r.status_code not in (302, 303) or f"/jurnal/{self.offering}/" not in r.headers.get("Location", ""):
                r.failure(f"{name}: {r.status_code} {r.error}")
                raise _Abort()

    @task
    @parks
    def work(self):
        self._wait_for_go()
        body = self._tab("jf midterm tab", "kollokvium")
        cells = _kscore_cells(body)
        token = csrf(body)
        if not cells or not token:
            fixture_error(self, "jf midterm parse", f"cells={len(cells)} csrf={bool(token)} window_closed={'jd2-kwin-note' in body}")
            raise _Abort()
        self._think(10, 30)
        expected = {key: random.choice(opts[1:] or opts) for key, (_cur, opts) in cells.items()}
        self._post_scores("jf midterm save", token, expected)
        body = self._tab("jf midterm reopen", "kollokvium")
        stored = _kscore_cells(body)
        lost = sum(1 for key, v in expected.items() if stored.get(key, ("",))[0] != v)
        if lost:
            fixture_error(self, "jf midterm not persisted", f"{lost}/{len(expected)} cells differ after save")
        token = csrf(body) or token
        self._think(5, 15)
        edit = {key: random.choice(cells[key][1]) for key in random.sample(sorted(cells), min(3, len(cells)))}
        self._post_scores("jf midterm edit", token, edit)
        expected.update(edit)
        append_jsonl(
            "expected-midterm",
            {"offering": self.offering, "scores": {f"{c}:{e}": int(v) for (c, e), v in expected.items()}},
        )
        COUNTERS["midterm_saved"] += 1
        self._think(3, 8)
        self._tab("jf final tab", "yekun")
        raise _Abort()


_clerk_cursor = itertools.count(int(WORKER) * 7)
_final_offering_cursor = itertools.count(int(os.environ.get("CAP_T_OFFSET", "0")))


class FinalScoreClerk(_Base):
    """İmtahan Mərkəzi: «İmtahan balı» səhifəsi → açılış üzrə yekun imtahan balları (ilk daxiletmə).

    Hər açılış run-da bir dəfə (worker-in müəllim zolağından) — təkrar yazı sənədli
    düzəliş tələb edərdi (seed hər run balları sıfırlayır)."""

    wait_time = between(1, 2)
    weight = 1
    fixed_count = int(os.environ.get("CAP_CLERK_USERS", "0") or 0)

    @parks
    def on_start(self):
        clerks = SEED.get("clerks") or []
        if not clerks:
            fixture_error(self, "clerk pool empty", "seed.clerks")
            raise _Abort()
        k = next(_clerk_cursor)
        self.username = clerks[k % len(clerks)]
        self._client_setup(62000 + k, "/accounts/login/muellim/")
        self._login(self.username, "muellim", "[pre] ")

    @task
    @parks
    def enter_scores(self):
        self._wait_for_go()
        index = next(_final_offering_cursor)
        journals = SEED.get("journals") or []
        if index >= _teacher_limit or index >= len(journals):
            self._park()
        offering = journals[index][1]
        enrollments = (SEED.get("enrollments") or {}).get(offering) or []
        page = f"/accounts/imtahan-bali/?ese_offering={offering}"
        self.client.headers["Referer"] = ORIGIN + page
        with self.client.get(page, name="jf exam-score page", catch_response=True, timeout=30) as r:
            token = csrf(r.text) or self.client.cookies.get("csrftoken", "")
            if r.status_code != 200:
                r.failure(f"exam-score page: {r.status_code} {r.error}")
                raise _Abort()
        self._think(15, 40)  # kağız vərəqdən köçürmə
        scores = {e: random.randint(10, 50) for e in enrollments}
        data = {
            "csrfmiddlewaretoken": token,
            "action": "save_scores",
            "offering_id": offering,
            "next": "/accounts/profile/?section=exam-score-entry",
            "exam_kind": "written",
        }
        data.update({f"score__{e}": str(v) for e, v in scores.items()})
        with self.client.post(
            "/accounts/imtahan-bali/", data=data, name="jf exam-score save", allow_redirects=False, catch_response=True, timeout=40
        ) as r:
            location = r.headers.get("Location", "")
            if r.status_code not in (302, 303) or "ese_saved=1" not in location:
                r.failure(f"exam-score save: {r.status_code} {r.error} → {location[:160]}")
                raise _Abort()
        append_jsonl("expected-finals", {"offering": offering, "scores": scores})
        COUNTERS["final_scores_saved"] += 1
        with self.client.get(location, name="jf exam-score after save", catch_response=True, timeout=30) as r:
            if r.status_code != 200:
                r.failure(f"exam-score after save: {r.status_code} {r.error}")


EXTRA_CLASSES = {
    "studentjournal": [StudentJournal],
    "journalfinal": [JournalFinalTeacher, FinalScoreClerk],
}
