"""Sahib 2026-11-21 (RİM rəhbəri) — i/e xanası 1 gün ərzində dəyişir, sonra q/b kimi donur.

«i/e qoyulandan sonra 1 gün ərzində müəllim onu dəyişə bilsin, sonra q/b kimi donsun; q/b və bal yazılandan 15 dəqiqə
sonra donur; əvvəlki olanlarda elə donsun; boş xanalara yazmaq olsun; hamısını sistem tənzimləmələrindən idarə edim.»

Kilidlənən qaydalar:

* i/e müddət (defolt 1440 dəqiqə) ərzində dəyişir, sonra ``LOCK_PRESENCE`` (servis, grid, DB trigger-i 0125);
* köçürülmüş (``entered_by`` boş) i/e də eyni saatla — köhnələr donub;
* ``journal.presence_lock_enabled`` söndürülüdə 2026-10-26 qaydası (i/e həmişə dəyişir) — servis və trigger;
* q/b və bal 15 dəqiqəlik kilidi dəyişməyib; boş xanaya (əvvəlki dərsdə də) yazmaq olur;
* açarlar «Sistem tənzimləmələri» → «Elektron jurnal»da, ``journal.mark_edit_minutes``-in ardınca.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.registrar import gradebook, journal_edit_windows
from apps.registrar.models import AttendanceStatus, LessonKind, LessonMark
from apps.registrar.tests.test_journal_rules import _setup_offering
from core import runtime_settings as rs
from core.rls import bypass_rls, journal_unlock

TODAY = timezone.localdate
DAY = 24 * 60
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "presence-window"}}


def _age(mark, minutes):
    """``created_at``-ı geri çəkir (köhnə, artıq donmuş sətir də — trigger-i rəsmi yolla keçir)."""
    with transaction.atomic(), journal_unlock():
        LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
    mark.refresh_from_db()
    return mark


class _Base(TestCase):
    prefix = "pew"

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

    def _legacy_ie(self, lesson=None):
        return LessonMark.objects.create(
            organization=self.org,
            lesson=lesson or self.lesson,
            enrollment=self.enrollment,
            status=AttendanceStatus.PRESENT,
        )

    def _cells(self):
        journal = gradebook.get_offering_journal(offering=self.offering)
        return {cell["lesson"].pk: cell for cell in journal["rows"][0]["cells"]}


class LockReasonTest(TestCase):
    def _mark(self, minutes, *, entered_by=1, status=AttendanceStatus.PRESENT, score=None):
        mark = LessonMark(status=status, score=score, entered_by_id=entered_by)
        mark.created_at = timezone.now() - timedelta(minutes=minutes)
        return mark

    def test_default_window_is_one_day(self):
        self.assertEqual(journal_edit_windows.presence_edit_window(), timedelta(minutes=DAY))
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(DAY - 5)), "")
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(DAY + 1)), journal_edit_windows.LOCK_PRESENCE)
        self.assertFalse(gradebook.can_edit_mark(self._mark(DAY + 1)))

    def test_legacy_ie_follows_window(self):
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(30, entered_by=None)), "")
        self.assertEqual(
            journal_edit_windows.mark_lock_reason(self._mark(DAY + 1, entered_by=None)),
            journal_edit_windows.LOCK_PRESENCE,
        )

    def test_qb_and_score_keep_15_minute_lock(self):
        for status, score in ((AttendanceStatus.ABSENT, None), (AttendanceStatus.PRESENT, Decimal("7"))):
            self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(14, status=status, score=score)), "")
            self.assertEqual(
                journal_edit_windows.mark_lock_reason(self._mark(16, status=status, score=score)),
                journal_edit_windows.LOCK_TIME,
            )
        self.assertEqual(
            journal_edit_windows.mark_lock_reason(self._mark(16, entered_by=None, status=AttendanceStatus.ABSENT)),
            journal_edit_windows.LOCK_LEGACY,
        )

    def test_write_period_still_applies_inside_window(self):
        mark = self._mark(60)
        self.assertEqual(journal_edit_windows.mark_lock_reason(mark, entry_open=False), journal_edit_windows.LOCK_ENTRY)

    @override_settings(JOURNAL_PRESENCE_LOCK_ENABLED=False)
    def test_toggle_off_restores_old_rule(self):
        self.assertIsNone(journal_edit_windows.presence_edit_window())
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(DAY * 30)), "")
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(DAY * 30, entered_by=None)), "")
        self.assertEqual(
            journal_edit_windows.mark_lock_reason(self._mark(DAY * 30), entry_open=False),
            journal_edit_windows.LOCK_ENTRY,
        )

    @override_settings(JOURNAL_PRESENCE_EDIT_MINUTES=5)
    def test_presence_window_shorter_than_mark_window_wins(self):
        self.assertEqual(journal_edit_windows.mark_lock_reason(self._mark(10)), journal_edit_windows.LOCK_PRESENCE)

    def test_lock_message(self):
        text = journal_edit_windows.lock_message(journal_edit_windows.LOCK_PRESENCE)
        self.assertIn("i/e qeydi yazılandan 24 saat keçib", text)
        self.assertIn("RİM-ə müraciət edib təqdimat yazın", text)
        ctx = journal_edit_windows.template_context()
        self.assertEqual(ctx["mark_lock_messages"][journal_edit_windows.LOCK_PRESENCE], text)
        self.assertEqual(ctx["presence_edit_window_label"], "24 saat")
        with override_settings(JOURNAL_PRESENCE_LOCK_ENABLED=False):
            self.assertEqual(journal_edit_windows.template_context()["presence_edit_window_label"], "")


class ServiceTest(_Base):
    prefix = "pews"

    def test_ie_editable_inside_window_and_new_qb_gets_15_minutes(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), DAY - 30)
            self.assertEqual(self._save("absent"), {"written": 1, "rejected": 0})
            mark = self._mark()
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)
            self.assertLess(timezone.now() - mark.created_at, timedelta(minutes=1))
            _age(mark, 16)
            result = self._save("present")
            self.assertEqual((result["written"], result["locked"]), (0, 1))
            self.assertIn("q/b və ya bal 15 dəqiqədən çox əvvəl yazılıb", result["locked_reason"])

    def test_ie_frozen_after_window(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), DAY + 1)
            for status, score in (("absent", None), ("present", "8")):
                result = self._save(status, score)
                self.assertEqual((result["written"], result["locked"]), (0, 1))
                self.assertIn("i/e qeydi yazılandan 24 saat keçib", result["locked_reason"])
            mark = self._mark()
            self.assertEqual((mark.status, mark.score), (AttendanceStatus.PRESENT, None))
            # Grid-in geri göndərdiyi eyni dəyər kilid sayılmır.
            result = self._save("present")
            self.assertEqual((result["written"], result.get("locked", 0)), (0, 0))
            cell = self._cells()[self.lesson.pk]
            self.assertEqual((cell["locked"], cell["writable"], cell["lock_reason"]), (True, False, "presence"))

    def test_legacy_ie_follows_window(self):
        with bypass_rls():
            self._legacy_ie()
            self.assertEqual(self._save("absent")["written"], 1)  # təzə köçürülmüş — müddət ərzində
            self._mark().delete()
            _age(self._legacy_ie(), DAY * 30)
            result = self._save("absent")
            self.assertEqual((result["written"], result["locked"]), (0, 1))
            self.assertIsNone(self._mark().entered_by_id)
            self.assertEqual(self._cells()[self.lesson.pk]["lock_reason"], journal_edit_windows.LOCK_PRESENCE)

    @override_settings(JOURNAL_PRESENCE_LOCK_ENABLED=False)
    def test_toggle_off_ie_changes_any_time(self):
        # Servis ``settings``-dən (testdə runtime oxu söndürülüdür), trigger bazadakı sətirdən oxuyur — ikisi də söndürülü.
        RuntimeSetting.objects.create(key="journal.presence_lock_enabled", value=False)
        with bypass_rls():
            _age(self._legacy_ie(), DAY * 30)
            self.assertEqual(self._save("absent")["written"], 1)
            mark = self._mark()
            self.assertEqual((mark.status, mark.entered_by_id), (AttendanceStatus.ABSENT, self.teacher.pk))

    def test_qb_and_score_15_minute_lock_unchanged(self):
        with bypass_rls():
            self._save("absent")
            _age(self._mark(), 14)
            self.assertEqual(self._save("present", "6")["written"], 1)
            _age(self._mark(), 16)
            for status, score in (("present", ""), ("absent", None), ("present", "9")):
                result = self._save(status, score)
                self.assertEqual((result["written"], result["locked"]), (0, 1))
            self.assertEqual(self._mark().score, Decimal("6"))

    def test_empty_cell_in_earlier_lesson_still_writable(self):
        with bypass_rls():
            earlier = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=3), created_by=self.teacher
            )
            self._save("present")
            _age(self._mark(), DAY * 2)  # bu günün i/e-si donub — qonşu boş xanaya təsiri yoxdur
            self.assertTrue(self._cells()[earlier.pk]["writable"])
            self.assertEqual(self._save("absent", lesson=earlier)["written"], 1)
            self.assertEqual(self._mark(earlier).status, AttendanceStatus.ABSENT)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class RuntimeSettingsTest(TestCase):
    def setUp(self):
        RuntimeSetting.objects.filter(key__startswith="journal.presence").delete()
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def test_registry_order_and_admin_page(self):
        keys = list(rs.SPECS)
        anchor = keys.index("journal.mark_edit_minutes")
        self.assertEqual(
            keys[anchor + 1 : anchor + 3], ["journal.presence_lock_enabled", "journal.presence_edit_minutes"]
        )
        lock, minutes = rs.SPECS["journal.presence_lock_enabled"], rs.SPECS["journal.presence_edit_minutes"]
        self.assertEqual((lock.group, lock.kind, lock.default()), ("journal", "bool", True))
        self.assertEqual((minutes.group, minutes.kind, minutes.default(), minutes.min), ("journal", "int", 1440, 1))
        self.assertIn("q/b və bal", str(rs.SPECS["journal.mark_edit_minutes"].label))
        groups = {group["key"]: group for group in runtime_settings_admin.describe()}
        shown = [field["key"] for field in groups["journal"]["fields"]]
        self.assertIn("journal.presence_lock_enabled", shown)
        self.assertIn("journal.presence_edit_minutes", shown)

    def test_stored_values_drive_window(self):
        RuntimeSetting.objects.create(key="journal.presence_edit_minutes", value=120)
        rs.invalidate()
        self.assertEqual(journal_edit_windows.presence_edit_window(), timedelta(minutes=120))
        RuntimeSetting.objects.create(key="journal.presence_lock_enabled", value=False)
        rs.invalidate()
        self.assertIsNone(journal_edit_windows.presence_edit_window())


class TriggerTest(_Base):
    prefix = "pewt"

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")

    def _update(self, mark, **fields):
        with transaction.atomic():
            LessonMark.objects.filter(pk=mark.pk).update(**fields)

    def _blocked(self, mark, **fields):
        with self.assertRaises(InternalError), transaction.atomic():
            LessonMark.objects.filter(pk=mark.pk).update(**fields)

    def test_ie_inside_window_allowed_after_window_blocked(self):
        with bypass_rls():
            self._save("present")
            mark = _age(self._mark(), DAY - 30)
            self._update(mark, status=AttendanceStatus.ABSENT)
            self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
            # İndi q/b — köhnə yazılış saatı ilə (15 dəqiqə) donub.
            self._blocked(mark, status=AttendanceStatus.PRESENT)
            with transaction.atomic(), journal_unlock():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
            mark = _age(mark, DAY + 1)
            self._blocked(mark, status=AttendanceStatus.ABSENT)
            self._blocked(mark, score=Decimal("4"))
            self.assertEqual((self._mark().status, self._mark().score), (AttendanceStatus.PRESENT, None))

    def test_legacy_ie_blocked_after_window(self):
        with bypass_rls():
            mark = _age(self._legacy_ie(), DAY * 30)
            self._blocked(mark, score=Decimal("4"))
            with transaction.atomic(), journal_unlock():  # RİM rəsmi düzəlişi / data bərpası
                LessonMark.objects.filter(pk=mark.pk).update(score=Decimal("4"))
            self.assertEqual(self._mark().score, Decimal("4"))

    def test_toggle_off_allows_old_ie(self):
        with bypass_rls():
            mark = _age(self._legacy_ie(), DAY * 30)
            RuntimeSetting.objects.create(key="journal.presence_lock_enabled", value=False)
            self._update(mark, score=Decimal("4"))
            self.assertEqual(self._mark().score, Decimal("4"))

    def test_stored_minutes_used(self):
        with bypass_rls():
            RuntimeSetting.objects.create(key="journal.presence_edit_minutes", value=60)
            mark = _age(self._legacy_ie(), 59)
            self._update(mark, updated_at=timezone.now())
            mark = _age(mark, 61)
            self._blocked(mark, status=AttendanceStatus.ABSENT)

    def test_qb_lock_unchanged(self):
        with bypass_rls():
            self._save("absent")
            mark = _age(self._mark(), 14)
            self._update(mark, updated_at=timezone.now())
            mark = _age(mark, 16)
            self._blocked(mark, status=AttendanceStatus.PRESENT)


class HttpTest(_Base):
    prefix = "pewh"

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_frozen_ie_renders_locked_and_autosave_refuses(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), DAY + 1)
        client = self._client()
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        html = client.get(url).content.decode()
        self.assertIn('data-jd-lock="presence"', html)
        self.assertIn("data-jd-lock-msg-presence=", html)
        self.assertNotIn(f'name="att__{self.lesson.id}__{self.enrollment.id}"', html)
        resp = client.post(
            url,
            {
                "action": "save_marks",
                "autosave": "1",
                f"att__{self.lesson.id}__{self.enrollment.id}": "absent",
                f"score__{self.lesson.id}__{self.enrollment.id}": "",
            },
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "mark_locked")
        with bypass_rls():
            self.assertEqual(self._mark().status, AttendanceStatus.PRESENT)

    def test_ie_inside_window_is_select(self):
        with bypass_rls():
            self._save("present")
            _age(self._mark(), DAY - 60)
        html = self._client().get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn(f'name="att__{self.lesson.id}__{self.enrollment.id}"', html)
        self.assertNotIn('data-jd-lock="presence"', html)
