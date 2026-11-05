"""Sahib 2026-11-04 — müəllim müəyyən tarixdən bu günə keçmiş tarixli dərs əlavə edə bilər.

«sistem tənzimləməsində olmalıdır ki, müəllimlər sentyabrın 15-dən indiyə dərs əlavə edə bilsin; hələlik bunu
sistem idarəetməsindən idarə edim.»

Kilidlənən qaydalar:

* açarlar «journal» qrupundadır: ``journal.backdate_since_enabled`` (bool, defolt söndürülü) və
  ``journal.backdate_since`` (date, defolt 2026-09-15);
* söndürülüdə köhnə 7 günlük yazma pəncərəsi dəyişmir;
* yandırılanda başlanğıc tarixindən bu günədək dərs açılır və o dərsin boş xanasına yazılır (``EntryRule``),
  başlanğıcdan əvvəlki tarix rədd edilir (mesaj tarixi deyir), gələcək tarix yenə olmaz;
* başlanğıc tarixi adi həddən yenidirsə adi hədd qalır (pəncərəni daraltmır);
* modal tarix seçicisinin ``min``-i və ipucu eyni həddi göstərir.
"""

from __future__ import annotations

import datetime as dt
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.registrar import gradebook, journal_edit_windows
from apps.registrar.tests.test_journal_rules import _setup_offering
from core import runtime_settings as rs
from core.rls import bypass_rls
from core.runtime_settings_journal_backdate import (
    DEFAULT_BACKDATE_SINCE,
    KEY_BACKDATE_ENABLED,
    KEY_BACKDATE_SINCE,
    backdate_since,
)

User = get_user_model()
TODAY = timezone.localdate
OWNER_DAY = dt.date(2026, 11, 4)
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "backdate-since"}}
ON = {"JOURNAL_BACKDATE_SINCE_ENABLED": True, "JOURNAL_BACKDATE_SINCE": "2026-09-15"}


class BackdateRuleUnitTest(SimpleTestCase):
    def test_defaults_are_off_and_september_15(self):
        self.assertEqual(DEFAULT_BACKDATE_SINCE, "2026-09-15")
        self.assertIs(rs.SPECS[KEY_BACKDATE_ENABLED].default(), False)
        self.assertEqual(rs.SPECS[KEY_BACKDATE_ENABLED].kind, "bool")
        self.assertEqual(rs.SPECS[KEY_BACKDATE_SINCE].kind, "date")
        self.assertEqual(rs.SPECS[KEY_BACKDATE_SINCE].default(), "2026-09-15")
        self.assertEqual({rs.SPECS[KEY_BACKDATE_ENABLED].group, rs.SPECS[KEY_BACKDATE_SINCE].group}, {"journal"})
        self.assertIsNone(backdate_since())

    def test_disabled_keeps_the_seven_day_rule(self):
        self.assertEqual(journal_edit_windows.earliest_entry_date(OWNER_DAY), dt.date(2026, 10, 28))
        self.assertEqual(journal_edit_windows.lesson_date_error(dt.date(2026, 10, 28), today=OWNER_DAY), "")
        error = journal_edit_windows.lesson_date_error(dt.date(2026, 9, 20), today=OWNER_DAY)
        self.assertIn("ən çox 7 gün geriyə", error)

    @override_settings(**ON)
    def test_enabled_opens_from_since_date_to_today(self):
        self.assertEqual(backdate_since(), dt.date(2026, 9, 15))
        self.assertEqual(journal_edit_windows.earliest_entry_date(OWNER_DAY), dt.date(2026, 9, 15))
        for day in (dt.date(2026, 9, 15), dt.date(2026, 9, 20), dt.date(2026, 10, 1), OWNER_DAY):
            self.assertEqual(journal_edit_windows.lesson_date_error(day, today=OWNER_DAY), "", day)

    @override_settings(**ON)
    def test_enabled_rejects_before_since_and_future(self):
        error = journal_edit_windows.lesson_date_error(dt.date(2026, 9, 14), today=OWNER_DAY)
        self.assertEqual(
            error, "Dərs tarixi 15.09.2026 tarixindən əvvəl ola bilməz. Daha köhnə tarix üçün RİM-ə müraciət edin."
        )
        self.assertEqual(
            journal_edit_windows.lesson_date_error(OWNER_DAY + timedelta(days=1), today=OWNER_DAY),
            "Gələcək tarixə dərs əlavə etmək olmaz.",
        )

    @override_settings(JOURNAL_BACKDATE_SINCE_ENABLED=True, JOURNAL_BACKDATE_SINCE="2026-11-03")
    def test_recent_since_date_does_not_narrow_the_window(self):
        self.assertEqual(journal_edit_windows.earliest_entry_date(OWNER_DAY), dt.date(2026, 10, 28))
        self.assertIn(
            "ən çox 7 gün geriyə", journal_edit_windows.lesson_date_error(dt.date(2026, 10, 1), today=OWNER_DAY)
        )

    @override_settings(
        JOURNAL_BACKDATE_SINCE_ENABLED=True, JOURNAL_BACKDATE_SINCE="2026-09-15", JOURNAL_LATE_ENTRY_DAYS=0
    )
    def test_since_date_applies_even_with_zero_late_days(self):
        self.assertEqual(journal_edit_windows.lesson_date_error(dt.date(2026, 9, 20), today=OWNER_DAY), "")

    def test_entry_rule_message_names_the_since_date(self):
        rule = journal_edit_windows.EntryRule(
            now=timezone.now(),
            today=OWNER_DAY,
            late_days=7,
            activation_window=None,
            backdate_since=dt.date(2026, 9, 15),
        )
        self.assertEqual(rule.earliest_date, dt.date(2026, 9, 15))

        class _Lesson:
            date = dt.date(2026, 9, 10)

        self.assertIn("15.09.2026 tarixindən açıqdır", rule.block_reason(_Lesson()))
        _Lesson.date = dt.date(2026, 9, 20)
        self.assertEqual(rule.block_reason(_Lesson()), "")

    @override_settings(**ON)
    def test_template_context_exposes_since_bound(self):
        ctx = journal_edit_windows.template_context(OWNER_DAY)
        self.assertEqual(ctx["lesson_date_min"], dt.date(2026, 9, 15))
        self.assertEqual(ctx["lesson_backdate_since"], dt.date(2026, 9, 15))
        self.assertEqual(ctx["lesson_date_max"], OWNER_DAY)

    def test_template_context_without_since(self):
        ctx = journal_edit_windows.template_context(OWNER_DAY)
        self.assertEqual(ctx["lesson_date_min"], dt.date(2026, 10, 28))
        self.assertIsNone(ctx["lesson_backdate_since"])


