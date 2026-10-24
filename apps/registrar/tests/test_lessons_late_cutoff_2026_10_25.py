"""«Gec yazılıb» nəzarətinin başlanğıc tarixi (``journal.late_check_from``, sahib 2026-10-25).

Sahib: «o "Gec yazılıb"ı hər yerdən sil, çünki datanı inteqrasiya etmişik … gələn həftədən ola bilər.»
Kilidlənən qaydalar:

* tarixi başlanğıc tarixindən ƏVVƏL olan dərs heç yerdə «gec» deyil (sətir/ixrac ``note_state`` və KPI SQL-i);
* başlanğıc tarixi və sonrası mövcud 48 saat qaydasına tabedir;
* tənzimləmə dəyişəndə nəticə dəyişir (KPI keşi də — açar tarixi daşıyır);
* defolt 2026-10-26; yararsız saxlanmış dəyər tətbiq olunmur; forma tarixi yoxlayıb yazır.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.registrar import lessons_log as service
from apps.registrar.lessons_late_rule import is_late
from apps.registrar.lessons_log_totals import _compute_range_totals, totals_cache_key
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core import runtime_settings as rs
from core.runtime_settings_journal_late import DEFAULT_LATE_CHECK_FROM, KEY_LATE_CHECK_FROM, late_check_from

User = get_user_model()
PASSWORD = "StrongPass123!"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "late-cutoff"}}


class LateRuleUnitTest(SimpleTestCase):
    def test_lesson_before_the_cutoff_is_never_late(self):
        cutoff = dt.date(2026, 10, 26)
        self.assertFalse(
            is_late(lesson_date=dt.date(2026, 10, 25), written_date=dt.date(2027, 3, 1), check_from=cutoff)
        )
        self.assertFalse(is_late(lesson_date=dt.date(2025, 1, 1), written_date=dt.date(2025, 9, 1), check_from=cutoff))

    def test_lesson_on_or_after_the_cutoff_keeps_the_48_hour_rule(self):
        cutoff = dt.date(2026, 10, 26)
        lesson = dt.date(2026, 10, 26)
        self.assertFalse(is_late(lesson_date=lesson, written_date=dt.date(2026, 10, 28), check_from=cutoff))
        self.assertTrue(is_late(lesson_date=lesson, written_date=dt.date(2026, 10, 29), check_from=cutoff))
        later = dt.date(2026, 11, 2)
        self.assertTrue(is_late(lesson_date=later, written_date=dt.date(2026, 11, 9), check_from=cutoff))

    def test_default_cutoff_is_next_monday(self):
        self.assertEqual(DEFAULT_LATE_CHECK_FROM, "2026-10-26")
        self.assertEqual(dt.date.fromisoformat(DEFAULT_LATE_CHECK_FROM).weekday(), 0)
        with override_settings():
            del settings.JOURNAL_LATE_CHECK_FROM  # test ayarının erkən tarixi götürülür → kod defoltu
            self.assertEqual(late_check_from(), dt.date(2026, 10, 26))
            self.assertEqual(rs.SPECS[KEY_LATE_CHECK_FROM].default(), "2026-10-26")

    def test_date_kind_coerces_only_valid_iso_dates(self):
        spec = rs.SPECS[KEY_LATE_CHECK_FROM]
        self.assertEqual(rs.coerce(spec, "2026-11-02"), "2026-11-02")
        self.assertEqual(rs.coerce(spec, dt.date(2026, 11, 2)), "2026-11-02")
        for raw in ("", None, "02.11.2026", "2026-13-40", "abc", True):
            self.assertIsNone(rs.coerce(spec, raw), raw)
        # Başqa növlər tarix qəbul etmir (coerce yönləndirməsi bayraqları/ədədləri pozmur).
        self.assertIsNone(rs.coerce(rs.SPECS["journal.late_entry_days"], "2026-11-02"))


@override_settings(UNIVERSITY_MODE=True)
class LateCutoffLessonsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("lcut-univ")
        cls.stack = make_academic_stack(cls.org, code="LCUT1")
        cls.teacher = User.objects.create_user("lcut_teacher", "lcut_teacher@qku.edu.az", PASSWORD)
        cls.student = User.objects.create_user("lcut_student", "lcut_student@qku.edu.az", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=["course.view", "grade.input"])
        activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        cls.d_before = dt.date(2025, 10, 6)
        cls.d_cutoff = dt.date(2025, 10, 13)
        cls.d_after = dt.date(2025, 10, 20)
        # üç dərsin üçü də müəllimin öz dərsidir və 5 gün sonra yazılıb (qayda üzrə «gec»)
        cls.lessons = {}
        for name, day in (("before", cls.d_before), ("cutoff", cls.d_cutoff), ("after", cls.d_after)):
            lesson = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=day,
                kind=LessonKind.SEMINAR,
                hours=2,
                instructor=cls.teacher,
                created_by=cls.teacher,
            )
            mark = LessonMark.objects.create(
                organization=cls.org,
                lesson=lesson,
                enrollment=cls.enrollment,
                status=AttendanceStatus.PRESENT,
                entered_by=cls.teacher,
            )
            stamp = timezone.make_aware(dt.datetime.combine(day + dt.timedelta(days=5), dt.time(10, 0)))
            LessonMark.objects.filter(pk=mark.pk).update(created_at=stamp)
            cls.lessons[name] = lesson

    def _notes_and_totals(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        notes = {row["id"]: row["note"] for row in service.build_rows(lessons)}
        return notes, _compute_range_totals(lessons)

    def _note(self, notes, name):
        return notes[str(self.lessons[name].pk)]

    @override_settings(JOURNAL_LATE_CHECK_FROM="2000-01-01")
    def test_cutoff_in_the_far_past_keeps_the_old_behaviour(self):
        notes, totals = self._notes_and_totals()
        self.assertEqual({self._note(notes, n) for n in self.lessons}, {service.NOTE_LATE})
        self.assertEqual(totals["late"], 3)

    @override_settings(JOURNAL_LATE_CHECK_FROM="2025-10-13")
    def test_lessons_before_the_cutoff_are_not_late_anywhere(self):
        notes, totals = self._notes_and_totals()
        self.assertEqual(self._note(notes, "before"), service.NOTE_ON_TIME)
        self.assertEqual(self._note(notes, "cutoff"), service.NOTE_LATE)  # başlanğıc günü özü daxildir
        self.assertEqual(self._note(notes, "after"), service.NOTE_LATE)
        self.assertEqual(totals["late"], 2)
        self.assertEqual(totals["empty"], 0)
        self.assertEqual(totals["lessons"], 3)

    @override_settings(JOURNAL_LATE_CHECK_FROM="2026-10-26")
    def test_production_default_clears_all_past_data(self):
        notes, totals = self._notes_and_totals()
        self.assertEqual({self._note(notes, n) for n in self.lessons}, {service.NOTE_ON_TIME})
        self.assertEqual(totals["late"], 0)

    @override_settings(JOURNAL_LATE_CHECK_FROM="2025-10-20")
    def test_rows_and_sql_totals_agree(self):
        notes, totals = self._notes_and_totals()
        self.assertEqual(totals["late"], sum(1 for note in notes.values() if note == service.NOTE_LATE))
        self.assertEqual(totals["late"], 1)

    @override_settings(JOURNAL_LATE_CHECK_FROM="2025-10-13")
    def test_export_rows_follow_the_cutoff(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        rows = service.build_rows(lessons, limit=service.ROW_CAP)
        flagged = [row for row in rows if row["note"] != service.NOTE_ON_TIME]  # «yalnız problemli» süzgəci
        self.assertEqual({row["date"] for row in flagged}, {self.d_cutoff, self.d_after})

    def test_totals_cache_key_changes_with_the_cutoff(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        with override_settings(JOURNAL_LATE_CHECK_FROM="2025-10-13"):
            first = totals_cache_key(lessons)
            self.assertEqual(first, totals_cache_key(lessons))
        with override_settings(JOURNAL_LATE_CHECK_FROM="2025-10-20"):
            self.assertNotEqual(first, totals_cache_key(lessons))

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_changing_the_setting_changes_the_result(self):
        rs.invalidate()
        try:
            actor = User.objects.create_user("lcut_actor", "lcut_actor@qku.edu.az", PASSWORD)
            lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
            # sətir yoxdur → kod/test defoltu (2000-01-01): hamısı gec
            self.assertEqual(service.range_totals(lessons)["late"], 3)
            runtime_settings_admin.save_values(actor=actor, data={KEY_LATE_CHECK_FROM: "2025-10-20"})
            self.assertEqual(RuntimeSetting.objects.get(key=KEY_LATE_CHECK_FROM).value, "2025-10-20")
            self.assertEqual(service.range_totals(lessons)["late"], 1)  # keş açarı tarixi daşıyır → təzədən hesablanır
            notes = {row["id"]: row["note"] for row in service.build_rows(lessons)}
            self.assertEqual(self._note(notes, "cutoff"), service.NOTE_ON_TIME)
            self.assertEqual(self._note(notes, "after"), service.NOTE_LATE)
            # defolta qayıdış sətri silir
            runtime_settings_admin.save_values(actor=actor, data={KEY_LATE_CHECK_FROM: "2000-01-01"})
            self.assertFalse(RuntimeSetting.objects.filter(key=KEY_LATE_CHECK_FROM).exists())
            self.assertEqual(service.range_totals(lessons)["late"], 3)
        finally:
            rs.invalidate()

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_invalid_stored_or_submitted_date_is_not_applied(self):
        rs.invalidate()
        try:
            actor = User.objects.create_user("lcut_actor2", "lcut_actor2@qku.edu.az", PASSWORD)
            RuntimeSetting.objects.create(key=KEY_LATE_CHECK_FROM, value="bu tarix deyil")
            rs.invalidate()
            self.assertEqual(late_check_from(), dt.date(2000, 1, 1))  # yararsız dəyər → defolt
            with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
                runtime_settings_admin.save_values(actor=actor, data={KEY_LATE_CHECK_FROM: "31.02.2026"})
            self.assertIn(KEY_LATE_CHECK_FROM, ctx.exception.errors)
        finally:
            rs.invalidate()

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_settings_page_describes_the_date_field(self):
        rs.invalidate()
        try:
            fields = {field["key"]: field for group in runtime_settings_admin.describe() for field in group["fields"]}
            field = fields[KEY_LATE_CHECK_FROM]
            self.assertEqual(field["kind"], "date")
            self.assertEqual(field["value"], "2000-01-01")  # test ayarı; istehsalda 2026-10-26
        finally:
            rs.invalidate()
