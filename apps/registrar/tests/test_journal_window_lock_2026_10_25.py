"""Sahib 2026-10-25 — 7 günlük yazma pəncərəsi + 15 dəqiqəlik xana kilidi.

«1 həftəlik aktiv saxlayacağıq ki, müəllim keçən həftədə datanı yazmadıqlarını yaza bilsin … müəllim kiməsə q/b
və ya bal yazıbsa, yazdığından 15 dəqiqə sonra onu geri dəyişə bilməsin, olduğu kimi qalsın. Bunun üçün RİM-ə
müraciət edib təqdimat yazmaq lazım olduğunu qeyd etsin.»

Kilidlənən qaydalar:

* defoltlar: ``journal.late_entry_days`` = 7, ``journal.mark_edit_minutes`` = 15 (servis + DB trigger);
* pəncərə sərhədləri: 7 gün əvvəlki dərs açılır və yazılır, 8 gün əvvəlki yox; gələcək tarix olmaz;
* kilid İLK yazılışdan sayılır (14 dəq. — dəyişir, 16 dəq. — yox; sonrakı düzəliş saatı uzatmır);
* köçürülmüş xana (``entered_by`` boş) həmişə kilidlidir; dəyişməyən geri-göndəriş kilid sayılmır;
* avtomatik yadda saxlama kilidli xanaya dəyişikliyə 409 + «RİM-ə müraciət» mətni qaytarır;
* sistem yazısı (``journal_unlock`` — midterm/imtahan sinxronu, rəsmi düzəliş) kilidə tabe deyil;
* grid: kilidli xana yalnız-oxu + ``data-jd-lock``; boş xana pəncərədə yazıla bilən (toplu doldurma kilidliyə
  toxunmur — kilidli xana select deyil, server də yazmır).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.registrar import gradebook, journal_edit_windows
from apps.registrar.models import AttendanceStatus, ComponentScore, LessonKind, LessonMark
from apps.registrar.tests.test_journal_rules import _setup_offering
from core import runtime_settings as rs
from core.rls import bypass_rls, journal_unlock

TODAY = timezone.localdate


def _age(mark, minutes):
    LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
    mark.refresh_from_db()
    return mark


class DefaultsTest(TestCase):
    def test_defaults_are_seven_days_and_fifteen_minutes(self):
        self.assertEqual(rs.SPECS["journal.late_entry_days"].default(), 7)
        self.assertEqual(rs.SPECS["journal.mark_edit_minutes"].default(), 15)
        self.assertEqual(journal_edit_windows.late_entry_days(), 7)
        self.assertEqual(journal_edit_windows.mark_edit_window(), timedelta(minutes=15))
        ctx = journal_edit_windows.template_context(TODAY())
        self.assertEqual(ctx["lesson_date_min"], TODAY() - timedelta(days=7))
        self.assertEqual(ctx["lesson_date_max"], TODAY())
        self.assertIn("15 dəqiqədən çox əvvəl yazılıb", ctx["mark_lock_messages"]["time"])
        self.assertIn("RİM-ə müraciət edib təqdimat yazın", ctx["mark_lock_messages"]["legacy"])
        self.assertIn("section=applications&new_kind=texniki", ctx["mark_lock_request_url"])

    def test_lock_message_matches_owner_wording(self):
        self.assertEqual(
            journal_edit_windows.lock_message(journal_edit_windows.LOCK_TIME, window=timedelta(minutes=15)),
            "Bu qiymət 15 dəqiqədən çox əvvəl yazılıb və dəyişdirilə bilməz. Dəyişiklik üçün RİM-ə müraciət edib "
            "təqdimat yazın.",
        )


class WriteWindowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jww")

    def _mark(self, lesson, status="absent"):
        entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": status}
        return gradebook.save_marks(offering=self.offering, entries=[entry], by_user=self.teacher, report=True)

    def test_seven_days_back_is_open_eight_is_closed(self):
        with bypass_rls():
            week = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=7), created_by=self.teacher
            )
            self.assertEqual(self._mark(week), {"written": 1, "rejected": 0})
            with self.assertRaisesMessage(gradebook.LessonRuleError, "ən çox 7 gün geriyə"):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - timedelta(days=8), created_by=self.teacher
                )
            old = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=8), created_by=self.teacher, allow_past=True
            )
            result = self._mark(old)
            self.assertEqual(result["written"], 0)
            self.assertIn("7 gündən çox keçib", result["blocked_reason"])
            journal = gradebook.get_offering_journal(offering=self.offering)
            markable = {meta["lesson"].pk: meta["markable"] for meta in journal["lesson_meta"]}
            self.assertEqual(markable, {week.pk: True, old.pk: False})

    def test_future_date_is_refused_for_teacher(self):
        with bypass_rls():
            with self.assertRaisesMessage(gradebook.LessonRuleError, "Gələcək tarixə dərs əlavə etmək olmaz."):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() + timedelta(days=1), created_by=self.teacher
                )
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=lesson, date=TODAY() + timedelta(days=2))
            # RİM/İKT override (allow_past) gələcək dərsi aça bilər, amma ona qeyd hələ yazılmır.
            future = gradebook.create_lesson(
                offering=self.offering, date=TODAY() + timedelta(days=1), created_by=self.teacher, allow_past=True
            )
            self.assertEqual(self._mark(future)["written"], 0)

    @override_settings(JOURNAL_LATE_ENTRY_DAYS=0)
    def test_zero_keeps_lesson_day_rule(self):
        self.assertEqual(
            journal_edit_windows.lesson_date_error(TODAY() - timedelta(days=1)), "Keçmiş tarixə dərs əlavə etmək olmaz."
        )
        self.assertEqual(journal_edit_windows.lesson_date_error(TODAY()), "")


class MarkLockTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jml")
            cls.lesson = gradebook.create_lesson(
                offering=cls.offering, date=TODAY(), created_by=cls.teacher, kind=LessonKind.SEMINAR
            )

    def _save(self, status="present", score=None):
        entry = {"lesson_id": self.lesson.id, "enrollment_id": self.enrollment.id, "status": status, "score": score}
        return gradebook.save_marks(offering=self.offering, entries=[entry], by_user=self.teacher, report=True)

    def _mark(self):
        return LessonMark.objects.get(lesson=self.lesson, enrollment=self.enrollment)

    def test_changeable_within_fifteen_minutes(self):
        with bypass_rls():
            self._save("absent")
            _age(self._mark(), 14)
            self.assertEqual(self._save("present", "8")["written"], 1)
            mark = self._mark()
            self.assertEqual((mark.status, mark.score), (AttendanceStatus.PRESENT, Decimal("8")))

    def test_locked_after_fifteen_minutes_from_first_write(self):
        with bypass_rls():
            self._save("absent")
            created = self._mark().created_at
            self._save("present", "7")  # 2-ci yazı — kilid saatı uzanmır
            self.assertEqual(self._mark().created_at, created)
            _age(self._mark(), 16)
            result = self._save("present", "9")
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["locked"], 1)
            self.assertIn("15 dəqiqədən çox əvvəl yazılıb", result["locked_reason"])
            self.assertEqual(self._mark().score, Decimal("7"))

    def test_unchanged_resubmission_is_not_a_lock_error(self):
        with bypass_rls():
            self._save("present", "7")
            _age(self._mark(), 60)
            result = self._save("present", "7")
            self.assertEqual(result, {"written": 0, "rejected": 0})

    def test_legacy_cell_is_always_locked(self):
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson=self.lesson, enrollment=self.enrollment, status=AttendanceStatus.ABSENT
            )  # entered_by boş — köçürülmüş xana, YENİ yaranıb (vaxt kilidi hələ yoxdur)
            mark = self._mark()
            self.assertEqual(journal_edit_windows.mark_lock_reason(mark), journal_edit_windows.LOCK_LEGACY)
            self.assertFalse(gradebook.can_edit_mark(mark))
            result = self._save("present")
            self.assertEqual(result["written"], 0)
            self.assertIn("köhnə sistemdən köçürülüb", result["locked_reason"])
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)

    def test_grid_marks_locked_cells_and_keeps_empty_cells_writable(self):
        with bypass_rls():
            second = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=3), created_by=self.teacher
            )
            self._save("absent")
            _age(self._mark(), 30)
            journal = gradebook.get_offering_journal(offering=self.offering)
            cells = {cell["lesson"].pk: cell for cell in journal["rows"][0]["cells"]}
            locked = cells[self.lesson.pk]
            self.assertTrue(locked["locked"])
            self.assertFalse(locked["writable"])  # toplu doldurma select görmür → toxunmur
            self.assertEqual(locked["lock_reason"], journal_edit_windows.LOCK_TIME)
            empty = cells[second.pk]
            self.assertTrue(empty["writable"])
            self.assertEqual(empty["lock_reason"], "")

    def test_db_trigger_default_is_fifteen_minutes_and_unlock_is_exempt(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        with bypass_rls():
            self._save("absent")
            mark = _age(self._mark(), 20)
            with self.assertRaises(InternalError), transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
            # Sistem yazısı (midterm/imtahan sinxronu, sənədli düzəliş) rəsmi yoldan keçir.
            with transaction.atomic(), journal_unlock():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
            self.assertEqual(self._mark().status, AttendanceStatus.PRESENT)

    def test_component_score_trigger_same_window_system_sync_exempt(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        from apps.registrar.models import AssessmentComponent

        with bypass_rls():
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", max_score=Decimal("30")
            )
            row = ComponentScore.objects.create(
                organization=self.org, component=component, enrollment=self.enrollment, score=Decimal("10")
            )
            ComponentScore.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=20))
            with self.assertRaises(InternalError), transaction.atomic():
                ComponentScore.objects.filter(pk=row.pk).update(score=Decimal("12"))
            with transaction.atomic(), journal_unlock():
                ComponentScore.objects.filter(pk=row.pk).update(score=Decimal("12"))


class AutosaveLockTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jma")
            cls.lesson = gradebook.create_lesson(
                offering=cls.offering, date=TODAY(), created_by=cls.teacher, kind=LessonKind.SEMINAR
            )

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post(self, client, **extra):
        key = f"att__{self.lesson.id}__{self.enrollment.id}"
        data = {"action": "save_marks", key: "absent", f"score__{self.lesson.id}__{self.enrollment.id}": ""}
        data.update(extra)
        return client.post(reverse("registrar:journal_detail", args=[self.offering.id]), data)

    def test_autosave_on_locked_cell_answers_409_with_rim_message(self):
        with bypass_rls():
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": self.lesson.id, "enrollment_id": self.enrollment.id, "status": "present"}],
                by_user=self.teacher,
            )
            _age(LessonMark.objects.get(lesson=self.lesson), 16)
        client = self._client()
        resp = self._post(client, autosave="1")
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["code"], "mark_locked")
        self.assertIn("RİM-ə müraciət edib təqdimat yazın", body["message"])
        # Adi «Yadda saxla» — yazı yoxdur, xəbərdarlıq mesajı.
        resp = self._post(client)
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=self.lesson).status, AttendanceStatus.PRESENT)

    def test_page_renders_lock_marker_and_dialog_texts(self):
        with bypass_rls():
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": self.lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            _age(LessonMark.objects.get(lesson=self.lesson), 16)
        html = self._client().get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn('data-jd-lock="time"', html)
        self.assertIn("jd2-ro--locked", html)
        self.assertIn("data-jd-lock-msg-time=", html)
        self.assertIn("registrar/js/journal_mark_lock.js", html)
        self.assertIn("registrar/css/journal_mark_lock.css", html)
