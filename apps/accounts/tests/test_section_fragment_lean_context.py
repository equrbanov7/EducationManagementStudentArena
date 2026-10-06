"""Kabinet bölmə fraqmenti — yığcam (lean) context xarakterizasiyası (tutum 2026-10-06).

Problem (yük testi, 8 replika × 0.5 CPU): ``/accounts/profile/api/sections/<bölmə>/``
hər bölmə üçün BÜTÜN profil context-ini (sidebar badge-ləri, bildiriş vəziyyəti,
kurs/imtahan sayları, parol formaları, …) qurub yalnız bölmənin partial-ını render
edirdi — ~150 ms app CPU / 43–55 SQL sorğu. Fraqment rejimində qabığa aid (shell-only)
iş artıq tənbəldir (``context_builder/_lazy.py``): partial oxumursa heç hesablanmır.

Bu testlər iki şeyi qoruyur:

* **Bayt-bayt eynilik** — eyni sorğu həm yığcam (defolt), həm də TAM (``LEAN_FRAGMENT_CONTEXT``
  söndürülüb = köhnə kod yolu) context-lə render olunur; ``html`` (csrf/nonce normallaşdırılıb)
  eyni olmalıdır. Tələbə: ana səhifə, profil, jurnal siyahısı + fənn detalı, fənlərim,
  ümumi akademik, nəticələrim, tapşırıqlar; müəllim: ana səhifə, profil, imtahanlarım, jurnal.
* **Sorğu büdcəsi** — hər tələbə bölməsi üçün fraqment ucunun sorğu tavanı (warm keş).

Ölçü (``EMS_FRAGMENT_PERF=1``): hər bölmə üçün ~20 sorğunun orta vaxtı + sorğu sayı,
yığcam və tam rejimdə (hesabat üçün; CI-da işləmir).
"""

from __future__ import annotations

import json
import os
import re
import time
from unittest import mock, skipUnless

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.tests.test_cabinet_shell_query_budget import _LOCMEM, _build_tenant, _client_for
from apps.exams.models import Exam, ExamAttempt
from core.rls import bypass_rls

