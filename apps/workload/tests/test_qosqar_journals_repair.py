"""One migrated-PG receipt owns both source schedules and both reviewed Qoşqar corrections."""

import io
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.syllabus.models import SyllabusShare
from apps.workload.models import TeacherAssignment
from apps.workload.services import qosqar_journals_repair as service
from apps.workload.services import qosqar_reviewed_workload as workload_review
from apps.workload.tests import test_qosqar_modelling_repair as modelling_fixture
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import make_row


class QosqarJournalsTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        modelling_fixture.QosqarModellingTests.prepare(self)
        self.org.refresh_from_db()
        state, common, mod = service.state, service.state.duplicate, service.state.modelling
        self.target, self.source, self.anchor = self.offerings
        keep = make_row(self.task, self.stack, lecture_total=45, seminar_total=45)
        keep.lecture_plan = keep.seminar_plan = 45
        keep.total_hours = 90
        keep.save()
        duplicate = make_row(
            self.task, {**self.stack, "subject": self.source.subject}, lecture_total=45, seminar_total=45
        )
        duplicate.lecture_plan = duplicate.seminar_plan = 45
        duplicate.total_hours = 90
        duplicate.save()
        for row in (keep, duplicate):
            for kind in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=self.org,
                    row=row,
                    teacher=self.teacher,
                    activity=kind,
                    hours=45,
                    is_hourly_paid=row == duplicate,
                )
        self.other_source = CourseOffering.objects.create(
            organization=self.org,
            subject=self.source.subject,
            period=self.anchor.period,
            group=self.anchor.group,
            instructor=self.teacher,
            lesson_hours=90,
        )
        Enrollment.objects.create(organization=self.org, offering=self.other_source, student=self.actor)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.anchor, date="2026-10-13", start_time="13:35", kind="seminar"
        )
        self.anchor_mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=self.anchor.enrollments.get(), status="present", score=7
        )
        for key, value in {
            "TASK": str(self.task.pk),
            "PERIOD": str(self.anchor.period_id),
            "TEACHER": self.teacher.pk,
            "SUBJECT": str(self.anchor.subject_id),
            "DUPLICATE_SUBJECT": str(self.source.subject_id),
            "FILLED": str(self.anchor.pk),
            "EMPTY": str(self.other_source.pk),
            "KEEP_ROW": str(keep.pk),
            "REMOVE_ROW": str(duplicate.pk),
        }.items():
            self.patches.enter_context(patch.object(common, key, value))
        self.patches.enter_context(
            patch.object(
                service.schedule.single,
                "PAIRS",
                {str(self.source.pk): str(self.target.pk), str(self.other_source.pk): str(self.anchor.pk)},
            )
        )
        for offering in (self.source, self.other_source):
            for day, start, end, week, kind, room in service.schedule.SIGNATURES:
                ScheduleSlot.all_objects.create(
                    organization=self.org,
                    offering=offering,
                    weekday=day,
                    start_time=start,
                    end_time=end,
                    week_type=week,
                    kind=kind,
                    room=room,
                    created_by=self.teacher,
                )
        type(keep).objects.filter(pk__in=(keep.pk, duplicate.pk, self.row.pk)).update(credits=7)
        self.keep, self.duplicate = keep, duplicate
        self.state, self.mod = state, mod
        self.patches.enter_context(
            patch.object(
                workload_review,
                "RETIRING_ASSIGNMENTS",
                set(map(str, duplicate.assignments.values_list("pk", flat=True))),
            )
        )

    def call(self, **kwargs):
        return service.repair_qosqar_journals(
            organization=self.org, user=self.actor, sections=self.sections, source_sha256=self.mod.SOURCE_SHA, **kwargs
        )

    def test_all_eight_sources_park_before_first_target_and_exact_id_undo(self):
        self.prepare()
        before = self.state.capture()
        source_ids = set(ScheduleSlot.all_objects.values_list("id", flat=True))
        original = service.schedule.single.schedule.create_slot

        def check_parked(**fields):
            self.assertEqual(ScheduleSlot.all_objects.filter(pk__in=source_ids, is_parked=False).count(), 0)
            return original(**fields)

        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_create"], 8)
        self.assertEqual(self.state.digest(before), self.state.digest(self.state.capture()))
        with patch.object(service.schedule.single.schedule, "create_slot", side_effect=check_parked):
            result = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["schedule_slots_created"], 8)
        self.assertEqual(ScheduleSlot.all_objects.filter(pk__in=source_ids, is_parked=True).count(), 8)
        self.assertEqual(
            ScheduleSlot.objects.filter(offering__in=(self.target, self.anchor), is_parked=False).count(), 8
        )
        self.assertEqual(self.call()["already_present"], 1)
        self.target.refresh_from_db()
        self.assertEqual(self.target.subject_id, self.anchor.subject_id)
        self.assertFalse(type(self.duplicate).objects.filter(pk=self.duplicate.pk).exists())
        for mark in (self.mark, self.anchor_mark):
            mark.refresh_from_db()
            self.assertIn(mark.score, (7, 8))
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        after = self.state.capture()
        for key in ("rows", "groups", "group_links", "assignments", "subjects"):
            self.assertEqual(self.state.digest(before[key]), self.state.digest(after[key]), key)
        self.assertEqual(
            self.state.digest(self.state.protected(before)), self.state.digest(self.state.protected(after))
        )
        for label in (
            "registrar.Lesson",
            "registrar.LessonMark",
            "registrar.Enrollment",
            "syllabus.Syllabus",
            "syllabus.SyllabusVersion",
        ):
            self.assertEqual(
                self.state.digest(before["academic"].get(label, [])),
                self.state.digest(after["academic"].get(label, [])),
                label,
            )
        self.assertEqual(ScheduleSlot.all_objects.filter(pk__in=source_ids, is_parked=False).count(), 8)
        self.assertEqual(ScheduleSlot.all_objects.exclude(pk__in=source_ids).filter(is_parked=True).count(), 8)

    def test_partial_second_pair_copy_failure_rolls_back_everything(self):
        self.prepare()
        before = self.state.capture()
        dry = self.call()
        original = service.schedule.single.schedule.create_slot
        count = 0

        def fail_second_pair(**fields):
            nonlocal count
            count += 1
            if count == 6:
                raise ValueError("forced second pair failure")
            return original(**fields)

        with patch.object(service.schedule.single.schedule, "create_slot", side_effect=fail_second_pair):
            with self.assertRaisesRegex(ValueError, "forced second pair"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.state.digest(before), self.state.digest(self.state.capture()))
        self.assertFalse(SyllabusShare.objects.filter(offering=self.target).exists())

    def test_both_hygiene_and_configuration_rows_are_byte_identical(self):
        self.prepare()
        for source in (self.source, self.other_source):
            enrollment = source.enrollments.get()
            Enrollment.objects.filter(pk=enrollment.pk).update(status="dropped")
            self.state.model("registrar.JournalHygieneDecision").objects.create(
                organization=self.org,
                enrollment=enrollment,
                batch=uuid4(),
                category="empty_subject",
                reason_code="reviewed_empty",
                from_status="enrolled",
                to_status="dropped",
                evidence={"preserve": "unchanged"},
                evidence_digest="1" * 64,
                reason="Reviewed historical decision to preserve",
                decided_by=self.actor,
            )
            self.state.model("registrar.AssessmentScheme").objects.create(organization=self.org, offering=source)
        before = self.state.capture()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        after = self.state.capture()
        for label in ("registrar.JournalHygieneDecision", "registrar.AssessmentScheme", "registrar.Enrollment"):
            self.assertEqual(self.state.digest(before["academic"][label]), self.state.digest(after["academic"][label]))

    def test_live_outside_room_or_teacher_conflict_is_never_excluded(self):
        self.prepare()
        # Exact signature but unrelated subject: it is not one of the reviewed source IDs.
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.target,
            weekday=5,
            start_time="13:35",
            end_time="15:05",
            week_type="odd",
            kind="lecture",
            room="35",
        )
        with self.assertRaisesRegex(ValueError, "external_conflict"):
            self.call()
        self.assertEqual(ScheduleSlot.objects.filter(is_parked=True).count(), 0)

    def test_source_slot_target_slot_or_source_proof_drift_refused(self):
        self.prepare()
        dry = self.call()
        slot = ScheduleSlot.objects.filter(offering=self.source).first()
        ScheduleSlot.objects.filter(pk=slot.pk).update(room="Other")
        with self.assertRaisesRegex(ValueError, "baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(ValueError, "four_slot_signature"):
            self.call()
        with self.assertRaisesRegex(ValueError, "source6591"):
            service.repair_qosqar_journals(
                organization=self.org, user=self.actor, sections=self.sections, source_sha256="0" * 64
            )

    def test_individual_repairs_remain_fail_closed_for_cross_pair_conflict(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "reviewed_schedule_conflict"):
            service.schedule.single.plan(str(self.source.pk), str(self.target.pk))
        with self.assertRaisesRegex(ValueError, "reviewed_schedule_conflict"):
            service.schedule.single.plan(str(self.other_source.pk), str(self.anchor.pk))

    def test_undo_blocks_new_history_and_source_values_remain_unchanged(self):
        self.prepare()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        LessonMark.objects.filter(pk=self.mark.pk).update(score=6)
        with self.assertRaisesRegex(ValueError, "undo_receipt_or_live_state_changed"):
            self.call(undo=True)
        self.assertEqual(
            ScheduleSlot.objects.filter(offering__in=(self.source, self.other_source), is_parked=False).count(), 0
        )

    def test_command_default_dry_run_and_digest_baseline_arguments(self):
        self.prepare()
        kwargs = dict(
            org=self.org.slug,
            actor=self.actor.username,
            file="private-source-file",
            sha256=self.mod.SOURCE_SHA,
            stdout=io.StringIO(),
        )
        with patch(
            "apps.legacy_import.management.commands.repair_qosqar_journals.qosqar_modelling_evidence.load",
            return_value=(self.sections, self.mod.SOURCE_SHA),
        ):
            call_command("repair_qosqar_journals", **kwargs)
            self.assertIn("qosqar_journals: mode=dry_run", kwargs["stdout"].getvalue())
            with self.assertRaisesRegex(CommandError, "fresh_live_baseline_required"):
                call_command("repair_qosqar_journals", apply=True, **kwargs)

    def test_exact_existing_canonical_target_reused_and_undo_retains_its_metadata(self):
        self.prepare()
        day, start, end, week, kind, room = sorted(service.schedule.SIGNATURES)[0]
        existing = ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.anchor,
            weekday=day,
            start_time=start,
            end_time=end,
            week_type=week,
            kind=kind,
            room=room,
        )
        original = self.state.records(ScheduleSlot.all_objects.filter(pk=existing.pk))
        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_create"], 7)
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(original, self.state.records(ScheduleSlot.all_objects.filter(pk=existing.pk)))
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(original, self.state.records(ScheduleSlot.all_objects.filter(pk=existing.pk)))

    def test_actual_empty_side_grade_history_and_partial_old_repair_refused(self):
        self.prepare()
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.other_source, date="2026-10-13", kind="lecture"
        )
        with self.assertRaisesRegex(ValueError, "empty_offering_has_content_or_history"):
            self.call()
        lesson.delete()
        self.mod._subject(self.target, self.mod.OLD, self.mod.NEW)
        with self.assertRaisesRegex(ValueError, "fixed_offering_identity_changed"):
            self.call()
        self.assertEqual(ScheduleSlot.objects.filter(is_parked=True).count(), 0)

    def test_target_schedule_drift_and_noncanonical_source_sections_fail(self):
        self.prepare()
        dry = self.call()
        ScheduleSlot.objects.create(
            organization=self.org, offering=self.anchor, weekday=1, start_time="10:00", end_time="11:30", kind="lecture"
        )
        with self.assertRaisesRegex(ValueError, "baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(ValueError, "target_schedule_signature_changed"):
            self.call()
        with self.assertRaisesRegex(ValueError, "source6591"):
            service.repair_qosqar_journals(
                organization=self.org, user=self.actor, sections={"modified": True}, source_sha256=self.mod.SOURCE_SHA
            )

    def test_reviewed_credit_multiplier_and_other_hours_are_guarded(self):
        self.prepare()
        type(self.duplicate).objects.filter(pk=self.duplicate.pk).update(credits=6)
        with self.assertRaisesRegex(ValueError, "credit_multiplier_or_other_hours"):
            self.call()
        type(self.duplicate).objects.filter(pk=self.duplicate.pk).update(credits=7, exam_hours=1)
        with self.assertRaisesRegex(ValueError, "credit_multiplier_or_other_hours"):
            self.call()

    def test_canonical_review_history_preserved_and_new_review_blocks_undo(self):
        self.prepare()
        cls = self.state.model("workload.TaskRowReview")
        review = cls.objects.create(organization=self.org, row=self.keep, coordinator=self.actor, status="reviewed")
        original = self.state.records(cls.objects.filter(pk=review.pk))
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(original, self.state.records(cls.objects.filter(pk=review.pk)))
        cls.objects.create(organization=self.org, row=self.row, coordinator=self.actor, status="reviewed")
        with self.assertRaisesRegex(ValueError, "undo_receipt_or_live_state_changed"):
            self.call(undo=True)

    def test_wrong_row_existing_review_history_is_not_deleted(self):
        self.prepare()
        cls = self.state.model("workload.TaskRowReview")
        review = cls.objects.create(
            organization=self.org, row=self.duplicate, coordinator=self.actor, status="reviewed"
        )
        original = self.state.records(cls.objects.filter(pk=review.pk))
        with self.assertRaisesRegex(ValueError, "duplicate_row_has_history"):
            self.call()
        self.assertEqual(original, self.state.records(cls.objects.filter(pk=review.pk)))

    def zero_choice(self):
        choice = make_row(self.task, {**self.stack, "subject": self.source.subject}, lecture_total=0, seminar_total=0)
        choice.groups.set([self.target.group])
        for key, value in {
            "subject_text": "ATMF XII blok: \n1.Kompüterlərdə modelləşdirmə\n2. Avtomatlar nəzəriyyəsi",
            "groups_text": "233 İT",
            "lecture_plan": 45,
            "seminar_plan": 45,
            "total_hours": 0,
            "union_count": 0,
            "subgroup_count": 0,
            "credits": 7,
            "student_count": 17,
        }.items():
            setattr(choice, key, value)
        choice.save()
        self.patches.enter_context(patch.object(workload_review, "ZERO_CHOICE_ROW", str(choice.pk)))
        return choice

    def test_exact_zero_choice_and_paid_retirement_provenance_survive_apply_undo(self):
        self.prepare()
        choice = self.zero_choice()
        before = self.state.capture()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(type(choice).objects.filter(pk=choice.pk, total_hours=0).exists())
        self.assertFalse(TeacherAssignment.objects.filter(row_id=self.duplicate.pk).exists())
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        after = self.state.capture()
        for key in ("rows", "groups", "group_links", "assignments"):
            self.assertEqual(self.state.digest(before[key]), self.state.digest(after[key]))
        self.assertEqual(TeacherAssignment.objects.filter(row_id=self.duplicate.pk, is_hourly_paid=True).count(), 2)
        self.assertFalse(TeacherAssignment.objects.filter(row=self.keep, is_hourly_paid=True).exists())

    def test_zero_choice_positive_load_assignment_or_identity_drift_holds(self):
        self.prepare()
        choice = self.zero_choice()
        for changes in ({"lecture_total": 1}, {"subject_text": "Other choice"}, {"subgroup_count": 1}):
            original = {key: getattr(choice, key) for key in changes}
            type(choice).objects.filter(pk=choice.pk).update(**changes)
            with self.assertRaisesRegex(ValueError, "zero_choice_workload_changed"):
                self.call()
            type(choice).objects.filter(pk=choice.pk).update(**original)
        type(choice).objects.filter(pk=choice.pk).update(lecture_total=1)
        TeacherAssignment.objects.create(
            organization=self.org, row=choice, teacher=self.teacher, activity="lecture", hours=1
        )
        with self.assertRaisesRegex(ValueError, "zero_choice_workload_changed"):
            self.call()

    def test_pay_basis_guard_is_exact_for_retiring_and_retained_rows(self):
        self.prepare()
        for row, changed, original in ((self.duplicate, False, True), (self.keep, True, False)):
            row.assignments.update(is_hourly_paid=changed)
            with self.assertRaisesRegex(ValueError, "pay_basis_changed"):
                self.call()
            row.assignments.update(is_hourly_paid=original)

    def test_recreated_retiring_assignment_with_same_quantity_is_not_whitelisted(self):
        self.prepare()
        item = self.duplicate.assignments.get(activity="lecture")
        item.delete()
        TeacherAssignment.objects.create(
            organization=self.org,
            row=self.duplicate,
            teacher=self.teacher,
            activity="lecture",
            hours=45,
            is_hourly_paid=True,
        )
        with self.assertRaisesRegex(ValueError, "retiring_assignment_ids_changed"):
            self.call()
