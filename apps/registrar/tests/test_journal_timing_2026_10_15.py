"""Jurnal vaxt qaydaları «Sistem tənzimləmələri»ndə (sahib 2026-10-15).

Kilidlənən qaydalar:

* düzəliş pəncərələri DƏQİQƏ ilə (``journal.mark_edit_minutes`` defolt 15 — 2026-10-25, ``journal.lesson_edit_minutes``
  defolt 120);
  dəqiqə yoxdursa köhnə saat açarı (×60), o da yoxdursa 120 — servis və DB trigger-i eyni ardıcıllıqla;
* ``journal.late_entry_days`` (defolt 0 = yalnız dərs günü): N gün geriyə dərs açmaq və yeni qeyd yazmaq olur,
  sonra açıq Azərbaycan mesajı ilə bağlanır; ``allow_past`` / ``enforce_day=False`` bypass-ları işləyir;
* «Aktivləşdir» yanılıdırsa yeni qeyd aktivləşdirmədən sonrakı ``journal.activation_write_minutes`` ərzində;
* forma: köhnə saat açarları gizlidir, dəqiqə yazılanda köhnə sətir silinir, hədd xarici dəyər rədd olunur.
"""

from __future__ import annotations

import datetime
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.organizations.models import Membership, Role
from apps.registrar import gradebook, journal_edit_windows
from apps.registrar.models import AttendanceStatus, Lesson, LessonMark
from apps.registrar.tests.test_journal_rules import _setup_offering
from core import runtime_settings as rs
from core.constants import RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "journal-timing"}}
TODAY = timezone.localdate


def _settings(**values):
    RuntimeSetting.objects.all().delete()
    for key, value in values.items():
        RuntimeSetting.objects.create(key=key, value=value)
    rs.invalidate()


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class EditWindowMinutesTest(TestCase):
    def tearDown(self):
        rs.invalidate()

    def test_defaults_lesson_120_mark_15_minutes(self):
        _settings()
        self.assertEqual(journal_edit_windows.mark_edit_window(), timedelta(minutes=15))
        self.assertEqual(journal_edit_windows.lesson_edit_window(), timedelta(minutes=120))

    def test_minutes_override_wins_over_hours(self):
        _settings(**{"journal.mark_edit_minutes": 45, "journal.mark_edit_hours": 5, "journal.lesson_edit_minutes": 15})
        self.assertEqual(gradebook.mark_edit_window(), timedelta(minutes=45))
        self.assertEqual(gradebook.lesson_edit_window(), timedelta(minutes=15))

    def test_fallback_to_legacy_hours(self):
        _settings(**{"journal.mark_edit_hours": 3, "journal.lesson_edit_hours": 1})
        self.assertEqual(gradebook.mark_edit_window(), timedelta(minutes=180))
        self.assertEqual(gradebook.lesson_edit_window(), timedelta(minutes=60))

    def test_invalid_minutes_fall_back(self):
        _settings(**{"journal.mark_edit_minutes": 99999, "journal.mark_edit_hours": 2})
        self.assertEqual(gradebook.mark_edit_window(), timedelta(hours=2))

    def test_service_freezes_mark_after_minutes(self):
        with bypass_rls():
            _setup_offering(self, "jtm")
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}
            gradebook.save_marks(offering=self.offering, entries=[entry], by_user=self.teacher)
            mark = LessonMark.objects.get(lesson=lesson)
            LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=40))
            _settings(**{"journal.mark_edit_minutes": 30})
            mark.refresh_from_db()
            self.assertFalse(gradebook.can_edit_mark(mark))
            _settings(**{"journal.mark_edit_minutes": 60})
            self.assertTrue(gradebook.can_edit_mark(mark))