_CSRF_RE = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+(")')
_NONCE_RE = re.compile(r'(nonce=")[^"]+(")')
#: İmzalı başlama tokeni (``si=``) zaman möhürlüdür — iki render arasında saniyə dəyişə bilər.
_SIGNED_RE = re.compile(r"(si=)[^\"&]+")

#: (aktor, bölmə, əlavə query). ``{enrollment}`` — tələbənin ilk qeydiyyatı.
CASES = (
    ("student", "dashboard", ""),
    ("student", "profile-info", ""),
    ("student", "my-journal", ""),
    ("student", "my-journal", "&subject={enrollment}&period={period}"),
    ("student", "my-subjects", ""),
    ("student", "overall-academic", ""),
    ("student", "my-results", ""),
    ("student", "my-results", "&results_type=exams"),
    ("student", "assigned-exams", ""),
    ("teacher", "dashboard", ""),
    ("teacher", "profile-info", ""),
    ("teacher", "my-exams", ""),
    ("teacher", "my-journal", ""),
)

#: Tələbə bölmələri üçün fraqment sorğu tavanı (warm: badge dəsti + org-switcher keşdə).
#: Ölçülmüş dəyər + 2 ehtiyat; middleware/RLS qatı (~11 ifadə) daxildir.
STUDENT_FRAGMENT_BUDGET = {
    ("dashboard", ""): 22,
    ("profile-info", ""): 32,
    ("my-journal", ""): 22,
    ("my-journal", "&subject={enrollment}&period={period}"): 40,
    ("my-subjects", ""): 46,
    ("overall-academic", ""): 24,
    ("my-results", ""): 31,
    ("assigned-exams", ""): 21,
}


def _normalise(html: str) -> str:
    return _SIGNED_RE.sub(r"\1S", _NONCE_RE.sub(r"\1N\2", _CSRF_RE.sub(r"\1T\2", html)))


def _add_exam_activity(tenant):
    """Tələbəyə təyin olunmuş aktiv imtahan + qiymətləndirilmiş cəhd («Nəticələrim», «Tapşırıqlar»)."""
    with bypass_rls():
        for idx in range(2):
            exam = Exam.objects.create(
                author=tenant["teacher"],
                title=f"Fragment imtahanı {idx}",
                is_active=True,
                is_public=False,
                organization=tenant["org"],
            )
            exam.allowed_users.add(tenant["student"])
            if idx == 0:
                ExamAttempt.objects.create(
                    user=tenant["student"],
                    exam=exam,
                    status="submitted",
                    correct_count=7,
                    wrong_count=3,
                )
    return tenant


class _FragmentMixin:
    def _url(self, section, extra):
        tenant = self.tenant
        query = extra.format(enrollment=tenant["enrollments"][0].id, period=tenant["period"].id)
        return reverse("accounts:profile_section_fragment", args=[section]) + ("?" + query.lstrip("&") if query else "")

    def _get(self, client, section, extra):
        response = client.get(self._url(section, extra), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200, f"{section}{extra}: {response.content[:300]!r}")
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        return payload["html"]


@override_settings(UNIVERSITY_MODE=True, CACHES=_LOCMEM)
class SectionFragmentLeanContextTests(_FragmentMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _add_exam_activity(_build_tenant(slug="lean4", subject_count=4))

    def setUp(self):
        cache.clear()
        self.clients = {actor: _client_for(self.tenant["org"], self.tenant[actor]) for actor in ("student", "teacher")}

    def test_fragment_html_identical_to_full_context(self):
        for actor, section, extra in CASES:
            with self.subTest(actor=actor, section=section, extra=extra):
                client = self.clients[actor]
                lean = self._get(client, section, extra)
                with mock.patch("apps.accounts.views.profile.sections_api.LEAN_FRAGMENT_CONTEXT", False):
                    full = self._get(client, section, extra)
                self.assertGreater(len(lean), 200)
                self.assertEqual(_normalise(lean), _normalise(full))
                dump_dir = os.environ.get("EMS_FRAGMENT_DUMP")
                if dump_dir:
                    os.makedirs(dump_dir, exist_ok=True)
                    name = f"{actor}_{section}{'_detail' if 'subject' in extra else ''}{'_x' if 'results' in extra else ''}"
                    with open(os.path.join(dump_dir, name + ".html"), "w", encoding="utf-8") as fh:
                        fh.write(_normalise(lean))

    def test_student_fragment_query_budget(self):
        client = self.clients["student"]
        for (section, extra), budget in STUDENT_FRAGMENT_BUDGET.items():
            with self.subTest(section=section, extra=extra):
                self._get(client, section, extra)  # isinmə: sessiya möhürü + badge/org-switcher keşi
                with CaptureQueriesContext(connection) as ctx:
                    self._get(client, section, extra)
                count = len(ctx.captured_queries)
                self.assertLessEqual(count, budget, f"{section}{extra}: {count} sorğu > {budget}")

    def test_shell_only_work_is_skipped_for_student_fragments(self):
        """Badge dəsti (cold keşdə ~17 sorğu), bildiriş vəziyyəti və oxunmamış say partial
        oxumursa HEÇ hesablanmır: cold və warm keşdə sorğu sayı eynidir, cədvəllərə toxunulmur."""
        client = self.clients["student"]
        shell_tables = ('"notifications_inappnotification"', '"notifications_studentorganizationrequest"')
        for section in ("dashboard", "my-journal", "my-subjects", "overall-academic", "assigned-exams"):
            with self.subTest(section=section):
                self._get(client, section, "")
                with CaptureQueriesContext(connection) as warm:
                    self._get(client, section, "")
                cache.clear()
                with CaptureQueriesContext(connection) as cold:
                    self._get(client, section, "")
                # Cold fərqi yalnız middleware-in keşlənmiş üzvlük bloku ola bilər (bypass_rls
                # 3 ifadə + Membership); badge dəsti hesablansaydı ~17 sorğu əlavə olunardı.
                extra = len(cold.captured_queries) - len(warm.captured_queries)
                self.assertLessEqual(extra, 4, f"{section}: cold keşdə +{extra} sorğu")
                touched = [q["sql"] for q in cold.captured_queries if any(t in q["sql"] for t in shell_tables)]
                self.assertEqual(touched, [])

    def test_full_page_still_has_shell_counts(self):
        """Tam səhifə yolu dəyişməyib: sidebar badge-ləri və formalar context-dədir."""
        client = self.clients["student"]
        response = client.get(reverse("accounts:profile") + "?section=my-journal")
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["assigned_exams_count"], 2)
        self.assertEqual(ctx["courses_count"], ctx["assigned_courses_count"])
        self.assertIsNotNone(ctx["password_change_form"])
        self.assertIsInstance(ctx["notifications_unread_count"], int)


@skipUnless(os.environ.get("EMS_FRAGMENT_PERF"), "ölçü: EMS_FRAGMENT_PERF=1")
@override_settings(UNIVERSITY_MODE=True, CACHES=_LOCMEM)
class SectionFragmentPerfReport(_FragmentMixin, TestCase):
    ROUNDS = 20

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _add_exam_activity(_build_tenant(slug="leanp", subject_count=6))

    def _measure(self, client, section, extra):
        self._get(client, section, extra)
        with CaptureQueriesContext(connection) as ctx:
            self._get(client, section, extra)
        queries = len(ctx.captured_queries)
        started, cpu_started = time.perf_counter(), time.process_time()
        for _ in range(self.ROUNDS):
            self._get(client, section, extra)
        wall = (time.perf_counter() - started) * 1000 / self.ROUNDS
        # process_time — yalnız app prosesinin CPU-su (DB gözləməsi daxil deyil).
        return queries, wall, (time.process_time() - cpu_started) * 1000 / self.ROUNDS

    def test_report(self):
        lines = []
        for actor, section, extra in CASES:
            client = _client_for(self.tenant["org"], self.tenant[actor])
            with mock.patch("apps.accounts.views.profile.sections_api.LEAN_FRAGMENT_CONTEXT", False):
                fq, fms, fcpu = self._measure(client, section, extra)
            lq, lms, lcpu = self._measure(client, section, extra)
            label = (
                f"{actor}:{section}{' (detal)' if 'subject' in extra else ''}{' (exams)' if 'results' in extra else ''}"
            )
            lines.append(
                f"{label:<30} full {fq:>3} q {fms:6.1f} ms (cpu {fcpu:5.1f}) | lean {lq:>3} q {lms:6.1f} ms (cpu {lcpu:5.1f})"
            )
        print("\n" + "\n".join(lines))
