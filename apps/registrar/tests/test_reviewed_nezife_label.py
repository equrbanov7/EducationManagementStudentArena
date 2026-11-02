import datetime as dt
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.organizations.models import Membership
from apps.registrar import reviewed_nezife_label as op
from apps.registrar.models import Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.registrar.tests import test_teacher_journal_visibility as fixtures


class NezifeExactScheduleLabelTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering

    def setUp(self):
        self.actor = self.org.owner
        self.actor.profile.organization = self.org
        self.actor.profile.access_state = "active"
        self.actor.profile.save()
        self.teacher.username, self.teacher.first_name, self.teacher.last_name = "nezife.asirova", "Nəzifə", "Aşırova"
        self.teacher.save()
        self.teacher.profile.patronymic = "Vilayət"
        self.teacher.profile.save(update_fields=["patronymic"])
        self.course = self.offering(instructor=self.teacher)
        self.room = apps.get_model("exams.ExamRoom").objects.create(organization=self.org, name="53", code="53")
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.course,
            instructor=self.teacher,
            date=dt.date(2026, 10, 21),
            start_time=dt.time(11, 50),
            end_time=dt.time(13, 20),
            kind="seminar",
            hours=2,
            room=self.room,
            off_schedule_reason=op.REASON,
        )
        self.slot = ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.course,
            weekday=3,
            start_time=dt.time(11, 50),
            end_time=dt.time(13, 20),
            kind="seminar",
            week_type="all",
            room="53",
        )
        for i in range(21):
            student = get_user_model().objects.create_user("nezife-label-student" + str(i))
            Membership.objects.create(organization=self.org, user=student, role=self.org.roles.get(name="student"))
            enrollment = Enrollment.objects.create(organization=self.org, offering=self.course, student=student)
            LessonMark.objects.create(
                organization=self.org,
                lesson=self.lesson,
                enrollment=enrollment,
                status="absent" if i == 0 else "present",
                score=0 if i == 1 else None,
            )
        self.other = Lesson.objects.create(
            organization=self.org,
            offering=self.course,
            date=dt.date(2026, 10, 20),
            kind="lecture",
            off_schedule_reason="Other unrelated exception",
        )
        values = dict(
            ORG=str(self.org.pk),
            PERIOD=str(self.course.period_id),
            OFFERING=str(self.course.pk),
            GROUP=str(self.course.group_id),
            SUBJECT=str(self.course.subject_id),
            TEACHER=self.teacher.pk,
            LESSON=str(self.lesson.pk),
            SLOT=str(self.slot.pk),
            ROOM=self.room.pk,
        )
        for key, value in values.items():
            p = patch.object(op, key, value)
            p.start()
            self.addCleanup(p.stop)

    def execute(self, **kwargs):
        return op.run(organization=self.org, user=self.actor, **kwargs)

    def test_apply_repeat_and_exact_undo_preserve_full_academic_graph(self):
        with transaction.atomic():
            before = op.snapshot(self.org, self.actor)
        dry = self.execute()
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.off_schedule_reason, op.REASON)
        apply = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.off_schedule_reason, "")
        with transaction.atomic():
            after = op.snapshot(self.org, self.actor)
        self.assertEqual(op.protected(before), op.protected(after))
        self.assertEqual(self.execute()["status"], "already_applied")
        undo = self.execute(undo=apply["receipt"])
        self.execute(undo=apply["receipt"], apply=True, expected_baseline=undo["baseline"])
        with transaction.atomic():
            self.assertEqual(op.snapshot(self.org, self.actor), before)
        self.assertEqual(self.execute(undo=apply["receipt"])["status"], "already_undone")

    def test_fresh_changed_mark_blocks_stale_apply(self):
        dry = self.execute()
        LessonMark.objects.filter(lesson=self.lesson, score=0).update(score=1)
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.off_schedule_reason, op.REASON)

    def test_changed_schedule_time_holds(self):
        ScheduleSlot.objects.filter(pk=self.slot.pk).update(start_time=dt.time(13, 35))
        with self.assertRaisesRegex(ValueError, "schedule_changed"), transaction.atomic():
            self.execute()

    def test_changed_reason_date_or_kind_holds(self):
        Lesson.objects.filter(pk=self.lesson.pk).update(off_schedule_reason="Teacher replacement")
        with self.assertRaisesRegex(ValueError, "lesson_changed"), transaction.atomic():
            self.execute()

    def test_undo_after_mark_change_holds(self):
        apply = self.execute(apply=True, expected_baseline=self.execute()["baseline"])
        LessonMark.objects.filter(lesson=self.lesson, score=0).update(score=8)
        with self.assertRaisesRegex(ValueError, "undo_changed"), transaction.atomic():
            self.execute(undo=apply["receipt"])

    def test_atomic_graph_guard_failure_rolls_back_label(self):
        dry = self.execute()
        real = op.protected
        count = [0]

        def changed(value):
            count[0] += 1
            result = real(value)
            if count[0] == 2:
                result["unexpected_change"] = True
            return result

        with (
            patch.object(op, "protected", side_effect=changed),
            self.assertRaisesRegex(ValueError, "academic_graph_changed"),
            transaction.atomic(),
        ):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.off_schedule_reason, op.REASON)

    def test_inactive_actor_or_wrong_tenant_refused(self):
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaisesRegex(ValueError, "actor_scope"), transaction.atomic():
            self.execute()

    def test_parked_slot_cannot_clear_label(self):
        ScheduleSlot.objects.filter(pk=self.slot.pk).update(is_parked=True)
        with self.assertRaisesRegex(ValueError, "schedule_changed"), transaction.atomic():
            self.execute()

    def test_room_rename_or_changed_roster_mark_count_holds(self):
        self.room.name = "Different room"
        self.room.save(update_fields=["name"])
        with self.assertRaisesRegex(ValueError, "room_changed"), transaction.atomic():
            self.execute()
        self.room.name = "53"
        self.room.save(update_fields=["name"])
        LessonMark.objects.filter(lesson=self.lesson).first().delete()
        with self.assertRaisesRegex(ValueError, "mark_inventory_changed"), transaction.atomic():
            self.execute()

    def test_cross_tenant_actor_profile_refused(self):
        self.actor.profile.organization = None
        self.actor.profile.save(update_fields=["organization"])
        with self.assertRaisesRegex(ValueError, "actor_tenant"), transaction.atomic():
            self.execute()