class MarkTriggerMinutesTest(TestCase):
    """Trigger cədvəli birbaşa oxuyur (``RUNTIME_SETTINGS_ENABLED`` ondan asılı deyil)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jtt")

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")

    def _stale_mark(self, minutes_ago):
        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            mark = LessonMark.objects.get(lesson=lesson)
            LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
            return mark

    def _raw_update_fails(self, mark) -> bool:
        try:
            with bypass_rls(), transaction.atomic():
                LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
        except InternalError:
            return True
        return False

    def test_trigger_reads_minutes_key(self):
        RuntimeSetting.objects.create(key="journal.mark_edit_minutes", value=30)
        self.assertTrue(self._raw_update_fails(self._stale_mark(45)))
        RuntimeSetting.objects.filter(key="journal.mark_edit_minutes").update(value=60)
        self.assertFalse(self._raw_update_fails(self._stale_mark(45)))

    def test_trigger_falls_back_to_hours_then_default(self):
        RuntimeSetting.objects.create(key="journal.mark_edit_hours", value=1)
        self.assertFalse(self._raw_update_fails(self._stale_mark(45)))
        self.assertTrue(self._raw_update_fails(self._stale_mark(75)))
        RuntimeSetting.objects.all().delete()
        self.assertFalse(self._raw_update_fails(self._stale_mark(10)))  # defolt 15 dəqiqə (0099, sahib 2026-10-25)
        self.assertTrue(self._raw_update_fails(self._stale_mark(20)))


class LateEntryDaysTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jtl")

    def _mark(self, lesson, **kwargs):
        entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present"}
        return gradebook.save_marks(
            offering=self.offering, entries=[entry], by_user=self.teacher, report=True, **kwargs
        )

    def _past_lesson(self, days):
        return gradebook.create_lesson(
            offering=self.offering, date=TODAY() - timedelta(days=days), created_by=self.teacher, allow_past=True
        )

    @override_settings(JOURNAL_LATE_ENTRY_DAYS=0)
    def test_zero_days_keeps_lesson_day_rule(self):
        with bypass_rls():
            with self.assertRaisesMessage(gradebook.LessonRuleError, "Keçmiş tarixə dərs əlavə etmək olmaz."):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - timedelta(days=1), created_by=self.teacher
                )
            result = self._mark(self._past_lesson(1))
            self.assertEqual(result["written"], 0)
            self.assertEqual(result["blocked"], 1)
            self.assertIn("dərsin öz günündə", result["blocked_reason"])
            journal = gradebook.get_offering_journal(offering=self.offering)
            self.assertFalse(journal["lesson_meta"][0]["markable"])

    @override_settings(JOURNAL_LATE_ENTRY_DAYS=2)
    def test_two_days_allow_create_and_mark_then_block(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering, date=TODAY() - timedelta(days=2), created_by=self.teacher
            )
            self.assertEqual(self._mark(lesson), {"written": 1, "rejected": 0})
            with self.assertRaisesMessage(gradebook.LessonRuleError, "ən çox 2 gün geriyə"):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - timedelta(days=3), created_by=self.teacher
                )
            old = self._past_lesson(3)
            result = self._mark(old)
            self.assertEqual(result["written"], 0)
            self.assertIn("2 gündən çox keçib", result["blocked_reason"])
            # Grid eyni qaydanı göstərir: 2 gün əvvəlki dərs yazılır, 3 gün əvvəlki yox.
            journal = gradebook.get_offering_journal(offering=self.offering)
            markable = {meta["lesson"].pk: meta["markable"] for meta in journal["lesson_meta"]}
            self.assertEqual(markable, {lesson.pk: True, old.pk: False})
            self.assertEqual(journal_edit_windows.template_context()["lesson_date_min"], TODAY() - timedelta(days=2))

    @override_settings(JOURNAL_LATE_ENTRY_DAYS=2)
    def test_update_lesson_respects_limit(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            self.assertTrue(gradebook.update_lesson(lesson=lesson, date=TODAY() - timedelta(days=1)))
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=lesson, date=TODAY() - timedelta(days=5))

    def test_bypasses_still_work(self):
        with bypass_rls():
            lesson = self._past_lesson(10)  # allow_past (RİM/İKT, seed, backfill)
            self.assertEqual(self._mark(lesson, enforce_day=False), {"written": 1, "rejected": 0})

    def test_future_lesson_still_blocked(self):
        with bypass_rls():
            # Müəllim gələcək tarixə dərs aça bilmir (2026-10-25); RİM/İKT override açsa da qeyd hələ yazılmır.
            future = gradebook.create_lesson(
                offering=self.offering, date=TODAY() + timedelta(days=1), created_by=self.teacher, allow_past=True
            )
            self.assertEqual(self._mark(future)["written"], 0)


@override_settings(JOURNAL_LESSON_ACTIVATION=True, JOURNAL_ACTIVATION_WRITE_MINUTES=60, JOURNAL_LATE_ENTRY_DAYS=1)
class ActivationWindowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jta")

    def _lesson_created(self, minutes_ago):
        created = timezone.now() - timedelta(minutes=minutes_ago)
        lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
        # Tarix yaranış gününə bərabər (gecəyarısı keçidində də aktivləşdirmə qaydası yoxlanır).
        Lesson.objects.filter(pk=lesson.pk).update(created_at=created, date=timezone.localtime(created).date())
        lesson.refresh_from_db()
        return lesson

    def _mark(self, lesson, **kwargs):
        entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}
        return gradebook.save_marks(
            offering=self.offering, entries=[entry], by_user=self.teacher, report=True, **kwargs
        )

    def test_marks_only_within_window_after_activation(self):
        with bypass_rls():
            self.assertEqual(self._mark(self._lesson_created(30))["written"], 1)
            stale = self._lesson_created(90)
            result = self._mark(stale)
            self.assertEqual(result["written"], 0)
            self.assertIn("aktivləşdiriləndən 1 saat keçib", result["blocked_reason"])
            self.assertEqual(self._mark(stale, enforce_day=False)["written"], 1)  # bypass

    @override_settings(JOURNAL_LESSON_ACTIVATION=False)
    def test_rule_off_when_activation_disabled(self):
        with bypass_rls():
            self.assertEqual(self._mark(self._lesson_created(90))["written"], 1)
        self.assertEqual(journal_edit_windows.template_context()["activation_write_label"], "")


class ActivationStartTest(SimpleTestCase):
    def test_lesson_opened_in_advance_counts_from_start_time(self):
        tz = timezone.get_current_timezone()
        day = datetime.date(2026, 10, 15)
        created = timezone.make_aware(datetime.datetime(2026, 10, 13, 12, 0), tz)
        lesson = Lesson(date=day, start_time=datetime.time(9, 0), created_at=created)
        start = journal_edit_windows.activation_start(lesson)
        self.assertEqual(start, timezone.make_aware(datetime.datetime(2026, 10, 15, 9, 0), tz))
        rule = journal_edit_windows.EntryRule(
            now=start + timedelta(minutes=50), today=day, late_days=0, activation_window=timedelta(minutes=60)
        )
        self.assertTrue(rule.allows(lesson))
        later = journal_edit_windows.EntryRule(
            now=start + timedelta(minutes=70), today=day, late_days=0, activation_window=timedelta(minutes=60)
        )
        self.assertFalse(later.allows(lesson))

    def test_duration_text(self):
        self.assertEqual(journal_edit_windows.duration_text(timedelta(minutes=120)), "2 saat")
        self.assertEqual(journal_edit_windows.duration_text(timedelta(minutes=90)), "90 dəqiqə")
        self.assertEqual(journal_edit_windows.duration_text(timedelta(minutes=150)), "2 saat 30 dəqiqə")


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class TimingSettingsFormTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jtf")
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="ikt_rehber",
            defaults={
                "display_name": "RİM",
                "level": 95,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["semester.view"],
                "is_active": True,
            },
        )
        cls.rim = User.objects.create_user("jtf_rim", "jtf_rim@qku.edu.az", "pw")
        Membership.objects.create(user=cls.rim, organization=cls.org, role=role, is_primary=False, is_active=True)

    def setUp(self):
        _settings()

    def tearDown(self):
        rs.invalidate()

    def test_journal_group_shows_new_keys_and_hides_hours(self):
        groups = {group["key"]: group for group in runtime_settings_admin.describe()}
        keys = [field["key"] for field in groups["journal"]["fields"]]
        for key in (
            "journal.lesson_edit_minutes",
            "journal.mark_edit_minutes",
            "journal.late_entry_days",
            "journal.activation_write_minutes",
        ):
            self.assertIn(key, keys)
        self.assertNotIn("journal.mark_edit_hours", keys)
        self.assertNotIn("journal.lesson_edit_hours", keys)
        units = {field["key"]: field["unit"] for field in groups["journal"]["fields"]}
        self.assertEqual(units["journal.mark_edit_minutes"], "dəqiqə")
        self.assertEqual(units["journal.late_entry_days"], "gün")

    def test_save_validates_and_drops_legacy_row(self):
        RuntimeSetting.objects.create(key="journal.mark_edit_hours", value=4)
        rs.invalidate()
        for key, bad in (
            ("journal.mark_edit_minutes", "0"),
            ("journal.mark_edit_minutes", "5000"),
            ("journal.late_entry_days", "31"),
            ("journal.activation_write_minutes", "abc"),
        ):
            with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
                runtime_settings_admin.save_values(actor=self.rim, data={key: bad})
            self.assertIn(key, ctx.exception.errors)
        # Köhnə saat açarı formadan yazılmır.
        runtime_settings_admin.save_values(actor=self.rim, data={"journal.mark_edit_hours": "9"})
        self.assertTrue(RuntimeSetting.objects.filter(key="journal.mark_edit_hours", value=4).exists())

        runtime_settings_admin.save_values(
            actor=self.rim, data={"journal.mark_edit_minutes": "45", "journal.late_entry_days": "2"}
        )
        self.assertFalse(RuntimeSetting.objects.filter(key="journal.mark_edit_hours").exists())
        self.assertEqual(gradebook.mark_edit_window(), timedelta(minutes=45))
        self.assertEqual(journal_edit_windows.late_entry_days(), 2)

    def test_endpoint_rejects_out_of_range(self):
        client = Client()
        client.force_login(self.rim)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("accounts:system_settings_save")
        bad = client.post(url, {"journal.late_entry_days": "99"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("journal.late_entry_days", bad.json()["errors"])
        good = client.post(url, {"journal.activation_write_minutes": "90"})
        self.assertEqual(good.status_code, 200, good.content)
        self.assertTrue(RuntimeSetting.objects.filter(key="journal.activation_write_minutes", value=90).exists())


class HoursToMinutesMigrationTest(TestCase):
    """registrar 0089 data hissəsi: saat → dəqiqə (×60, köhnə sətir silinir), geri: dəqiqə → saat."""

    def test_forward_and_reverse(self):
        import importlib

        from django.apps import apps as registry

        migration = importlib.import_module("apps.registrar.migrations.0089_journal_windows_in_minutes")
        RuntimeSetting.objects.all().delete()
        RuntimeSetting.objects.create(key="journal.mark_edit_hours", value=3)
        RuntimeSetting.objects.create(key="journal.lesson_edit_hours", value=2)
        RuntimeSetting.objects.create(key="journal.lesson_edit_minutes", value=30)  # yeni açar üstündür
        migration._hours_to_minutes(registry, None)
        values = dict(RuntimeSetting.objects.values_list("key", "value"))
        self.assertEqual(values, {"journal.mark_edit_minutes": 180, "journal.lesson_edit_minutes": 30})

        migration._minutes_to_hours(registry, None)
        values = dict(RuntimeSetting.objects.values_list("key", "value"))
        self.assertEqual(values, {"journal.mark_edit_hours": 3, "journal.lesson_edit_hours": 1})
