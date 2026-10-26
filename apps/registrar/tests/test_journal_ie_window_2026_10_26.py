"""Sahib 2026-10-26 — balsız i/e xanası 15 dəqiqədən sonra da dəyişir; q/b və bal kilidli qalır.

«E-jurnalda 15 dəqiqə sonra i/e-ni dəyişmək olmur — onu dəyişmək olsun; qb-ni və balı dəyişmək olmasın.»

Kilidlənən qaydalar:

* pəncərə ərzində hər şey əvvəlki kimidir (q/b → i/e, i/e → bal);
* pəncərədən sonra balsız i/e → q/b / bal YAZILIR (servis, POST, avtomatik yadda saxlama, DB trigger), kilid saatı
  dəyişiklik anından yenidən başlayır; q/b və ballı xana kilidli qalır (409 + «RİM-ə müraciət»);
* köçürülmüş (``entered_by`` boş) i/e dəyişir, eyni dəyərin geri-göndərişi onu «mənimsəmir»; köçürülmüş q/b kilidli;
* i/e dəyişikliyi YENİ qeyd kimidir: dərsin yazma müddəti (7 gün) bitibsə ``LOCK_ENTRY``;
* grid: açıq i/e select-dir (kilid nişanı yox), müddəti bitmiş i/e ``data-jd-lock="entry"``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.registrar import gradebook, journal_edit_windows
from apps.registrar.models import AttendanceStatus, LessonKind, LessonMark
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.rls import bypass_rls

TODAY = timezone.localdate


def _age(mark, minutes):
    LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
    mark.refresh_from_db()
    return mark


class _Base(TestCase):
    prefix = "jie"

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, cls.prefix)
            cls.lesson = gradebook.create_lesson(
                offering=cls.offering, date=TODAY(), created_by=cls.teacher, kind=LessonKind.SEMINAR
            )

    def _save(self, status="present", score=None, lesson=None, enforce_day=True):
        entry = {
            "lesson_id": (lesson or self.lesson).id,
            "enrollment_id": self.enrollment.id,
            "status": status,
            "score": score,
        }
        return gradebook.save_marks(
            offering=self.offering, entries=[entry], by_user=self.teacher, report=True, enforce_day=enforce_day
        )

    def _mark(self, lesson=None):
        return LessonMark.objects.get(lesson=lesson or self.lesson, enrollment=self.enrollment)


class ServiceRuleTest(_Base):
    prefix = "jies"

    def test_lock_reason_by_value(self):
        mark = LessonMark(status=AttendanceStatus.PRESENT, score=None, entered_by_id=1)
        mark.created_at = timezone.now() - timedelta(minutes=60)
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark), "")
        self.assertTrue(gradebook.can_edit_mark(mark))
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark, entry_open=False), journal_edit_windows.LOCK_ENTRY)
        mark.score = Decimal("7")
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark), journal_edit_windows.LOCK_TIME)
        mark.score, mark.status = None, AttendanceStatus.ABSENT
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark), journal_edit_windows.LOCK_TIME)
        mark.status = AttendanceStatus.EXCUSED
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark), journal_edit_windows.LOCK_TIME)
        # Pəncərə ərzində hər dəyər dəyişir — yazma müddəti burada rol oynamır (əvvəlki kimi).
        mark.created_at = timezone.now() - timedelta(minutes=5)
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark, entry_open=False), "")

    def test_within_window_unchanged(self):
        with bypass_rls():
            self._save("absent")
            _age(self._mark(), 14)
            self.assertEqual(self._save("present")["written"], 1)
            _age(self._mark(), 14)
            self.assertEqual(self._save("present", "8")["written"], 1)
            mark = self._mark()
            self.assertEqual((mark.status, mark.score), (AttendanceStatus.PRESENT, Decimal("8")))

    def test_ie_changes_after_window_and_lock_clock_restarts(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), 30)
            result = self._save("absent")
            self.assertEqual(result, {"written": 1, "rejected": 0})
            mark = self._mark()
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)
            self.assertLess(timezone.now() - mark.created_at, timedelta(minutes=1))
            # Yeni q/b öz 15 dəqiqəsində düzəlir, sonra donur.
            self.assertEqual(self._save("present")["written"], 1)
            self.assertEqual(self._save("absent")["written"], 1)
            _age(self._mark(), 16)
            result = self._save("present")
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["locked"], 1)
            self.assertIn("q/b və ya bal 15 dəqiqədən çox əvvəl yazılıb", result["locked_reason"])
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)

    def test_ie_gets_score_after_window(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), 30)
            self.assertEqual(self._save("present", "9")["written"], 1)
            self.assertEqual(self._mark().score, Decimal("9"))

    def test_absent_and_score_stay_locked_after_window(self):
        with bypass_rls():
            self._save("absent")
            _age(self._mark(), 16)
            result = self._save("present")
            self.assertEqual((result["written"], result["locked"]), (0, 1))
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
            LessonMark.objects.filter(pk=self._mark().pk).delete()
            self._save("present", "6")
            _age(self._mark(), 16)
            for status, score in (("present", ""), ("present", "7"), ("absent", None)):
                result = self._save(status, score)
                self.assertEqual((result["written"], result["locked"]), (0, 1))
            mark = self._mark()
            self.assertEqual((mark.status, mark.score), (AttendanceStatus.PRESENT, Decimal("6")))

    def test_legacy_ie_changes_legacy_absent_stays_locked(self):
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson=self.lesson, enrollment=self.enrollment, status=AttendanceStatus.PRESENT
            )
            # Eyni dəyərin geri-göndərişi köçürülmüş xananı «mənimsəmir».
            self._save("present")
            self.assertIsNone(self._mark().entered_by_id)
            self.assertEqual(self._save("absent")["written"], 1)
            mark = self._mark()
            self.assertEqual((mark.status, mark.entered_by_id), (AttendanceStatus.ABSENT, self.teacher.pk))
            mark.delete()
            LessonMark.objects.create(
                organization=self.org, lesson=self.lesson, enrollment=self.enrollment, status=AttendanceStatus.ABSENT
            )
            self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark()), journal_edit_windows.LOCK_LEGACY)
            result = self._save("present")
            self.assertEqual(result["written"], 0)
            self.assertIn("köhnə sistemdən köçürülüb", result["locked_reason"])

    def test_ie_on_lesson_past_write_period_is_locked(self):
        with bypass_rls():
            old = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=8), created_by=self.teacher, allow_past=True
            )
            self._save("present", lesson=old, enforce_day=False)
            _age(self._mark(old), 30)
            result = self._save("absent", lesson=old)
            self.assertEqual((result["written"], result["locked"]), (0, 1))
            self.assertIn("yazma müddəti bitib", result["locked_reason"])
            self.assertEqual(self._mark(old).status, AttendanceStatus.PRESENT)
            journal = gradebook.get_offering_journal(offering=self.offering)
            cells = {cell["lesson"].pk: cell for cell in journal["rows"][0]["cells"]}
            self.assertEqual(cells[old.pk]["lock_reason"], journal_edit_windows.LOCK_ENTRY)
            self.assertFalse(cells[old.pk]["writable"])

    def test_grid_ie_writable_absent_locked(self):
        with bypass_rls():
            second = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=2), created_by=self.teacher
            )
            self._save("present")
            self._save("absent", lesson=second)
            _age(self._mark(), 30)
            _age(self._mark(second), 30)
            journal = gradebook.get_offering_journal(offering=self.offering)
            cells = {cell["lesson"].pk: cell for cell in journal["rows"][0]["cells"]}
            ie = cells[self.lesson.pk]
            self.assertEqual((ie["locked"], ie["writable"], ie["lock_reason"]), (False, True, ""))
            qb = cells[second.pk]
            self.assertEqual((qb["locked"], qb["writable"], qb["lock_reason"]), (True, False, "time"))


class TriggerTest(_Base):
    prefix = "jiet"

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")

    def test_trigger_allows_ie_blocks_absent_and_score(self):
        with bypass_rls():
            self._save("present")
            mark = _age(self._mark(), 60)
            with transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.ABSENT)
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
            # İndi q/b — köhnə yazılış saatı ilə donub.
            with self.assertRaises(InternalError), transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
            with transaction.atomic(), self._unlock():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT, score=Decimal("5"))
            with self.assertRaises(InternalError), transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(score=Decimal("6"))
            self.assertEqual(self._mark().score, Decimal("5"))

    def test_trigger_allows_legacy_ie(self):
        with bypass_rls():
            mark = LessonMark.objects.create(
                organization=self.org, lesson=self.lesson, enrollment=self.enrollment, status=AttendanceStatus.PRESENT
            )
            _age(mark, 60 * 24 * 30)
            with transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(score=Decimal("4"))
            self.assertEqual(self._mark().score, Decimal("4"))

    @staticmethod
    def _unlock():
        from core.rls import journal_unlock

        return journal_unlock()


class HttpTest(_Base):
    prefix = "jieh"

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post(self, client, status, score="", **extra):
        data = {
            "action": "save_marks",
            f"att__{self.lesson.id}__{self.enrollment.id}": status,
            f"score__{self.lesson.id}__{self.enrollment.id}": score,
        }
        data.update(extra)
        return client.post(reverse("registrar:journal_detail", args=[self.offering.id]), data)

    def test_autosave_and_post_change_ie_after_window(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), 30)
        client = self._client()
        resp = self._post(client, "absent", autosave="1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["written"], 1)
        with bypass_rls():
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
            LessonMark.objects.filter(pk=self._mark().pk).update(status=AttendanceStatus.PRESENT)
            _age(self._mark(), 30)
        resp = self._post(client, "present", score="8")  # adi «Yadda saxla»
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(self._mark().score, Decimal("8"))

    def test_autosave_refuses_absent_after_window(self):
        with bypass_rls():
            self._save("absent")
            _age(self._mark(), 30)
        resp = self._post(self._client(), "present", autosave="1")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "mark_locked")
        with bypass_rls():
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)

    def test_page_renders_ie_as_select_and_entry_dialog_text(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), 30)
        html = self._client().get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn(f'name="att__{self.lesson.id}__{self.enrollment.id}"', html)
        self.assertNotIn('data-jd-lock="time"', html)
        self.assertIn("data-jd-lock-msg-entry=", html)
