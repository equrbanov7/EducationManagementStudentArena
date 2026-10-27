"""Yeni dərsin növ kilidi (RİM 2026-10-27, MR-000054 / MR-000017): cədvəl tək növ verir, amma açılışın başqa
növə sübutu (dərs, pay, dərs yükü saatı) varsa kilid yoxdur."""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import gradebook
from apps.registrar.journal_extras import locked_lesson_kind
from apps.registrar.models import JournalShare, JournalShareSource, Lesson, LessonKind, ScheduleSlot
from apps.registrar.tests.test_journal_rules import _setup_offering
from apps.registrar.tests.test_journal_shares_2026_10_26 import _ShareBase
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.constants import OrgUnitType
from core.rls import bypass_rls


def _slot(case, kind, weekday=None, start=(8, 30), end=(9, 50)):
    return ScheduleSlot.objects.create(
        organization=case.org,
        offering=case.offering,
        weekday=timezone.localdate().isoweekday() if weekday is None else weekday,
        start_time=datetime.time(*start),
        end_time=datetime.time(*end),
        kind=kind,
    )


class LockRuleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "lkl")
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Tarix kafedrası", slug="lkl-chair", unit_type=OrgUnitType.CHAIR
            )

    def _lock(self):
        with bypass_rls():
            return locked_lesson_kind(self.offering)

    def _row(self, **hours):
        task = TeachingTask.objects.create(
            organization=self.org, chair=self.chair, academic_year="2026/2027", status="distributed"
        )
        row = TeachingTaskRow.objects.create(
            organization=self.org, task=task, period=self.period, subject=self.subject, **hours
        )
        row.groups.set([self.group])
        return row

    def test_no_slots_no_lock(self):
        self.assertIsNone(self._lock())

    def test_single_kind_without_other_evidence_locks(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=timezone.localdate(), kind=LessonKind.LECTURE
            )
            self._row(lecture_plan=30)
        self.assertEqual(self._lock(), LessonKind.LECTURE)

    def test_two_slot_kinds_no_lock(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            _slot(self, LessonKind.SEMINAR, weekday=3)
        self.assertIsNone(self._lock())

    def test_existing_lesson_of_other_kind_unlocks(self):
        # MR-000054: cədvəldə yalnız mühazirə slotu, jurnalda isə köhnə sistemdən gələn seminarlar var.
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=timezone.localdate(), kind=LessonKind.SEMINAR
            )
        self.assertIsNone(self._lock())

    def test_workload_seminar_hours_unlock(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            self._row(lecture_plan=30, seminar_plan=30)
        self.assertIsNone(self._lock())

    def test_workload_row_of_other_group_is_ignored(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            other = OrgUnit.objects.create(
                organization=self.org, name="JR-102", slug="lkl-jr102", unit_type=OrgUnitType.GROUP
            )
            self._row(lecture_plan=30, seminar_plan=30).groups.set([other])
        self.assertEqual(self._lock(), LessonKind.LECTURE)

    def test_active_share_of_other_kind_unlocks_inactive_does_not(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            share = JournalShare.objects.create(
                organization=self.org,
                offering=self.offering,
                teacher=self.teacher,
                kinds=["seminar"],
                source=JournalShareSource.LEGACY,
                is_active=False,
            )
        self.assertEqual(self._lock(), LessonKind.LECTURE)
        with bypass_rls():
            JournalShare.objects.filter(pk=share.pk).update(is_active=True)
        self.assertIsNone(self._lock())

    def test_deleted_slot_is_not_counted(self):
        with bypass_rls():
            _slot(self, LessonKind.LECTURE)
            _slot(self, LessonKind.SEMINAR, weekday=3).delete()
        self.assertEqual(self._lock(), LessonKind.LECTURE)


class SeminarShareOnLectureSlotTest(_ShareBase):
    """MR-000017: seminar payı olan müəllim, cədvəldə yalnız mühazirə slotu — seminar dərsi əlavə edə bilir."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            _slot(cls, LessonKind.LECTURE, start=(13, 35), end=(15, 5))

    def _add(self, kind):
        return self._client(self.seminarist).post(
            self._url(),
            {
                "action": "add_lesson",
                "lesson_date": timezone.localdate().isoformat(),
                "lesson_kind": kind,
                "lesson_hours": "2",
                "lesson_time": "13:35|15:05",
            },
        )

    def test_seminar_holder_adds_seminar(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        self.assertEqual(self._add("seminar").status_code, 302)
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering, start_time="13:35")
        self.assertEqual((lesson.kind, lesson.instructor_id), (LessonKind.SEMINAR, self.seminarist.pk))

    def test_seminar_holder_still_cannot_add_lecture(self):
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e2])
        self.assertEqual(self._add("lecture").status_code, 403)
