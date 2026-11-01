"""Real PG: one canonical current handover preserves source cells, old authors and bodies."""

import datetime
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.registrar.journal_assignment_sources import teacher_journal_assignments
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, TeachingHandover

from ..models import TeacherAssignment
from ..services import reviewed_consumer_handover as repair
from ..services import reviewed_consumer_handover_spec as spec
from ..services import reviewed_consumer_handover_state as state
from ..services import reviewed_ilahe_subject_state as actor_state
from ..services.reviewed_leyla_catalog_graph import RepairError, bounded
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class ReviewedConsumerHandoverTests(TestCase):
    def setUp(self):
        self.org = make_org("consumer-handover")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="CO")
        self.task = make_task(self.org, self.stack["chair"], status="amended")
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30, lab_total=0)
        self.old = get_user_model().objects.create_user("old-consumer", first_name="Aydın", last_name="Rəfiyev")
        self.new = get_user_model().objects.create_user("new-consumer", first_name="Ülviyyə", last_name="Xudaverdili")
        for user, patronymic in [(self.old, "Ağaəli"), (self.new, "Ramiz")]:
            activate_member(self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
            user.profile.organization, user.profile.patronymic = self.org, patronymic
            user.profile.save(update_fields=["organization", "patronymic"])
        self.course = CourseOffering.objects.create(
            organization=self.org,
            instructor=self.old,
            subject=self.stack["subject"],
            group=self.stack["group"],
            period=self.stack["period"],
            lesson_hours=60,
        )
        student = get_user_model().objects.create_user("consumer-student")
        activate_member(self.org, student, "student", permissions=["course.view"])
        self.enrollment = Enrollment.objects.create(organization=self.org, offering=self.course, student=student)
        self.lessons = []
        for index in range(9):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.course,
                date=timezone.localdate() - datetime.timedelta(days=index + 1),
                start_time="09:00",
                kind="lecture" if index < 4 else "seminar",
                hours=2,
                instructor=self.old if index == 0 else None,
                created_by=self.old if index == 0 else None,
            )
            self.lessons.append(lesson)
            LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status="present",
                score=0 if index == 8 else None,
                entered_by=self.old if index == 0 else None,
            )
        self.assignments = {
            TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=self.old, activity=kind, hours=30
            ): kind
            for kind in ["lecture", "seminar"]
        }
        values = {
            "ORG": str(self.org.pk),
            "PERIOD": str(self.course.period_id),
            "COURSE": str(self.course.pk),
            "GROUP": str(self.course.group_id),
            "SUBJECT": str(self.course.subject_id),
            "ROW": str(self.row.pk),
            "TASK": str(self.task.pk),
            "CHAIR": str(self.task.chair_id),
            "OLD": self.old.pk,
            "NEW": self.new.pk,
            "NAMES": {self.old.pk: ("Aydın", "Rəfiyev", "Ağaəli"), self.new.pk: ("Ülviyyə", "Xudaverdili", "Ramiz")},
            "ASSIGNMENTS": {str(a.pk): kind for a, kind in self.assignments.items()},
            "COUNTS": {"registrar.Lesson": 9, "registrar.LessonMark": 9, "registrar.Enrollment": 1},
        }
        for key, value in values.items():
            p = patch.object(spec, key, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(state, "PINS", {"bridge": []})
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(actor_state.spec, "ORG", str(self.org.pk))
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual(self.execute()["count"], 1)

    def execute(self, **options):
        return repair.run(organization=self.org, actor=self.actor, **options)

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def assert_hold(self):
        with self.assertRaises(RepairError), transaction.atomic():
            self.execute()
        self.course.refresh_from_db()
        self.assertEqual(self.course.instructor_id, self.old.pk)

    def test_apply_repeat_undo_preserves_academic_rows_and_original_allocation_ids(self):
        with transaction.atomic():
            before = state.snapshot()
            old_assign = bounded(TeacherAssignment.objects.filter(row=self.row))
        self.assertEqual(teacher_journal_assignments(organization=self.org, teacher_id=self.new.pk), {})
        started = timezone.now()
        result = self.apply()
        self.course.refresh_from_db()
        self.assertEqual(self.course.instructor_id, self.new.pk)
        self.assertEqual(
            set(TeacherAssignment.objects.filter(row=self.row, teacher=self.new).values_list("id", flat=True)),
            {a.pk for a in self.assignments},
        )
        self.assertEqual({a.hours for a in TeacherAssignment.objects.filter(row=self.row)}, {30})
        self.assertTrue(teacher_journal_assignments(organization=self.org, teacher_id=self.new.pk))
        event = TeachingHandover.objects.get(offering=self.course)
        self.assertGreaterEqual(event.created_at, started)
        self.assertEqual(event.from_instructor_id, self.old.pk)
        self.assertEqual(event.to_instructor_id, self.new.pk)
        self.assertEqual(self.execute()["count"], 0)
        self.assertEqual(self.execute(apply=True)["status"], "already_applied")
        with transaction.atomic():
            after = state.snapshot(allowed_handover=str(event.pk))
        self.assertEqual(
            state.protected(before, handover_id=str(event.pk)), state.protected(after, handover_id=str(event.pk))
        )
        dry = self.execute(undo=result["receipt"])
        self.execute(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.course.refresh_from_db()
        self.assertEqual(self.course.instructor_id, self.old.pk)
        with transaction.atomic():
            self.assertEqual(bounded(TeacherAssignment.objects.filter(row=self.row)), old_assign)
        event.refresh_from_db()
        self.assertIsNotNone(event.reverted_at)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")

    def test_changed_grade_between_dry_and_apply_is_stale_and_never_overwritten(self):
        baseline = self.execute()["baseline"]
        LessonMark.objects.filter(score=0).update(score=1)
        with self.assertRaisesRegex(RepairError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=baseline)
        self.assertEqual(LessonMark.objects.filter(score=1).count(), 1)

    def test_wrong_teacher_assignment_holds(self):
        TeacherAssignment.objects.filter(pk=next(iter(self.assignments)).pk).update(teacher=self.new)
        self.assert_hold()

    def test_changed_hour_total_holds(self):
        apps.get_model("workload.TeachingTaskRow").objects.filter(pk=self.row.pk).update(lecture_total=29)
        self.assert_hold()

    def test_draft_task_cannot_bypass_approval_chain(self):
        apps.get_model("workload.TeachingTask").objects.filter(pk=self.task.pk).update(status="draft")
        self.assert_hold()

    def test_other_current_owner_holds(self):
        third = get_user_model().objects.create_user("consumer-third-owner")
        activate_member(self.org, third, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        CourseOffering.objects.filter(pk=self.course.pk).update(instructor=third)
        self.assert_hold_no_owner_assert()

    def assert_hold_no_owner_assert(self):
        with self.assertRaises(RepairError), transaction.atomic():
            self.execute()

    def test_active_share_is_not_silently_deactivated(self):
        apps.get_model("registrar.JournalShare").objects.create(
            organization=self.org, offering=self.course, teacher=self.new, kinds=["seminar"], is_active=True
        )
        self.assert_hold()

    def test_unknown_existing_handover_holds(self):
        TeachingHandover.objects.create(
            organization=self.org,
            offering=self.course,
            from_instructor=self.actor,
            to_instructor=self.old,
            performed_by=self.actor,
            reason="Prior unrelated event",
        )
        self.assert_hold()

    def test_changed_source_bridge_holds(self):
        state.PINS["bridge"].append({"legacy_pk": "613", "source_row_hash": "a" * 64})
        self.assert_hold()

    def test_native_canonical_failure_rolls_back_both_assignment_writes(self):
        from apps.registrar.public import handover_actions

        baseline = self.execute()["baseline"]
        with (
            patch.object(handover_actions, "reassign", side_effect=handover_actions.HandoverError("blocked", "no")),
            self.assertRaises(handover_actions.HandoverError),
            transaction.atomic(),
        ):
            self.execute(apply=True, expected_baseline=baseline)
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row, teacher=self.old).count(), 2)
        self.assertFalse(TeachingHandover.objects.filter(offering=self.course).exists())

    def test_new_cell_after_apply_prevents_undo(self):
        result = self.apply()
        LessonMark.objects.filter(score=0).update(score=1)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"), transaction.atomic():
            self.execute(undo=result["receipt"], apply=True, expected_baseline="stale")
        self.course.refresh_from_db()
        self.assertEqual(self.course.instructor_id, self.new.pk)

    def test_inactive_new_teacher_holds(self):
        get_user_model().objects.filter(pk=self.new.pk).update(is_active=False)
        self.assert_hold()

    def test_existing_human_syllabus_body_and_author_are_not_copied_or_approved(self):
        syllabus = apps.get_model("syllabus.Syllabus").objects.create(
            organization=self.org,
            subject=self.course.subject,
            period=self.course.period,
            offering=self.course,
            author=self.old,
            chair_unit=self.stack["chair"],
        )
        version = apps.get_model("syllabus.SyllabusVersion").objects.create(
            organization=self.org,
            syllabus=syllabus,
            created_by=self.old,
            applies_to_period=self.course.period,
            plan_hours={"lecture": 30, "seminar": 30},
        )
        section = apps.get_model("syllabus.SyllabusSection").objects.create(
            organization=self.org,
            version=version,
            section_id="week",
            data={"rows": [{"topic": "Existing authored body", "lecture": 30, "seminar": 30}]},
        )
        apps.get_model("syllabus.Syllabus").objects.filter(pk=syllabus.pk).update(current_version=version)
        with transaction.atomic():
            before = state.snapshot()
        self.apply()
        section.refresh_from_db()
        version.refresh_from_db()
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.author_id, self.old.pk)
        self.assertEqual(version.status, "draft")
        self.assertEqual(section.data["rows"][0]["topic"], "Existing authored body")
        self.assertEqual(apps.get_model("syllabus.Syllabus").objects.filter(offering=self.course).count(), 1)
        with transaction.atomic():
            after = state.snapshot(allowed_handover=str(TeachingHandover.objects.get(offering=self.course).pk))
        for label in ["syllabus.Syllabus", "syllabus.SyllabusVersion", "syllabus.SyllabusSection"]:
            self.assertEqual(before["graph"][label], after["graph"][label])

    def test_other_positive_matching_row_never_gets_overwritten(self):
        other = make_row(self.task, self.stack, lecture_total=30, seminar_total=30, lab_total=0)
        TeacherAssignment.objects.create(
            organization=self.org, row=other, teacher=self.new, activity="lecture", hours=30
        )
        self.assert_hold()

    def test_unknown_new_current_lesson_is_not_absorbed(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.course,
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
            instructor=self.old,
        )
        self.assert_hold()

    def test_wrong_tenant_or_nonadmin_actor_is_refused(self):
        with self.assertRaises(RepairError), transaction.atomic():
            repair.run(organization=self.org, actor=self.old)
        self.course.refresh_from_db()
        self.assertEqual(self.course.instructor_id, self.old.pk)
