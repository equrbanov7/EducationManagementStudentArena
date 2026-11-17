"""Sahib 2026-11-17 (MR-000482): köhnə sistemin saat-saat yazdığı dərslər 2 → 1 saat, boş artıq sətirlər silinir."""

from __future__ import annotations

import datetime
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import legacy_hour_rows_2026_11_17 as service
from apps.registrar.legacy_hour_rows_rule import HOUR_MODE, NO_CHANGE, WINDOW_MODE, Row, decide
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

T = datetime.time
D1, D2, D3 = datetime.date(2024, 3, 4), datetime.date(2024, 3, 5), datetime.date(2024, 3, 6)


class RuleTest(SimpleTestCase):
    def test_hour_mode_lowers_every_two_hour_row_including_single_days(self):
        rows = [
            Row(1, D1, T(15, 35), 2),
            Row(2, D1, T(16, 25), 2),
            Row(3, D2, T(13, 50), 2),
            Row(4, D2, T(14, 40), 2),
            Row(5, D3, T(10, 0), 2),
        ]
        decision = decide(rows, 5)
        self.assertEqual(decision.mode, HOUR_MODE)
        self.assertEqual(decision.targets, {1, 2, 3, 4, 5})
        self.assertEqual((decision.total_before, decision.total_after), (10, 5))

    def test_window_mode_only_touches_rows_inside_one_pair(self):
        rows = [
            Row(1, D1, T(10, 0), 2),
            Row(2, D1, T(10, 50), 2),
            Row(3, D2, T(10, 0), 2),
            Row(4, D3, T(10, 0), 2),
            Row(5, D3, T(11, 40), 2),
        ]
        decision = decide(rows, 8)
        self.assertEqual(decision.mode, WINDOW_MODE)
        self.assertEqual(decision.targets, {1, 2})
        self.assertEqual(decision.total_after, 8)

    def test_pair_journal_and_non_two_hour_rows_are_untouched(self):
        pairs = [Row(1, D1, T(10, 0), 2), Row(2, D1, T(11, 40), 2), Row(3, D2, T(10, 0), 2)]
        self.assertEqual(decide(pairs, 6).mode, NO_CHANGE)
        done = [Row(1, D1, T(15, 35), 1), Row(2, D1, T(16, 25), 1)]
        self.assertEqual(decide(done, 2).targets, set())

    def test_tiny_gap_duplicates_are_counted_and_lowered(self):
        rows = [Row(1, D1, T(17, 43), 2), Row(2, D1, T(17, 44), 2), Row(3, D2, T(10, 0), 2)]
        decision = decide(rows, 4)
        self.assertEqual((decision.mode, decision.targets, decision.tiny_gap_rows), (WINDOW_MODE, {1, 2}, 2))


class FixLegacyHourRowsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        today = timezone.localdate()
        with bypass_rls():
            cls.owner = User.objects.create_user("lgh_owner", "lgh_owner@x.test", "pw", is_superuser=True)
            cls.org = Organization.objects.create(
                name="LGH Univ", slug="lgh-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
            )
            group = OrgUnit.objects.create(
                organization=cls.org, name="LGH-1", slug="lgh-1", unit_type=OrgUnitType.GROUP
            )
            current = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.past = past = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date=datetime.date(2024, 2, 1),
                end_date=datetime.date(2024, 6, 30),
            )
            subject = Subject.objects.create(organization=cls.org, code="KIM", name="Kimya")
            cls.offering = CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=past, group=group, lesson_hours=6
            )
            cls.live = CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=current, group=group, lesson_hours=6
            )
            role, _created = Role.objects.get_or_create(
                organization=cls.org, name="student", defaults={"display_name": "Student", "level": 50}
            )
            Role.objects.filter(pk=role.pk).update(is_active=True, scope_type=RoleScopeType.ORGANIZATION)
            students = [User.objects.create_user(f"lgh_st{i}", f"lgh_st{i}@x.test", "pw") for i in range(2)]
            for student in students:
                Membership.objects.create(organization=cls.org, user=student, role=role, is_active=True)
            cls.group = group
            cls.e1, cls.e2 = (
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering)
                for student in students
            )

    def setUp(self):
        with bypass_rls():
            make = self._lesson
            self.a1, self.a2 = make(D1, T(15, 35)), make(D1, T(16, 25))
            self.b1, self.b2 = make(D2, T(13, 50)), make(D2, T(14, 40))
            self.c1, self.c2 = make(D3, T(10, 0)), make(D3, T(10, 50))
            self.empty = make(D2, T(17, 43))
            self.teacher_lesson = make(D3, T(12, 0), created_by=self.owner)
            self.live_lesson = make(datetime.date.today(), T(15, 35), offering=self.live)
            for lesson in (self.a1, self.a2, self.b1, self.b2, self.c1, self.c2):
                self._mark(lesson, self.e1, "present")
            self._mark(self.a1, self.e2, "absent")
            self._mark(self.a2, self.e2, "present")
            self._mark(self.b1, self.e2, "present")
            self._mark(self.b2, self.e2, "present")
            self._mark(self.c1, self.e2, "present")
            self._mark(self.c2, self.e2, "present")
            Enrollment.objects.filter(pk=self.e2.pk).update(absence_hours=2)

    def _lesson(self, date, start, *, offering=None, created_by=None):
        return Lesson.objects.create(
            organization=self.org,
            offering=offering or self.offering,
            date=date,
            start_time=start,
            kind="lecture",
            hours=2,
            created_by=created_by,
        )

    def _mark(self, lesson, enrollment, status):
        LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status=status)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "fix_legacy_hour_rows_20261117", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts, batch = {}, ""
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^legacy_hours: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if line.startswith("legacy_hours: org="):
                counts.update(pair.split("=", 1) for pair in line.split()[2:])
            if "batch=" in line:
                batch = line.split("batch=")[1].split()[0]
        return counts, batch

    def _hours(self):
        with bypass_rls():
            return dict(Lesson.objects.filter(organization=self.org).values_list("pk", "hours"))

    def test_dry_run_counts_without_writing(self):
        counts, _batch = self._call()
        self.assertEqual(counts["offerings_hour_mode"], "1")
        self.assertEqual((counts["lessons_one_hour"], counts["lessons_empty_deleted"]), ("6", "1"))
        self.assertEqual((counts["enrollments_unbarred"], counts["students_unbarred"]), ("1", "1"))
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.empty.pk).exists())
        self.assertEqual(set(self._hours().values()), {2})

    def test_apply_lowers_legacy_rows_recomputes_absence_and_undo_restores(self):
        counts, batch = self._call("--apply")
        self.assertEqual(counts["lessons_one_hour"], "6")
        hours = self._hours()
        for lesson in (self.a1, self.a2, self.b1, self.b2, self.c1, self.c2):
            self.assertEqual(hours[lesson.pk], 1)
        self.assertNotIn(self.empty.pk, hours)
        self.assertEqual(hours[self.teacher_lesson.pk], 2)  # yeni sistemdə müəllimin yazdığı dərs
        self.assertEqual(hours[self.live_lesson.pk], 2)  # cari semestr
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).absence_hours, 1)
        self.assertEqual(self._call("--apply")[0]["lessons_one_hour"], "0")  # idempotent

        undo, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual((undo["undo_hours_restored"], undo["undo_lessons_recreated"]), ("6", "1"))
        self.assertEqual(set(self._hours().values()), {2})
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.empty.pk, start_time=T(17, 43)).exists())
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).absence_hours, 2)

    def test_empty_row_of_departed_teacher_is_lowered_not_deleted(self):
        User = get_user_model()
        with bypass_rls():
            role, _created = Role.objects.get_or_create(
                organization=self.org, name="teacher", defaults={"display_name": "Teacher", "level": 50}
            )
            Role.objects.filter(pk=role.pk).update(
                is_active=True, permissions=["grade.input"], scope_type=RoleScopeType.ORGANIZATION
            )
            teacher = User.objects.create_user("lgh_teacher", "lgh_teacher@x.test", "pw")
            membership = Membership.objects.create(organization=self.org, user=teacher, role=role, is_active=True)
            Lesson.objects.filter(pk=self.empty.pk).update(instructor=teacher)
            Membership.objects.filter(pk=membership.pk).update(is_active=False)
            journal_teacher = User.objects.create_user("lgh_teacher2", "lgh_teacher2@x.test", "pw")
            Membership.objects.create(organization=self.org, user=journal_teacher, role=role, is_active=True)
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=journal_teacher)
        counts, batch = self._call("--apply")
        self.assertEqual((counts["lessons_empty_deleted"], counts["empty_kept_inactive_instructor"]), ("0", "1"))
        self.assertEqual(self._hours()[self.empty.pk], 1)
        undo, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual(undo["undo_hours_restored"], "7")
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=self.empty.pk).instructor_id, teacher.pk)

    def test_journal_teacher_departed_empty_row_is_deleted_and_restored_without_instructor(self):
        User = get_user_model()
        with bypass_rls():
            role, _created = Role.objects.get_or_create(
                organization=self.org, name="teacher", defaults={"display_name": "Teacher", "level": 50}
            )
            Role.objects.filter(pk=role.pk).update(
                is_active=True, permissions=["grade.input"], scope_type=RoleScopeType.ORGANIZATION
            )
            teacher = User.objects.create_user("lgh_teacher3", "lgh_teacher3@x.test", "pw")
            Membership.objects.create(organization=self.org, user=teacher, role=role, is_active=True)
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=teacher)
            Lesson.objects.filter(pk=self.empty.pk).update(instructor=teacher)
            User.objects.filter(pk=teacher.pk).update(is_active=False)
        counts, batch = self._call("--apply")
        self.assertEqual(counts["lessons_empty_deleted"], "1")
        undo, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual((undo["undo_lessons_recreated"], undo["undo_instructor_is_journal_teacher"]), ("1", "1"))
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(pk=self.empty.pk).instructor_id)

    def test_window_mode_keeps_pair_whole_when_its_duplicate_is_empty(self):
        with bypass_rls():
            subject = Subject.objects.create(organization=self.org, code="FIZ", name="Fizika")
            other = CourseOffering.objects.create(
                organization=self.org, subject=subject, period=self.past, group=self.group, lesson_hours=8
            )
            enrollment = Enrollment.objects.create(organization=self.org, student=self.e2.student, offering=other)
            make = self._lesson
            dup_filled, dup_empty = make(D1, T(10, 0), offering=other), make(D1, T(10, 1), offering=other)
            split_a, split_b = make(D2, T(10, 0), offering=other), make(D2, T(10, 50), offering=other)
            pair_a, pair_b = make(D3, T(10, 0), offering=other), make(D3, T(11, 40), offering=other)
            for lesson in (dup_filled, split_a, split_b, pair_a, pair_b):
                self._mark(lesson, enrollment, "absent")
        self._call("--apply")
        hours = self._hours()
        self.assertEqual(hours[dup_filled.pk], 2)  # cütün boş təkrarı silindi, cüt yarıya enmir
        self.assertNotIn(dup_empty.pk, hours)
        self.assertEqual((hours[split_a.pk], hours[split_b.pk]), (1, 1))
        self.assertEqual((hours[pair_a.pk], hours[pair_b.pk]), (2, 2))
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=enrollment.pk).absence_hours, 8)

    def test_corrected_lessons_are_skipped(self):
        with mock.patch.object(service, "corrected_lesson_ids", return_value={str(self.a1.pk)}):
            counts, _ = self._call("--apply")
        self.assertEqual(counts["corrected_lessons_skipped"], "1")
        self.assertEqual(self._hours()[self.a1.pk], 2)

    def test_batch_validation(self):
        with self.assertRaisesMessage(CommandError, "legacy_hours_batch_invalid"):
            self._call("--undo", "--batch", "nope")
        with self.assertRaisesMessage(CommandError, "legacy_hours_batch_needs_undo"):
            self._call("--batch", "lghours-20261117-120000-abcd")
