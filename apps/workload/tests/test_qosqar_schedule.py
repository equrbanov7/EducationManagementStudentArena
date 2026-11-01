"""Both fixed repairs preserve schedules, academic history, metadata and undo identities."""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    JournalShare,
    Lesson,
    ScheduleSlot,
    TeachingHandover,
)
from apps.workload.services import (
    qosqar_duplicate_state,
    qosqar_modelling_repair,
    qosqar_schedule,
)
from apps.workload.tests import test_qosqar_duplicate_repair as duplicate_fixture
from apps.workload.tests import test_qosqar_modelling_repair as modelling_fixture
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import TEACHER_PERMS, activate_member


class ScheduleCases:
    def slot(self, offering=None, **values):
        fields = dict(
            organization=self.org,
            offering=offering or self.source,
            weekday=2,
            start_time="08:30",
            end_time="10:00",
            room="101",
            kind="lecture",
            week_type="all",
            created_by=self.teacher,
        )
        fields.update(values)
        return ScheduleSlot.all_objects.create(**fields)

    def test_active_slots_copied_original_ids_and_inactive_metadata_preserved_then_undo(self):
        self.prepare()
        first = self.slot()
        second = self.slot(weekday=4, kind="seminar")
        parked = self.slot(weekday=5, is_parked=True, park_reason="Existing operator decision")
        deleted = self.slot(weekday=6, is_deleted=True)
        retained = self.slot(
            self.target, weekday=3, start_time="13:35", end_time="15:05", kind="seminar", is_parked=True
        )
        before = self.capture()
        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_park"], 2)
        self.assertEqual(dry["schedule_slots_to_create"], 2)
        self.assertEqual(qosqar_schedule.state.digest(before), qosqar_schedule.state.digest(self.capture()))
        result = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["schedule_slots_parked"], 2)
        for slot in (first, second):
            slot.refresh_from_db()
            self.assertTrue(slot.is_parked)
            self.assertEqual(slot.offering_id, self.source.pk)
        current = self.capture()
        receipt = (
            qosqar_schedule.state.model("audit.AuditLog")
            .objects.filter(
                organization=self.org,
                resource_type__in=("workload.qosqar_modelling_source_correction", "workload.qosqar_current_duplicate"),
            )
            .latest("created_at")
        )
        self.assertEqual(
            qosqar_schedule.state.digest(receipt.new_values["before"]["schedule"]),
            qosqar_schedule.state.digest(before["schedule"]),
        )
        self.assertEqual(
            qosqar_schedule.state.digest(receipt.new_values["schedule_after"]),
            qosqar_schedule.state.digest(current["schedule"]),
        )
        originals = {str(row["id"]): row for row in before["schedule"]}
        after = {str(row["id"]): row for row in current["schedule"]}
        for slot in (parked, deleted, retained):
            self.assertEqual(
                qosqar_schedule.state.digest(originals[str(slot.pk)]), qosqar_schedule.state.digest(after[str(slot.pk)])
            )
        created = set(after) - set(originals)
        self.assertEqual(len(created), 2)
        self.assertEqual(self.call()["already_present"], 1)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        restored = {str(row["id"]): row for row in self.capture()["schedule"]}
        for pk, row in originals.items():
            self.assertEqual(qosqar_schedule.state.digest(row), qosqar_schedule.state.digest(restored[pk]))
        for pk in created:
            self.assertTrue(restored[pk]["is_parked"])
            self.assertFalse(restored[pk]["is_deleted"])
        self.assertEqual(self.target.lessons.first().marks.count(), 1)

    def test_exact_existing_target_reused_and_undo_restores_original_duplicate(self):
        self.prepare()
        source = self.slot()
        target = self.slot(self.target)
        before = self.capture()
        dry = self.call()
        self.assertEqual(dry["schedule_slots_to_create"], 0)
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(ScheduleSlot.all_objects.filter(offering__in=(self.source, self.target)).count(), 2)
        source.refresh_from_db()
        target.refresh_from_db()
        self.assertTrue(source.is_parked)
        self.assertFalse(target.is_parked)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(
            qosqar_schedule.state.digest(before["schedule"]), qosqar_schedule.state.digest(self.capture()["schedule"])
        )

    def test_nonoverlapping_existing_same_kind_timetable_refuses_atomically(self):
        self.prepare()
        source = self.slot()
        target = self.slot(self.target, weekday=3, start_time="13:35", end_time="15:05")
        before = self.capture()
        baseline = qosqar_schedule.state.digest(before)
        for apply in (False, True):
            with self.assertRaisesMessage(
                qosqar_schedule.state.DuplicateError, "reviewed_schedule_competing_kind_timetables"
            ):
                self.call(apply=apply, expected_baseline=baseline)
            self.assertEqual(qosqar_schedule.state.digest(before), qosqar_schedule.state.digest(self.capture()))
        source.refresh_from_db()
        target.refresh_from_db()
        self.assertFalse(source.is_parked)
        self.assertFalse(target.is_parked)

    def test_missing_kind_is_copied_and_other_active_kind_preserved(self):
        self.prepare()
        source = self.slot(kind="seminar")
        target = self.slot(self.target, weekday=3, start_time="13:35", end_time="15:05", kind="lecture")
        before = self.capture()
        dry = self.call()
        self.assertEqual((dry["schedule_slots_to_park"], dry["schedule_slots_to_create"]), (1, 1))
        self.call(apply=True, expected_baseline=dry["baseline"])
        source.refresh_from_db()
        self.assertTrue(source.is_parked)
        replacement = ScheduleSlot.objects.get(offering=self.target, kind="seminar")
        self.assertEqual(qosqar_schedule._signature(source), qosqar_schedule._signature(replacement))
        after = self.capture()
        old = next(row for row in before["schedule"] if str(row["id"]) == str(target.pk))
        current = next(row for row in after["schedule"] if str(row["id"]) == str(target.pk))
        self.assertEqual(qosqar_schedule.state.digest(old), qosqar_schedule.state.digest(current))
        self.assertEqual(self.call()["already_present"], 1)

    def test_source_lesson_prevents_any_schedule_change(self):
        self.prepare()
        slot = self.slot()
        Lesson.objects.create(organization=self.org, offering=self.source, date="2026-10-13", kind="lecture")
        before = self.capture()
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "empty_offering_has_content"):
            self.call()
        slot.refresh_from_db()
        self.assertFalse(slot.is_parked)
        self.assertEqual(qosqar_schedule.state.digest(before), qosqar_schedule.state.digest(self.capture()))

    def test_foreign_teacher_and_unplanned_kind_fail_closed(self):
        self.prepare()
        teacher = get_user_model().objects.create_user("qosqar-other-schedule")
        activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS)
        slot = self.slot(instructor=teacher)
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "source_schedule_teacher_kind"):
            self.call()
        ScheduleSlot.objects.filter(pk=slot.pk).update(instructor=None, kind="lab")
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "source_schedule_teacher_kind"):
            self.call()

    def test_target_conflict_and_duplicate_signature_refuse_without_parking(self):
        self.prepare()
        source = self.slot()
        conflict = self.slot(self.target, end_time="10:15", kind="seminar")
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "conflicting_target_schedule_slot"):
            self.call()
        ScheduleSlot.objects.filter(pk=conflict.pk).update(end_time="10:00", kind="lecture")
        self.slot(self.target)
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "ambiguous_target_schedule_signature"):
            self.call()
        source.refresh_from_db()
        self.assertFalse(source.is_parked)

    def test_full_source_and_target_schedule_baseline_drift_refuses_apply(self):
        self.prepare()
        source = self.slot()
        target = self.slot(self.target, weekday=3, kind="seminar")
        dry = self.call()
        ScheduleSlot.objects.filter(pk=target.pk).update(park_reason="Changed after dry-run")
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "fresh_live_baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        source.refresh_from_db()
        self.assertFalse(source.is_parked)
        ScheduleSlot.objects.filter(pk=target.pk).update(park_reason="")
        dry = self.call()
        ScheduleSlot.objects.filter(pk=source.pk).update(room="Source metadata drift")
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "fresh_live_baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])

    def test_undo_refuses_edited_replacement(self):
        self.prepare()
        self.slot()
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        replacement = ScheduleSlot.objects.get(offering=self.target)
        ScheduleSlot.objects.filter(pk=replacement.pk).update(room="Operator changed room")
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "undo_live_state_changed"):
            self.call(undo=True)

    def test_known_noncontent_configuration_preserved_but_scores_or_handover_block(self):
        self.prepare()
        self.slot()
        AssessmentScheme.objects.create(organization=self.org, offering=self.source)
        component = AssessmentComponent.objects.create(
            organization=self.org, offering=self.source, name="Existing config"
        )
        share = JournalShare.objects.create(
            organization=self.org, offering=self.source, teacher=self.teacher, kinds=["lecture"]
        )
        share.enrollments.add(self.source.enrollments.get())
        dry = self.call()
        before = self.capture()
        self.call(apply=True, expected_baseline=dry["baseline"])
        for label in (
            "registrar.Enrollment",
            "registrar.AssessmentScheme",
            "registrar.AssessmentComponent",
            "registrar.JournalShare",
            "registrar.JournalShare_enrollments",
        ):
            self.assertEqual(
                qosqar_schedule.state.digest(before["academic"].get(label, [])),
                qosqar_schedule.state.digest(self.capture()["academic"].get(label, [])),
            )
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        score = ComponentScore.objects.create(
            organization=self.org, component=component, enrollment=self.source.enrollments.get(), score=3
        )
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "empty_offering_has_content_or_history"):
            self.call()
        score.delete()
        TeachingHandover.objects.create(
            organization=self.org,
            offering=self.source,
            from_instructor=self.teacher,
            to_instructor=self.teacher,
            reason="Historical handover",
        )
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "empty_offering_has_content_or_history"):
            self.call()

    def hygiene(self, enrollment):
        return qosqar_schedule.state.model("registrar.JournalHygieneDecision").objects.create(
            organization=self.org,
            enrollment=enrollment,
            batch=uuid4(),
            category="empty_subject",
            reason_code="reviewed_empty",
            from_status="enrolled",
            to_status="dropped",
            evidence={"retained": "append-only source evidence"},
            evidence_digest="1" * 64,
            reason="Reviewed historical empty journal decision",
            decided_by=self.actor,
        )

    def test_append_only_hygiene_decision_is_byte_identical_through_apply_and_undo(self):
        self.prepare()
        enrollment = self.source.enrollments.get()
        type(enrollment).objects.filter(pk=enrollment.pk).update(status="dropped")
        decision = self.hygiene(enrollment)
        original = qosqar_schedule.state.records(type(decision).objects.filter(pk=decision.pk))
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(original, qosqar_schedule.state.records(type(decision).objects.filter(pk=decision.pk)))
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(original, qosqar_schedule.state.records(type(decision).objects.filter(pk=decision.pk)))
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, "dropped")

    def test_hygiene_from_other_offering_is_not_a_source_history_exception(self):
        self.prepare()
        decision = self.hygiene(self.target.enrollments.first())
        original = qosqar_schedule._children
        source_enrollment = self.source.enrollments.get()

        def mismatched_children(label, ids):
            yield from original(label, ids)
            if label == "registrar.Enrollment" and str(source_enrollment.pk) in set(map(str, ids)):
                yield "registrar.JournalHygieneDecision", type(decision).objects.filter(pk=decision.pk)

        with patch.object(qosqar_schedule, "_children", side_effect=mismatched_children):
            with self.assertRaisesMessage(
                qosqar_schedule.state.DuplicateError, "retained_hygiene_decision_source_enrollment_changed"
            ):
                self.call()

    def test_external_recognition_beneath_hygiene_still_blocks_retirement(self):
        self.prepare()
        enrollment = self.source.enrollments.get()
        decision = self.hygiene(enrollment)
        recognition = qosqar_schedule.state.model("registrar.ExternalCreditRecognition").objects.create(
            organization=self.org,
            student=enrollment.student,
            subject=self.source.subject,
            period=self.source.period,
            exempt_decision=decision,
            program="erasmus",
            institution="Source university",
            country="AZ",
            foreign_subject="Reviewed subject",
            foreign_credit=3,
            foreign_grade="80",
            study_period="2026/2027",
            recognized_score=80,
            credit=3,
            document="private/no-file-created.pdf",
            created_by=self.actor,
        )
        with self.assertRaisesMessage(
            qosqar_schedule.state.DuplicateError,
            "empty_offering_has_content_or_history_registrar_externalcreditrecognition",
        ):
            self.call()
        self.assertTrue(type(recognition).objects.filter(pk=recognition.pk).exists())

    def test_unreviewed_pair_never_gets_schedule_exception(self):
        self.prepare()
        with self.assertRaisesMessage(qosqar_schedule.state.DuplicateError, "schedule_fixed_reviewed_pair_required"):
            qosqar_schedule.plan(self.target.pk, self.source.pk)

    def test_canonical_copy_conflict_rolls_back_parking_and_academic_repair(self):
        self.prepare()
        self.slot()
        dry = self.call()
        before = self.capture()
        original = qosqar_schedule.schedule.create_slot

        def conflicting_create(**fields):
            self.slot(self.target)
            return original(**fields)

        with patch.object(qosqar_schedule.schedule, "create_slot", side_effect=conflicting_create):
            with self.assertRaises(qosqar_schedule.schedule.ScheduleConflict):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(qosqar_schedule.state.digest(before), qosqar_schedule.state.digest(self.capture()))


class QosqarModellingScheduleTests(ScheduleCases, TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp
    call = modelling_fixture.QosqarModellingTests.call

    def prepare(self):
        modelling_fixture.QosqarModellingTests.prepare(self)
        self.org.refresh_from_db()
        self.target, self.source, _anchor = self.offerings

    def capture(self):
        return qosqar_modelling_repair.capture()


class QosqarDuplicateScheduleTests(ScheduleCases, TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp
    call = duplicate_fixture.QosqarDuplicateTests.call

    def prepare(self):
        duplicate_fixture.QosqarDuplicateTests.prepare(self)
        self.org.refresh_from_db()
        self.target, self.source = self.filled, self.empty

    def capture(self):
        return qosqar_duplicate_state.capture()