class BackdateServiceTest(TestCase):
    """Servis qatı — dərs açma və boş xanaya yazı eyni həddə tabedir (bu günə nisbətən)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jbs")

    def _mark(self, lesson, status="absent"):
        entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": status}
        return gradebook.save_marks(offering=self.offering, entries=[entry], by_user=self.teacher, report=True)

    def test_disabled_old_lesson_is_refused(self):
        with bypass_rls():
            with self.assertRaisesMessage(gradebook.LessonRuleError, "ən çox 7 gün geriyə"):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - timedelta(days=20), created_by=self.teacher
                )

    def test_enabled_old_lesson_opens_and_takes_marks(self):
        since = TODAY() - timedelta(days=30)
        with override_settings(JOURNAL_BACKDATE_SINCE_ENABLED=True, JOURNAL_BACKDATE_SINCE=since.isoformat()):
            with bypass_rls():
                lesson = gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - timedelta(days=20), created_by=self.teacher
                )
                self.assertEqual(self._mark(lesson), {"written": 1, "rejected": 0})
                first = gradebook.create_lesson(offering=self.offering, date=since, created_by=self.teacher)
                with self.assertRaisesMessage(gradebook.LessonRuleError, "tarixindən əvvəl ola bilməz"):
                    gradebook.create_lesson(
                        offering=self.offering, date=since - timedelta(days=1), created_by=self.teacher
                    )
                with self.assertRaisesMessage(gradebook.LessonRuleError, "Gələcək tarixə dərs əlavə etmək olmaz."):
                    gradebook.create_lesson(
                        offering=self.offering, date=TODAY() + timedelta(days=1), created_by=self.teacher
                    )
                older = gradebook.create_lesson(
                    offering=self.offering, date=since - timedelta(days=1), created_by=self.teacher, allow_past=True
                )
                result = self._mark(older)
                self.assertEqual(result["written"], 0)
                self.assertIn("tarixindən açıqdır", result["blocked_reason"])
                journal = gradebook.get_offering_journal(offering=self.offering)
                markable = {meta["lesson"].pk: meta["markable"] for meta in journal["lesson_meta"]}
                self.assertEqual(markable, {lesson.pk: True, first.pk: True, older.pk: False})
        # Söndürüləndə adi 7 günlük qayda qayıdır — 20 gün əvvəlki dərsin boş xanası artıq bağlıdır.
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering)
            markable = {meta["lesson"].pk: meta["markable"] for meta in journal["lesson_meta"]}
            self.assertFalse(markable[lesson.pk])


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class BackdateSettingsPageTest(TestCase):
    def test_settings_page_lists_both_keys_and_save_applies(self):
        rs.invalidate()
        try:
            actor = User.objects.create_user("jbs_actor", "jbs_actor@qku.edu.az", "pw")
            groups = {group["key"]: group for group in runtime_settings_admin.describe()}
            fields = {field["key"]: field for field in groups["journal"]["fields"]}
            self.assertEqual(fields[KEY_BACKDATE_ENABLED]["kind"], "bool")
            self.assertIs(fields[KEY_BACKDATE_ENABLED]["value"], False)
            self.assertEqual(fields[KEY_BACKDATE_SINCE]["kind"], "date")
            self.assertEqual(fields[KEY_BACKDATE_SINCE]["value"], "2026-09-15")
            self.assertIsNone(backdate_since())

            runtime_settings_admin.save_values(
                actor=actor, data={KEY_BACKDATE_ENABLED: "1", KEY_BACKDATE_SINCE: "2026-09-01"}
            )
            self.assertIs(RuntimeSetting.objects.get(key=KEY_BACKDATE_ENABLED).value, True)
            self.assertEqual(backdate_since(), dt.date(2026, 9, 1))
            self.assertEqual(journal_edit_windows.earliest_entry_date(OWNER_DAY), dt.date(2026, 9, 1))

            with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
                runtime_settings_admin.save_values(actor=actor, data={KEY_BACKDATE_SINCE: "31.02.2026"})
            self.assertIn(KEY_BACKDATE_SINCE, ctx.exception.errors)

            runtime_settings_admin.save_values(actor=actor, data={KEY_BACKDATE_ENABLED: "0"})
            self.assertIsNone(backdate_since())
            self.assertEqual(journal_edit_windows.earliest_entry_date(OWNER_DAY), dt.date(2026, 10, 28))
        finally:
            rs.invalidate()
