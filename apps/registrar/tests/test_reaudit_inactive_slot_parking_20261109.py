"""PostgreSQL regressions for exact reviewed inactive-slot parking and undo."""

import datetime as dt
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import reaudit_journal_structure as op
from apps.registrar import reaudit_journal_structure_parking as parking
from apps.registrar import reaudit_journal_structure_state as state
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.registrar.tests import test_reaudit_journal_structure as fixtures
from core.reviewed_graph import digest


class InactiveSlotParkingTests(TestCase):
    setUpTestData = classmethod(fixtures.JournalStructureTests.setUpTestData.__func__)
    offering = fixtures.JournalStructureTests.offering
    case_pins = fixtures.JournalStructureTests.case_pins

    def setUp(self):
        fixtures.JournalStructureTests.setUp(self)
        self.slots = [self.slot(self.course, weekday=day) for day in (1, 3)]
        CourseOffering.objects.filter(pk=self.course.pk).update(is_active=False)
        self.registry["inactive_slot_cases"] = []
        captured = state.capture(self.org, self.actor, self.manifest())
        fields = (
            "id",
            "organization_id",
            "offering_id",
            "weekday",
            "start_time",
            "end_time",
            "room",
            "week_type",
            "kind",
            "created_by_id",
            "instructor_id",
            "is_deleted",
            "parked_at",
            "parked_by_id",
            "park_reason",
        )
        self.registry["inactive_slot_cases"] = [
            {
                "slot_id": row["id"],
                "offering_id": row["offering_id"],
                "fields": fields,
                "geometry_sha256": digest({key: str(row[key]) for key in fields}),
            }
            for row in captured["graph"]["registrar.ScheduleSlot"]
        ]

    def slot(self, course, *, weekday=5):
        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=course,
            weekday=weekday,
            start_time=dt.time(9),
            end_time=dt.time(10, 30),
            room="Synthetic A",
            kind="seminar",
            created_by=self.actor,
        )

    def manifest(self):
        return {
            "format": "reaudit-journal-structure/1",
            "organization_id": str(self.org.pk),
            "period_id": str(self.course.period_id),
            "operation": "park_inactive_slots",
            "target_ids": sorted(str(row.pk) for row in self.slots),
            "authority_sha256": self.authority_sha,
        }

    def execute(self, **kwargs):
        return op.run(organization=self.org, actor=self.actor, manifest=self.manifest(), **kwargs)

    def apply(self):
        return self.execute(
            apply=True,
            authority_bytes=self.authority,
            expected_baseline=self.execute()["baseline"],
        )

    def slot_rows(self):
        return list(ScheduleSlot.all_objects.filter(pk__in=[s.pk for s in self.slots]).order_by("pk").values())

    def academics(self):
        return {
            model._meta.label: list(model.objects.filter(organization=self.org).order_by("pk").values())
            for model in (CourseOffering, Enrollment, Lesson, LessonMark, apps.get_model("registrar.AbsenceCredit"))
        }

    def test_apply_repeat_exact_receipt_undo_changes_only_park_flag(self):
        before, academic_before = self.slot_rows(), self.academics()
        dry = self.execute()
        self.assertEqual((dry["planned"], dry["changed"], dry["affected_counters"]), (2, 0, 0))
        self.assertEqual(self.slot_rows(), before)
        result = self.apply()
        self.assertEqual((result["status"], result["changed"]), ("applied", 2))
        self.assertEqual(self.slot_rows(), [dict(row, is_parked=True) for row in before])
        self.assertEqual(self.academics(), academic_before)
        self.assertEqual((self.execute()["status"], self.execute()["changed"]), ("already_applied", 0))
        receipt = apps.get_model("audit.AuditLog").objects.get(resource_id=result["receipt"])
        self.assertEqual(receipt.new_values["parked_slot_ids"], self.manifest()["target_ids"])
        self.assertEqual(receipt.new_values["authority_sha256"], self.authority_sha)
        preview = self.execute(undo=result["receipt"])
        undone = self.execute(
            undo=result["receipt"],
            apply=True,
            authority_bytes=self.authority,
            expected_baseline=preview["baseline"],
        )
        self.assertEqual((undone["status"], undone["changed"]), ("undone", 2))
        self.assertEqual(self.slot_rows(), before)
        self.assertEqual(self.academics(), academic_before)
        self.assertEqual(
            (self.execute(undo=result["receipt"])["status"], self.execute(undo=result["receipt"])["changed"]),
            ("already_undone", 0),
        )

    def test_offering_becoming_active_after_dry_run_refuses_apply(self):
        dry = self.execute()
        CourseOffering.objects.filter(pk=self.course.pk).update(is_active=True)
        with self.assertRaisesRegex(ValueError, "offering_now_active"), transaction.atomic():
            self.execute(apply=True, authority_bytes=self.authority, expected_baseline=dry["baseline"])
        self.assertFalse(any(row["is_parked"] for row in self.slot_rows()))

    def test_slot_geometry_change_before_review_refuses_even_new_baseline(self):
        ScheduleSlot.all_objects.filter(pk=self.slots[0].pk).update(room="Changed")
        with self.assertRaisesRegex(ValueError, "parking_geometry_changed"), transaction.atomic():
            self.execute()

    def test_slot_geometry_change_after_dry_run_refuses_apply(self):
        dry = self.execute()
        ScheduleSlot.all_objects.filter(pk=self.slots[0].pk).update(instructor=self.other)
        with self.assertRaisesRegex(ValueError, "parking_geometry_changed"), transaction.atomic():
            self.execute(apply=True, authority_bytes=self.authority, expected_baseline=dry["baseline"])

    def test_unpinned_timestamp_change_still_invalidates_baseline(self):
        dry = self.execute()
        ScheduleSlot.all_objects.filter(pk=self.slots[0].pk).update(updated_at=timezone.now())
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, authority_bytes=self.authority, expected_baseline=dry["baseline"])

    def test_teacher_mark_change_between_review_and_apply_is_preserved(self):
        dry = self.execute()
        LessonMark.objects.filter(enrollment=self.enrollment, score=0).update(score=1)
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, authority_bytes=self.authority, expected_baseline=dry["baseline"])
        self.assertTrue(LessonMark.objects.filter(enrollment=self.enrollment, score=1).exists())
        self.assertFalse(any(row["is_parked"] for row in self.slot_rows()))

    def test_unrelated_period_slot_edit_blocks_undo(self):
        other_slot = self.slot(self.course)
        result = self.apply()
        ScheduleSlot.all_objects.filter(pk=other_slot.pk).update(start_time=dt.time(12))
        with self.assertRaisesRegex(ValueError, "post_apply_graph_changed"), transaction.atomic():
            self.execute(undo=result["receipt"])

    def test_other_offering_effective_teacher_edit_blocks_undo(self):
        group = OrgUnit.objects.create(
            organization=self.org, name="Synthetic other group", slug="parking-other", unit_type="group"
        )
        other_course = self.offering(instructor=self.other, stack={**self.stack, "group": group})
        self.slot(other_course)
        result = self.apply()
        CourseOffering.objects.filter(pk=other_course.pk).update(instructor=self.teacher)
        with self.assertRaisesRegex(ValueError, "post_apply_graph_changed"), transaction.atomic():
            self.execute(undo=result["receipt"])

    def test_active_offering_after_apply_blocks_undo(self):
        result = self.apply()
        CourseOffering.objects.filter(pk=self.course.pk).update(is_active=True)
        with self.assertRaisesRegex(ValueError, "offering_now_active"), transaction.atomic():
            self.execute(undo=result["receipt"])

    def test_authority_and_exact_receipt_are_required(self):
        dry = self.execute()
        with self.assertRaisesRegex(ValueError, "source_authority"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"])
        result = self.apply()
        with self.assertRaisesRegex(ValueError, "exact_receipt"), transaction.atomic():
            self.execute(undo=str(uuid4()))
        self.assertTrue(result["receipt"])

    def test_unreviewed_target_and_foreign_tenant_manifest_refuse(self):
        for mutation, error in (
            ({"target_ids": [str(uuid4())]}, "unreviewed_slot"),
            ({"organization_id": str(uuid4())}, "manifest_tenant_period"),
            ({"period_id": str(uuid4())}, "manifest_tenant_period"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error), transaction.atomic():
                op.run(organization=self.org, actor=self.actor, manifest={**self.manifest(), **mutation})

    def test_deleted_slot_and_previously_parked_slot_refuse(self):
        for field, error in (("is_deleted", "offering_now_active_or_deleted"), ("is_parked", "parking_state_changed")):
            with self.subTest(field=field):
                ScheduleSlot.all_objects.filter(pk=self.slots[0].pk).update(**{field: True})
                with self.assertRaisesRegex(ValueError, error), transaction.atomic():
                    self.execute()
                ScheduleSlot.all_objects.filter(pk=self.slots[0].pk).update(**{field: False})

    def test_postwrite_guard_rolls_back_flags_and_unexpected_academic_change(self):
        before = self.slot_rows()
        original = parking.write

        def tampered(*args, **kwargs):
            original(*args, **kwargs)
            Lesson.objects.filter(pk=self.lessons[0].pk).update(hours=1)

        dry = self.execute()
        with patch.object(parking, "write", side_effect=tampered):
            with self.assertRaisesRegex(ValueError, "protected_graph_changed"), transaction.atomic():
                self.execute(apply=True, authority_bytes=self.authority, expected_baseline=dry["baseline"])
        self.assertEqual(self.slot_rows(), before)
        self.lessons[0].refresh_from_db()
        self.assertEqual(self.lessons[0].hours, 2)
        self.assertFalse(apps.get_model("audit.AuditLog").objects.filter(resource_type=op.spec.RESOURCE).exists())
