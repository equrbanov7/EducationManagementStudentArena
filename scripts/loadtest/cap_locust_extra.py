"""Əlavə tutum rejimləri (Locust) — `cap_locust.py` bunları import edir.

  studentjournal — tələbə öz elektron jurnalını açır: «Elektron jurnal» bölməsi
                   (siyahı → fənn detalı `?subject=<enrollment>`), «Fənlərim»,
                   «Ümumi akademik», «Nəticələrim» və tam kabinet səhifəsi.
                   Tələbələr cap jurnallarındandır (seed `CAP_JOURNAL_STUDENT_OFFSET`).
"""

from __future__ import annotations

import random
import re

from locust import between, task

from cap_common import (
    COUNTERS,
    _Base,
    _next_student,
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


EXTRA_CLASSES = {
    "studentjournal": [StudentJournal],
}
