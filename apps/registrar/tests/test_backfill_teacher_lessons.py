"""``backfill_teacher_lessons`` — keçmiş dərslərin cədvəldən bərpası + hamıya «iə» (sahib 2026-10-15).

Dövr 3 həftə əvvəlki bazar ertəsi başlayır (1-ci həftə = üst/odd); aralıq ilk iki həftədir:
Çər. axşamı mühazirə hər həftə, Çərşənbə üst həftə mühazirə / alt həftə seminar → 4 dərs.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import pathlib
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import lesson_backfill, services
from apps.registrar.models import (
    AttendanceStatus,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    ScheduleSlot,
    SlotKind,
    WeekType,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
T = datetime.time


class BackfillTeacherLessonsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.start = today - datetime.timedelta(days=today.weekday() + 21)  # bazar ertəsi, 1-ci (üst) həftə
        cls.owner = User.objects.create_user("bf_owner", "bf_owner@qku.edu.az", "pw")
        cls.actor = User.objects.create_superuser("bf_admin", "bf_admin@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("bf.teacher", "bf_teacher@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="BF Univ",
                slug="bf-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="233 K ing", slug="bf-233k", unit_type=OrgUnitType.GROUP
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="234 K az", slug="bf-234k", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.start,
                end_date=today + datetime.timedelta(days=90),
                is_current=True,
            )
            cls.students = [User.objects.create_user(f"bf_s{i}", f"bf_s{i}@qku.edu.az", "pw") for i in range(5)]
            for user, role in [(cls.teacher, "teacher")] + [(student, "student") for student in cls.students]:
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            from apps.registrar.models import Subject

            web = Subject.objects.create(organization=cls.org, code="BF101", name="Müasir Veb proqramlaşdırma")
            mobile = Subject.objects.create(organization=cls.org, code="BF102", name="Mobil proqramlaşdırma")
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=web, period=cls.period, group=cls.group
            )
            cls.mobile = services.get_or_create_offering(
                organization=cls.org, subject=mobile, period=cls.period, group=cls.other_group
            )
            for offering in (cls.offering, cls.mobile):
                offering.instructor = cls.teacher
                offering.lesson_hours = 60
                offering.save(update_fields=["instructor", "lesson_hours"])
            status = Enrollment.Status
            cls.e_active, cls.e_absent, cls.e_dropped, cls.e_suspended, cls.e_guest = [
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering, status=st)
                for student, st in zip(
                    cls.students,
                    (status.ENROLLED, status.ENROLLED, status.DROPPED, status.SUSPENDED, status.ENROLLED),
                )
            ]
            # Alt qrupdan 2-ci həftənin çərşənbəsində əlavə olunub → əvvəlki dərslər işarələnmir.
            joined = datetime.datetime.combine(cls.start + datetime.timedelta(days=9), T(9, 0))
            cls.e_guest.source_group = cls.other_group
            cls.e_guest.added_at = timezone.make_aware(joined)
            cls.e_guest.save(update_fields=["source_group", "added_at"])

            def slot(offering, weekday, start, end, kind, week_type=WeekType.ALL):
                return ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=offering,
                    weekday=weekday,
                    start_time=start,
                    end_time=end,
                    kind=kind,
                    week_type=week_type,
                )

            cls.tue = slot(cls.offering, 2, T(15, 15), T(16, 45), SlotKind.LECTURE)
            cls.wed_odd = slot(cls.offering, 3, T(11, 50), T(13, 20), SlotKind.LECTURE, WeekType.ODD)
            cls.wed_even = slot(cls.offering, 3, T(11, 50), T(13, 20), SlotKind.SEMINAR, WeekType.EVEN)
            # Mövcud dərs (1-ci həftə çər. axşamı) + bir işarə (qb) — təkrarlanmamalı, işarə dəyişməməlidir.
            cls.existing = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=cls.start + datetime.timedelta(days=1),
                kind=LessonKind.LECTURE,
                start_time=T(15, 15),
                end_time=T(16, 45),
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=cls.existing, enrollment=cls.e_absent, status=AttendanceStatus.ABSENT
            )

    def _run(self, *, apply, specs=None, replace=False, days=13):
        with bypass_rls():
            return lesson_backfill.run_backfill(
                organization=self.org,
                period=self.period,
                teacher=self.teacher,
                date_from=self.start,
                date_to=self.start + datetime.timedelta(days=days),
                actor=self.actor,
                specs=specs,
                replace_slots=replace,
                apply=apply,
            )

    def _lessons(self, offering=None):
        with bypass_rls():
            return list(Lesson.objects.filter(offering=offering or self.offering).order_by("date", "start_time"))

    def _marks(self, enrollment):
        with bypass_rls():
            return dict(LessonMark.objects.filter(enrollment=enrollment).values_list("lesson__date", "status"))

    def _day(self, offset):
        return self.start + datetime.timedelta(days=offset)

    def test_dry_run_writes_nothing(self):
        with bypass_rls():
            before = (Lesson.objects.count(), LessonMark.objects.count(), ScheduleSlot.all_objects.count())
        result = self._run(apply=False)
        self.assertEqual(result.lesson_counts["create"], 3)
        self.assertEqual(result.lesson_counts["exists"], 1)
        self.assertGreater(result.marks_written, 0)
        with bypass_rls():
            after = (Lesson.objects.count(), LessonMark.objects.count(), ScheduleSlot.all_objects.count())
        self.assertEqual(before, after)

    def test_apply_creates_lessons_on_matching_weekdays_and_parity(self):
        result = self._run(apply=True)
        lessons = self._lessons()
        self.assertEqual(
            [(lesson.date, lesson.kind, lesson.start_time) for lesson in lessons],
            [
                (self._day(1), LessonKind.LECTURE, T(15, 15)),  # mövcud — təkrarlanmayıb
                (self._day(2), LessonKind.LECTURE, T(11, 50)),  # üst həftə
                (self._day(8), LessonKind.LECTURE, T(15, 15)),
                (self._day(9), LessonKind.SEMINAR, T(11, 50)),  # alt həftə
            ],
        )
        self.assertEqual(lessons[0].pk, self.existing.pk)
        self.assertEqual(result.lesson_counts["create"], 3)
        self.assertTrue(all(lesson.end_time == T(13, 20) for lesson in lessons if lesson.start_time == T(11, 50)))
        self.assertEqual(self._lessons(self.mobile), [])  # slotu yoxdur → dərs yox

    def test_marks_present_without_touching_existing_or_inactive(self):
        self._run(apply=True)
        dates = [self._day(offset) for offset in (1, 2, 8, 9)]
        self.assertEqual(self._marks(self.e_active), {day: AttendanceStatus.PRESENT for day in dates})
        absent = self._marks(self.e_absent)
        self.assertEqual(absent[self._day(1)], AttendanceStatus.ABSENT)  # mövcud işarə toxunulmayıb
        self.assertEqual(absent[self._day(9)], AttendanceStatus.PRESENT)
        self.assertEqual(self._marks(self.e_dropped), {})
        self.assertEqual(self._marks(self.e_suspended), {})
        self.assertEqual(self._marks(self.e_guest), {self._day(9): AttendanceStatus.PRESENT})

    def test_second_run_is_idempotent(self):
        self._run(apply=True)
        with bypass_rls():
            counts = (Lesson.objects.count(), LessonMark.objects.count())
        again = self._run(apply=True)
        self.assertEqual(again.lesson_counts["create"], 0)
        self.assertEqual(again.lesson_counts["exists"], 4)
        self.assertEqual(again.marks_written, 0)
        with bypass_rls():
            self.assertEqual((Lesson.objects.count(), LessonMark.objects.count()), counts)

    def test_existing_lesson_at_other_time_is_not_duplicated(self):
        with bypass_rls():
            Lesson.objects.filter(pk=self.existing.pk).update(start_time=T(16, 55), end_time=T(18, 25))
        result = self._run(apply=True)
        self.assertEqual(result.lesson_counts["exists_other_time"], 1)
        self.assertEqual(len([lesson for lesson in self._lessons() if lesson.date == self._day(1)]), 1)

    def test_slots_file_with_replace_soft_deletes_other_slots(self):
        specs = lesson_backfill.load_slot_spec(
            json.dumps(
                [
                    {"group": "233 K ing", "subject_contains": "Müasir Veb", "weekday": 2, "start": "16:55",
                     "end": "18:25", "kind": "lecture", "week_type": "all"},
                    {"group": "233 K ing", "subject_contains": "Müasir Veb", "weekday": 3, "start": "11:50",
                     "end": "13:20", "kind": "lecture", "week_type": "odd"},
                    {"group": "234 K az", "subject_contains": "Mobil", "weekday": 5, "start": "11:50",
                     "end": "13:20", "kind": "lecture", "week_type": "odd"},
                    {"group": "999 X", "subject_contains": "Mobil", "weekday": 5, "start": "08:30",
                     "end": "10:00", "kind": "lecture"},
                ]
            )  # fmt: skip
        )
        result = self._run(apply=True, specs=specs, replace=True)
        counts = result.slot_counts
        self.assertEqual((counts["kept"], counts["created"], counts["unmatched"]), (1, 2, 1))
        self.assertEqual(counts["soft_deleted"], 2)  # çər. axşamı 15:15 + çərşənbə alt həftə seminarı
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(pk__in=[self.tue.pk, self.wed_even.pk]).exists())
            self.assertEqual(ScheduleSlot.all_objects.filter(pk=self.tue.pk, is_deleted=True).count(), 1)
            self.assertTrue(ScheduleSlot.objects.filter(pk=self.wed_odd.pk).exists())
        # Çər. axşamı 1-ci həftə: mövcud 15:15 mühazirəsi eyni növlə tutuşur (yeni 16:55 dərsi YARANMIR).
        own = [(lesson.date, lesson.start_time) for lesson in self._lessons()]
        self.assertEqual(own, [(self._day(1), T(15, 15)), (self._day(2), T(11, 50)), (self._day(8), T(16, 55))])
        self.assertEqual([lesson.date for lesson in self._lessons(self.mobile)], [self._day(4)])

    def test_slots_file_without_replace_keeps_other_slots(self):
        specs = lesson_backfill.load_slot_spec(
            '[{"group": "234 K az", "subject_contains": "Mobil", "weekday": 5, "start": "11:50", "end": "13:20",'
            ' "kind": "seminar", "week_type": "even"}]'
        )
        result = self._run(apply=True, specs=specs)
        self.assertEqual(result.slot_counts["soft_deleted"], 0)
        with bypass_rls():
            self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering).count(), 3)
        self.assertEqual(self._lessons(), [self.existing])  # yalnız spesifikasiya slotlarından dərs
        self.assertEqual([lesson.date for lesson in self._lessons(self.mobile)], [self._day(11)])

    def test_spec_validation(self):
        for bad in ("[]", "{}", '[{"group": "", "weekday": 2}]', '[{"group": "A", "weekday": 9}]'):
            with self.assertRaises(lesson_backfill.SpecError):
                lesson_backfill.load_slot_spec(bad)

    def test_command_dry_run_default_and_report(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            call_command(
                "backfill_teacher_lessons",
                "--org", "bf-univ", "--teacher", "bf.teacher", "--period", "Payız 2026/2027",
                "--from", self.start.isoformat(), "--to", self._day(13).isoformat(),
                "--actor", "bf_admin", "--report", folder, stdout=out,
            )  # fmt: skip
            rows = list(csv.reader(pathlib.Path(folder, "lesson_backfill_lessons.csv").open(encoding="utf-8")))
        text = out.getvalue()
        self.assertIn("DRY-RUN", text)
        self.assertIn("create=3", text)
        self.assertNotIn("bf_s", text)  # tələbə adı/istifadəçi adı loga düşmür
        self.assertEqual(rows[0][:4], ["subject_code", "subject", "group", "date"])
        self.assertEqual(len(rows), 5)
        self.assertEqual(len(self._lessons()), 1)

    def test_command_rejects_non_superuser_actor_and_replace_without_spec(self):
        base = ["--org", "bf-univ", "--teacher", "bf.teacher", "--period", "Payız 2026/2027"]
        base += ["--from", self.start.isoformat(), "--to", self._day(13).isoformat()]
        with self.assertRaises(CommandError):
            call_command("backfill_teacher_lessons", *base, "--actor", "bf.teacher", stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command(
                "backfill_teacher_lessons",
                *base,
                "--actor",
                "bf_admin",
                "--replace-teacher-slots",
                stdout=io.StringIO(),
            )
