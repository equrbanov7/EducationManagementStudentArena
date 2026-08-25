"""Tests for the timetable (schedule) service (U4): conflict detection + views data."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, services
from apps.registrar.models import ScheduleSlot, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

T9 = datetime.time(9, 0)
T1030 = datetime.time(10, 30)
T10 = datetime.time(10, 0)
T1130 = datetime.time(11, 30)


class ScheduleServiceTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("sc_owner", "sc_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="SC Univ",
                slug="sc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="sc-g1", unit_type=OrgUnitType.GROUP
            )
            self.group2 = OrgUnit.objects.create(
                organization=self.org, name="G2", slug="sc-g2", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.teacher = User.objects.create_user("sc_teacher", "sc_teacher@qku.edu.az", "pw")
            self.teacher2 = User.objects.create_user("sc_teacher2", "sc_teacher2@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.teacher2,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            self.math = Subject.objects.create(organization=self.org, code="MATH", name="Riyaziyyat")
            self.phys = Subject.objects.create(organization=self.org, code="PHYS", name="Fizika")
            self.off1 = services.get_or_create_offering(
                organization=self.org, subject=self.math, period=self.period, group=self.group
            )
            self.off1.instructor = self.teacher
            self.off1.save(update_fields=["instructor"])

    def _off(self, subject, group, instructor):
        off = services.get_or_create_offering(organization=self.org, subject=subject, period=self.period, group=group)
        off.instructor = instructor
        off.save(update_fields=["instructor"])
        return off

    def test_create_slot(self):
        with bypass_rls():
            slot = schedule.create_slot(
                offering=self.off1, weekday=1, start_time=T9, end_time=T1030, room="201", created_by=self.teacher
            )
            self.assertEqual(ScheduleSlot.objects.count(), 1)
            self.assertEqual(slot.room, "201")

    def test_same_group_overlap_conflicts(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=1, start_time=T9, end_time=T1030)
            # Another subject for the same group, overlapping time.
            off2 = self._off(self.phys, self.group, self.teacher2)
            with self.assertRaises(schedule.ScheduleConflict):
                schedule.create_slot(offering=off2, weekday=1, start_time=T10, end_time=T1130)

    def test_same_instructor_overlap_conflicts(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=2, start_time=T9, end_time=T1030)
            # Same teacher, a different group, overlapping time.
            off2 = self._off(self.phys, self.group2, self.teacher)
            with self.assertRaises(schedule.ScheduleConflict):
                schedule.create_slot(offering=off2, weekday=2, start_time=T10, end_time=T1130)

    def test_same_room_overlap_conflicts(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=3, start_time=T9, end_time=T1030, room="305")
            off2 = self._off(self.phys, self.group2, self.teacher2)  # different group + teacher
            with self.assertRaises(schedule.ScheduleConflict):
                schedule.create_slot(offering=off2, weekday=3, start_time=T10, end_time=T1130, room="305")

    def test_no_conflict_different_day_or_time_or_weektype(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=1, start_time=T9, end_time=T1030, week_type=WeekType.ODD)
            off2 = self._off(self.phys, self.group, self.teacher)  # same group + teacher
            # Different weekday → ok.
            schedule.create_slot(offering=off2, weekday=2, start_time=T9, end_time=T1030)
            # Non-overlapping time same day → ok.
            schedule.create_slot(offering=off2, weekday=1, start_time=T1030, end_time=T1130)
            # Even week vs the odd-week slot at the same time → ok.
            schedule.create_slot(offering=off2, weekday=1, start_time=T9, end_time=T1030, week_type=WeekType.EVEN)
            self.assertEqual(ScheduleSlot.objects.count(), 4)

    def test_group_and_teacher_schedule_and_grid(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=1, start_time=T9, end_time=T1030)
            schedule.create_slot(offering=self.off1, weekday=3, start_time=T9, end_time=T1030)
            group_slots = schedule.get_group_schedule(organization=self.org, group=self.group, period=self.period)
            teacher_slots = schedule.get_teacher_schedule(
                organization=self.org, teacher=self.teacher, period=self.period
            )
            self.assertEqual(len(group_slots), 2)
            self.assertEqual(len(teacher_slots), 2)
            grid = schedule.build_week_grid(group_slots)
            monday = next(d for d in grid if d["weekday"] == 1)
            self.assertEqual(len(monday["slots"]), 1)

    # ── Konkret həftə: tarixlər + üst/alt həftə + imtahanlar ──────────────────
    def test_week_parity_anchored_to_period_start(self):
        # 2024-09-01 is a Sunday → its week's Monday is 2024-08-26 (week 1 = odd/üst).
        first_monday = datetime.date(2024, 8, 26)
        self.assertEqual(schedule.week_parity(self.period, first_monday), WeekType.ODD)
        self.assertEqual(schedule.week_parity(self.period, first_monday + datetime.timedelta(weeks=1)), WeekType.EVEN)
        self.assertEqual(schedule.week_parity(self.period, first_monday + datetime.timedelta(weeks=2)), WeekType.ODD)

    def test_build_week_context_shape(self):
        ctx = schedule.build_week_context(self.period, offset=0)
        self.assertTrue(ctx["is_current"])
        self.assertEqual(ctx["monday"].weekday(), 0)  # Monday
        self.assertEqual((ctx["sunday"] - ctx["monday"]).days, 6)
        self.assertIn(ctx["parity"], {WeekType.ODD, WeekType.EVEN})
        self.assertEqual(len(ctx["dates"]), 6)  # Mon–Sat teaching days

    def test_build_week_view_marks_off_week_slots(self):
        with bypass_rls():
            schedule.create_slot(offering=self.off1, weekday=1, start_time=T9, end_time=T1030, week_type=WeekType.ODD)
            slots = schedule.get_group_schedule(organization=self.org, group=self.group, period=self.period)
        ctx = schedule.build_week_context(self.period, offset=0)
        days = schedule.build_week_view(slots, week_context=ctx)
        monday = next(d for d in days if d["weekday"] == 1)
        self.assertEqual(len(monday["slots"]), 1)
        # The odd-week slot applies only when the current week is odd.
        self.assertEqual(monday["slots"][0]["this_week"], ctx["parity"] == WeekType.ODD)

    def test_get_week_exams_groups_by_weekday(self):
        from django.utils import timezone

        from apps.exams.models import Exam

        monday = schedule._week_monday(0)
        wednesday = monday + datetime.timedelta(days=2)
        start = timezone.make_aware(datetime.datetime.combine(wednesday, datetime.time(10, 0)))
        with bypass_rls():
            exam = Exam.objects.create(
                organization=self.org,
                author=self.teacher,
                title="Aralıq imtahan",
                exam_type="written",
                start_datetime=start,
                end_datetime=start + datetime.timedelta(hours=1),
                is_active=True,
            )
            by_day = schedule.get_week_exams(organization=self.org, course_ids=[], author=self.teacher, monday=monday)
        self.assertIn(3, by_day)  # Wednesday
        self.assertEqual(by_day[3][0]["exam"].id, exam.id)

    def test_get_week_exams_excludes_other_weeks(self):
        from django.utils import timezone

        from apps.exams.models import Exam

        monday = schedule._week_monday(0)
        next_week_wed = monday + datetime.timedelta(days=9)
        start = timezone.make_aware(datetime.datetime.combine(next_week_wed, datetime.time(10, 0)))
        with bypass_rls():
            Exam.objects.create(
                organization=self.org,
                author=self.teacher,
                title="Gələn həftə imtahanı",
                exam_type="written",
                start_datetime=start,
                end_datetime=start + datetime.timedelta(hours=1),
                is_active=True,
            )
            by_day = schedule.get_week_exams(organization=self.org, course_ids=[], author=self.teacher, monday=monday)
        self.assertEqual(by_day, {})
