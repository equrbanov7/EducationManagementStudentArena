"""Sahib 2026-10-14 — jurnal UX: avtomatik yadda saxlama, yaşıl «Bu günün cədvəl dərsləri» zolağı yoxdur.

Nəyi qoruyur
------------
* ``autosave=1`` POST MÖVCUD ünvana gedir (``save_marks`` / ``kollokvium_save``) və eyni qaydalardan
  keçir — fərq yalnız cavabdadır: redirect + flash əvəzinə JSON, sessiyaya mesaj yığılmır;
* kilidli jurnal / bağlı Midterm pəncərəsi → 409 JSON (yazı yoxdur); başqa müəllim → 404 (dəyişməyib);
* dərs günü qaydası: keçmiş dərsə YENİ işarə yazılmır, cavabda ``skipped`` sayılır;
* təkrar göndəriş (beacon + fetch) dublikat yaratmır — eyni xana bir sətirdir;
* jurnal səhifəsində forma ``data-jd-autosave`` + vəziyyət mətni + skript yüklənir; düzəliş rejimində yox.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.registrar import gradebook, journal_extras
from apps.registrar.models import (
    ApprovalStatus,
    AssessmentScheme,
    AttendanceStatus,
    ComponentScore,
    KollokviumWindow,
    LessonKind,
    LessonMark,
)
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.rls import bypass_rls


class JournalAutosaveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jas")
            cls.lesson = gradebook.create_lesson(
                allow_past=True, offering=cls.offering, date=timezone.localdate(), kind=LessonKind.SEMINAR
            )
            cls.old_lesson = gradebook.create_lesson(
                allow_past=True,
                offering=cls.offering,
                date=timezone.localdate() - datetime.timedelta(days=7),
                kind=LessonKind.LECTURE,
            )

    def _client(self, user=None):
        client = Client()
        client.force_login(user or self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _url(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])

    def _marks(self, lesson=None):
        with bypass_rls():
            return list(LessonMark.objects.filter(lesson=lesson or self.lesson, enrollment=self.enrollment))

    def _autosave(self, client=None, **cells):
        data = {"action": "save_marks", "autosave": "1"}
        data.update(cells)
        return (client or self._client()).post(self._url(), data)

    def test_autosave_writes_through_save_marks_and_answers_json_without_flash(self):
        client = self._client()
        key = f"att__{self.lesson.id}__{self.enrollment.id}"
        resp = self._autosave(client, **{key: "absent", f"score__{self.lesson.id}__{self.enrollment.id}": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertEqual(
            resp.json(), {"ok": True, "sent": 1, "written": 1, "rejected": 0, "skipped": 0, "blocked": False}
        )
        (mark,) = self._marks()
        self.assertEqual(mark.status, AttendanceStatus.ABSENT)
        self.assertEqual(mark.entered_by_id, self.teacher.pk)
        self.assertEqual(list(get_messages(resp.wsgi_request)), [])  # növbəti səhifədə «yadda saxlanıldı» çıxmır

    def test_repeated_autosave_never_duplicates_a_cell(self):
        client = self._client()
        score = f"score__{self.lesson.id}__{self.enrollment.id}"
        att = f"att__{self.lesson.id}__{self.enrollment.id}"
        for _ in range(3):  # beacon + fetch + əl ilə «Yadda saxla» eyni xananı göndərə bilər
            self._autosave(client, **{att: "present", score: "8"})
        (mark,) = self._marks()
        self.assertEqual((mark.status, mark.score), (AttendanceStatus.PRESENT, Decimal("8")))

    def test_server_rules_still_apply_and_skips_are_reported(self):
        resp = self._autosave(
            **{
                f"att__{self.old_lesson.id}__{self.enrollment.id}": "absent",  # keçmiş dərs — yeni işarə yox
                f"att__{self.lesson.id}__{self.enrollment.id}": "present",
                f"score__{self.lesson.id}__{self.enrollment.id}": "15",  # 0–10 xaricində — rədd
            }
        )
        body = resp.json()
        self.assertEqual((body["sent"], body["written"], body["rejected"], body["skipped"]), (2, 0, 1, 1))
        self.assertEqual(self._marks(self.old_lesson), [])
        self.assertEqual(self._marks(), [])

    def test_locked_journal_refuses_with_409_json(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )
        resp = self._autosave(**{f"att__{self.lesson.id}__{self.enrollment.id}": "absent"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "locked")
        self.assertIn("Jurnal bağlıdır", resp.json()["message"])
        self.assertEqual(self._marks(), [])

    def test_other_teacher_cannot_autosave(self):
        from django.contrib.auth import get_user_model

        with bypass_rls():
            stranger = get_user_model().objects.create_user("jas_stranger", "jas_stranger@qku.edu.az", "pw")
        resp = self._autosave(self._client(stranger), **{f"att__{self.lesson.id}__{self.enrollment.id}": "absent"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self._marks(), [])

    def test_manual_save_keeps_the_redirect_and_flash(self):
        resp = self._client().post(
            self._url(), {"action": "save_marks", f"att__{self.lesson.id}__{self.enrollment.id}": "present"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(any("yadda saxlanıldı" in str(m) for m in get_messages(resp.wsgi_request)))

    def test_journal_page_wires_autosave_and_has_no_today_strip(self):
        resp = self._client().get(self._url())
        self.assertContains(resp, "data-jd-autosave ")
        self.assertContains(resp, f'data-jd-autosave-url="{self._url()}"')
        self.assertContains(resp, "data-jd-autosave-status")
        self.assertContains(resp, "registrar/js/journal_grid_autosave.js")
        self.assertContains(resp, "registrar/css/journal_autosave.css")
        self.assertContains(resp, "Yadda saxla")  # əl ilə düymə ehtiyat yol kimi qalır
        self.assertNotContains(resp, 'class="jd2-today"')
        self.assertNotIn("today_strip", resp.context)


class MidtermAutosaveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jasm")

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post(self, score):
        with bypass_rls():
            midterm = journal_extras.ensure_kollokviums(self.offering)[0]
        url = reverse("registrar:journal_kollokvium_save", args=[self.offering.id])
        resp = self._client().post(url, {"autosave": "1", f"kscore__{midterm.id}__{self.enrollment.id}": score})
        return midterm, resp

    def test_open_window_autosaves_midterm_as_json(self):
        today = timezone.localdate()
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=today - datetime.timedelta(days=1),
                closes_on=today + datetime.timedelta(days=5),
                is_active=True,
            )
        midterm, resp = self._post("18")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["written"], 1)
        with bypass_rls():
            self.assertEqual(
                ComponentScore.objects.get(component=midterm, enrollment=self.enrollment).score, Decimal("18")
            )
        page = self._client().get(reverse("registrar:journal_detail", args=[self.offering.id]), {"jt": "kollokvium"})
        self.assertContains(page, "data-jd-autosave ")
        self.assertContains(page, "data-jd-autosave-status")

    def test_closed_window_refuses_with_409_json(self):
        midterm, resp = self._post("18")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "window_closed")
        with bypass_rls():
            self.assertFalse(ComponentScore.objects.filter(component=midterm).exists())
