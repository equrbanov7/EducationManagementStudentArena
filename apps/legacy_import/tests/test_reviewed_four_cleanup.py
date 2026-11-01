"""Real PG: only byte-pinned reviewed technical deletes, never later teacher clear intent."""

import copy

from django.db import connection, transaction
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services import reviewed_content_four_spec as fixed
from apps.legacy_import.services import reviewed_four_cleanup as cleanup
from apps.legacy_import.services.reviewed_content_contract import ContentError, validate_payload
from apps.legacy_import.services.reviewed_content_state import digest
from apps.legacy_import.tests import test_reviewed_content_four as fixture
from apps.registrar.models import LessonMark


class ReviewedTechnicalCleanupTests(TestCase):
    setUpTestData = classmethod(fixture.FourCellsTests.setUpTestData.__func__)
    mapping = classmethod(fixture.FourCellsTests.mapping.__func__)
    execute = fixture.FourCellsTests.execute
    apply = fixture.FourCellsTests.apply
    undo = fixture.FourCellsTests.undo

    def setUp(self):
        fixture.FourCellsTests.setUp(self)
        self.pin_patch = fixture.patch.dict(cleanup.PINS, {}, clear=True)
        self.pin_patch.start()
        self.addCleanup(self.pin_patch.stop)

    def technical(self, offering_id):
        cases = {point: c for point, c in fixed.CASES.items() if c[0] == offering_id}
        values = {
            "count": 1,
            "marks": len(cases),
            "lessons": [
                dict(
                    category="absent_only",
                    marks=[dict(enrollment_id=c[2], student_id=c[4], status="absent") for c in cases.values()],
                )
            ],
        }
        row = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="delete",
            resource_type=cleanup.RESOURCE,
            resource_id=offering_id,
            reason="legacy_repair:empty_lessons",
            old_values=values,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM audit_auditlog t WHERE id=%s",
                [row.pk],
            )
            raw_sha = cursor.fetchone()[0]
        cleanup.PINS[str(row.pk)] = dict(
            row_sha256=raw_sha,
            old_values_sha256=digest(values),
            offering_id=offering_id,
            case_ids=sorted(cases),
            actor_id=self.actor.pk,
            classification="fixture_reviewed_technical_bulk_cleanup",
        )
        return row

    def test_reviewed_byte_pinned_cleanup_can_restore_four_without_erasing_any_audit(self):
        old = [self.technical(oid) for oid in fixed.TARGETS]
        original = list(AuditLog.objects.filter(pk__in=[r.pk for r in old]).values())
        done = self.apply()
        self.assertEqual((done["created_lessons"], done["created_marks"]), (0, 4))
        self.assertEqual(original, list(AuditLog.objects.filter(pk__in=[r.pk for r in old]).values()))
        receipt = AuditLog.objects.get(resource_id=done["batch"])
        proof = receipt.new_values["fixed_four_recovery"]["reviewed_technical_cleanup"]
        self.assertEqual({r["audit_id"] for r in proof}, {str(r.pk) for r in old})
        self.assertEqual(self.apply()["already_done"], 1)
        dry = self.undo(done["batch"])
        self.assertEqual(self.undo(done["batch"], apply=True, expected_baseline=dry["baseline"])["deleted_marks"], 4)
        self.assertEqual(original, list(AuditLog.objects.filter(pk__in=[r.pk for r in old]).values()))

    def test_unknown_cleanup_with_the_same_resource_kind_is_not_exempted(self):
        oid = next(iter(fixed.TARGETS))
        row = self.technical(oid)
        cleanup.PINS.clear()
        with self.assertRaisesMessage(ContentError, "contrary_clear_delete"):
            self.execute()
        self.assertTrue(AuditLog.objects.filter(pk=row.pk).exists())
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_full_row_or_old_body_hash_drift_refuses_without_creating_marks(self):
        row = self.technical(next(iter(fixed.TARGETS)))
        pin = cleanup.PINS[str(row.pk)]
        for field in ("row_sha256", "old_values_sha256"):
            before = pin[field]
            pin[field] = "0" * 64
            with self.assertRaisesMessage(ContentError, "contrary_clear_delete"):
                self.execute()
            pin[field] = before
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_later_human_clear_delete_malformed_and_source_undo_remain_holds(self):
        for oid in fixed.TARGETS:
            self.technical(oid)
        c = fixed.CASES[5558632]
        cases = [
            dict(
                action="update",
                resource_type="registrar.grade.mark",
                changes=[{"lesson_id": c[1], "enrollment_id": c[2], "old": "q/b", "new": "—"}],
            ),
            dict(action="delete", resource_type="registrar.Lesson"),
            dict(action="update", resource_type="registrar.grade.full-edit", changes={"broken": "PRIVATE"}),
            dict(
                action="update",
                resource_type="legacy_import.reviewed_content",
                new_values={"operation": "fixed_four_undo"},
            ),
        ]
        for event in cases:
            with self.subTest(event=event["resource_type"]), transaction.atomic():
                row = AuditLog.objects.create(organization=self.org, user=self.actor, resource_id=c[1], **event)
                with self.assertRaisesMessage(ContentError, "contrary_clear_delete"):
                    self.execute()
                self.assertTrue(AuditLog.objects.filter(pk=row.pk).exists())
                self.assertEqual(LessonMark.objects.count(), 0)
                transaction.set_rollback(True)

    def test_reviewed_technical_cleanup_never_overwrites_later_zero_or_excused(self):
        for oid in fixed.TARGETS:
            self.technical(oid)
        c = fixed.CASES[5558632]
        for status, score in [("present", 0), ("excused", None)]:
            with self.subTest(status=status), transaction.atomic():
                mark = LessonMark.objects.create(
                    organization=self.org, lesson_id=c[1], enrollment_id=c[2], status=status, score=score
                )
                with self.assertRaises(ContentError):
                    self.execute()
                mark.refresh_from_db()
                self.assertEqual(mark.status, status)
                self.assertEqual(mark.score, score)
                self.assertEqual(LessonMark.objects.count(), 1)
                transaction.set_rollback(True)

    def test_partial_source_authority_never_reuses_a_technical_delete_pin(self):
        row = self.technical(next(iter(fixed.TARGETS)))
        data = validate_payload(self.raw, target_ids=sorted(fixed.TARGETS))
        # Ask the real current SELECT service for the projected immutable row.
        from apps.workload.public import fixed_four_recovery_history

        projected = next(
            r
            for r in fixed_four_recovery_history(actor=self.actor, organization=self.org)["four_cell_history_audits"]
            if r["id"] == str(row.pk)
        )
        self.assertTrue(cleanup.permits_reviewed_cleanup(projected, data))
        partial = copy.deepcopy(data)
        partial["points"] = partial["points"][:-1]
        self.assertFalse(cleanup.permits_reviewed_cleanup(projected, partial))
        changed = {**projected, "contrary_clear_evidence": True}
        self.assertFalse(cleanup.permits_reviewed_cleanup(changed, data))
