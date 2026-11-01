"""Real PG: reviewed other-day history never exempts current-slot intent or old zero grades."""

import copy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils.translation import override

from apps.audit.models import AuditLog
from apps.legacy_import.services import reviewed_content_28 as guard
from apps.legacy_import.services import reviewed_content_28_spec as fixed
from apps.legacy_import.services import reviewed_content_28_undo as undo_service
from apps.legacy_import.services import reviewed_source28_history as review
from apps.legacy_import.services.reviewed_content_contract import ContentError, validate_payload
from apps.legacy_import.tests import test_reviewed_content_28 as fixture
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.workload.services.scoped_snapshot.four_cell_history import collect_available_history
from apps.workload.services.source28_spec import history_scope


class ReviewedSource28HistoryTests(TestCase):
    setUpTestData = classmethod(fixture.Source28Tests.setUpTestData.__func__)
    mapping = classmethod(fixture.Source28Tests.mapping.__func__)
    execute = fixture.Source28Tests.execute
    apply = fixture.Source28Tests.apply

    def setUp(self):
        fixture.Source28Tests.setUp(self)
        self.rows = []
        self.maintenance = get_user_model().objects.create_user("source28-maintenance")
        self.cleanup = self.audit(
            action="delete",
            resource_type="legacy_import.empty_lesson",
            user=self.maintenance,
            reason="legacy_repair:empty_lessons",
            old_values={
                "count": 1,
                "marks": 0,
                "lessons": [
                    {
                        "id": "6d13d93c-a9c9-4014-b3ec-1ff9123fc713",
                        "date": "2026-09-05",
                        "kind": "seminar",
                        "hours": 2,
                        "start_time": "15:15:00",
                        "offering_id": fixed.TARGET,
                        "category": "empty",
                        "marks": [],
                    }
                ],
            },
        )
        self.pin_row(self.cleanup, "empty_september_column_zero_marks")
        self.teacher = get_user_model().objects.get(pk=fixed.SPEC["teacher_id"])
        self.grade = self.audit(
            action="update",
            resource_type="registrar.grade.mark",
            user=self.teacher,
            reason="Other day legitimate positive changes",
            new_values={"count": 39},
            changes=[
                {"student": "Known legacy label", "item": "2026-10-26 · Seminar", "old": "—", "new": "i/e"}
                for _ in range(39)
            ],
        )
        self.pin_row(self.grade, "teacher_positive_other_day_2026_10_26")
        self.amendment = self.audit(
            action="update",
            resource_type="workload.WorkloadAmendment",
            user=self.maintenance,
            reason="workload.amendment:correction",
            new_values={"action": "vacant_fill", "offerings": {fixed.TARGET: {}}, "fills": [], "batch": "fixture"},
        )
        self.pin_row(self.amendment, "released_vacantfill_allocation")

    def audit(self, **values):
        values.setdefault("resource_id", fixed.TARGET)
        row = AuditLog.objects.create(organization=self.org, **values)
        self.rows.append(row)
        return row

    def history(self):
        with override("az"):
            return collect_available_history(_scope=history_scope())

    def projected(self, row):
        return next(r for r in self.history()["source28_history_audits"] if r["id"] == str(row.pk))

    def pin_row(self, row, classification):
        value = self.projected(row)
        review.PINS[str(row.pk)] = {
            **{
                key: value[key]
                for key in (
                    "raw_record_sha256",
                    "old_values_sha256",
                    "new_values_sha256",
                    "changes_sha256",
                    "user_id",
                    "action",
                    "resource_kind",
                    "resource_kind_sha256",
                    "resource_id",
                    "resource_id_sha256",
                )
            },
            "classification": classification,
            "change_count": len(row.changes or []),
        }

    def old_zero(self):
        c = next(iter(fixed.CASES.values()))
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date="2026-10-26",
            start_time="15:15",
            kind="seminar",
            hours=2,
        )
        return LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=Enrollment.objects.get(pk=c["enrollment_id"]),
            status="present",
            score=Decimal("0"),
        )

    def test_reviewed_history_restores28_preserves_original_audits_and_zero_grade_repeat_undo(self):
        old = self.old_zero()
        before = list(AuditLog.objects.filter(pk__in=[r.pk for r in self.rows]).order_by("pk").values())
        zero_before = LessonMark.objects.filter(pk=old.pk).values().get()
        done = self.apply()
        self.assertEqual((done["created_lessons"], done["created_marks"]), (1, 28))
        self.assertEqual(zero_before, LessonMark.objects.filter(pk=old.pk).values().get())
        self.assertEqual(
            before, list(AuditLog.objects.filter(pk__in=[r.pk for r in self.rows]).order_by("pk").values())
        )
        proof = AuditLog.objects.get(resource_id=done["batch"]).new_values["fixed_source28_recovery"]
        self.assertEqual(
            {r["audit_id"] for r in proof["reviewed_nonconflicting_history"]}, {str(r.pk) for r in self.rows}
        )
        self.assertEqual(self.apply()["already_done"], 1)
        data = validate_payload(self.raw, target_ids=[fixed.TARGET])
        dry = undo_service.undo(
            data=data, source_sha256=fixed.SOURCE_SHA, user=self.actor, organization=self.org, batch=done["batch"]
        )
        result = undo_service.undo(
            data=data,
            source_sha256=fixed.SOURCE_SHA,
            user=self.actor,
            organization=self.org,
            batch=done["batch"],
            apply=True,
            expected_baseline=dry["baseline"],
        )
        self.assertEqual((result["deleted_lessons"], result["deleted_marks"]), (1, 28))
        self.assertEqual(zero_before, LessonMark.objects.filter(pk=old.pk).values().get())
        self.assertEqual(
            before, list(AuditLog.objects.filter(pk__in=[r.pk for r in self.rows]).order_by("pk").values())
        )

    def test_current_day_teacher_clear_of_zero_is_not_blank_and_holds(self):
        c = next(iter(fixed.CASES.values()))
        user = get_user_model().objects.get(pk=c["student_id"])
        with override("az"):
            label = fixed.DATE + " · " + str(Lesson(kind="seminar").get_kind_display())
            self.audit(
                action="update",
                resource_type="registrar.grade.mark",
                user=self.teacher,
                changes=[{"student": user.get_full_name() or user.username, "item": label, "old": "0", "new": "—"}],
            )
            with self.assertRaisesMessage(ContentError, "contrary_history"):
                self.apply()
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_unknown_other_day_same_resource_is_not_generically_ignored(self):
        self.audit(
            action="update",
            resource_type="registrar.grade.mark",
            user=self.teacher,
            changes=[{"student": "Unknown", "item": "2026-10-26 · Seminar", "old": "—", "new": "i/e"}],
        )
        with self.assertRaisesMessage(ContentError, "unresolved_course_audit"):
            self.execute()

    def test_changed_full_or_json_body_hash_or_actor_holds_without_insert(self):
        pin = review.PINS[str(self.cleanup.pk)]
        for field in (
            "raw_record_sha256",
            "old_values_sha256",
            "new_values_sha256",
            "changes_sha256",
            "resource_kind_sha256",
            "resource_id_sha256",
            "user_id",
        ):
            with self.subTest(field=field):
                original = pin[field]
                pin[field] = 0 if field == "user_id" else "0" * 64
                try:
                    with self.assertRaisesMessage(ContentError, "reviewed_history_anchor_changed"):
                        self.execute()
                    self.assertEqual(LessonMark.objects.count(), 0)
                finally:
                    pin[field] = original

    def test_missing_reviewed_anchor_is_not_silently_missing_history(self):
        review.PINS["00000000-0000-0000-0000-000000000001"] = copy.deepcopy(review.PINS[str(self.cleanup.pk)])
        with self.assertRaisesMessage(ContentError, "reviewed_history_anchor_missing"):
            self.execute()

    def test_extra_malformed_change_and_unknown_slot_remain_hold(self):
        for changes in (
            [{"student": "Unknown", "item": "Seminar", "old": "9", "new": "—"}],
            [
                {"student": "Unknown", "item": "2026-10-26 · Seminar", "old": "—", "new": "i/e"},
                "unknown malformed node",
            ],
        ):
            with transaction.atomic():
                self.audit(action="update", resource_type="registrar.grade.mark", user=self.teacher, changes=changes)
                with self.assertRaises(ContentError):
                    self.execute()
                self.assertEqual(LessonMark.objects.count(), 0)
                transaction.set_rollback(True)

    def test_fixed_source_scope_and_unapproved_fields_cannot_select_classification(self):
        data = validate_payload(self.raw, target_ids=[fixed.TARGET])
        row = self.projected(self.cleanup)
        self.assertTrue(review.permits(row, data))
        for bad in ([], [fixed.TARGET, "other"]):
            changed = copy.deepcopy(data)
            changed["selected_target_ids"] = bad
            self.assertFalse(review.permits(row, changed))
        row["changes_sha256"] = "0" * 64
        self.assertFalse(review.permits(row, data))

    def test_existing_current_slot_zero_never_overwritten(self):
        c = next(iter(fixed.CASES.values()))
        lesson = Lesson.objects.create(
            id=fixed.LESSON,
            organization=self.org,
            offering=self.offering,
            date=fixed.DATE,
            start_time=fixed.START,
            kind="seminar",
            hours=2,
            topic=fixed.TOPIC,
        )
        old = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment_id=c["enrollment_id"], status="present", score=Decimal("0")
        )
        with self.assertRaisesMessage(ContentError, "existing_content_without_original_recovery_receipt"):
            self.execute()
        old.refresh_from_db()
        self.assertEqual(old.score, Decimal("0"))
        self.assertEqual(LessonMark.objects.count(), 1)

    def test_later_absent_or_excused_or_new_clear_prevents_repeat_and_undo(self):
        done = self.apply()
        data = validate_payload(self.raw, target_ids=[fixed.TARGET])
        for status in ("absent", "excused"):
            with transaction.atomic():
                LessonMark.objects.filter(pk=next(iter(guard.mark_ids().values()))).update(status=status)
                with self.assertRaises(ContentError):
                    self.execute()
                with self.assertRaises(ContentError):
                    undo_service.undo(
                        data=data,
                        source_sha256=fixed.SOURCE_SHA,
                        user=self.actor,
                        organization=self.org,
                        batch=done["batch"],
                    )
                self.assertEqual(LessonMark.objects.count(), 28)
                transaction.set_rollback(True)

    def test_new_anchor_failures_keep_safe_native_diagnostic_codes(self):
        from apps.workload.public import describe_read_only_export_error

        for suffix in ("fixed_scope_required", "anchor_missing", "anchor_changed"):
            code = "reviewed_source28_reviewed_history_" + suffix
            fields = describe_read_only_export_error(ContentError(code), "source28_history")
            self.assertEqual(fields["guard"], code)
