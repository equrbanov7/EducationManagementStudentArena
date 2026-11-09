"""Adı fərqli rəsmi birləşmə yalnız native receipt və canlı qrafla qəbul edilir."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.exams.management.commands.sync_final_scores import official_final_attempts
from apps.exams.models import ExamAttempt
from apps.exams.services import journal_sync, midterm_journal_sync
from apps.exams.services.journal_sync_scope import target_identity, target_key
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar import exam_bridge
from apps.registrar.exam_journal_merge_scope import merged_offering_ids
from apps.registrar.models import CourseOffering, Enrollment, FinalGrade, Subject
from apps.registrar.twin_merge_empty import EmptyTwinMerge
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls


class ReviewedMergeScopeTests(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.canonical = Subject.objects.create(organization=self.org, code="OFFICIAL", name="Rəsmi yeni ad")
            self.target = CourseOffering.objects.create(
                organization=self.org, subject=self.canonical, group=self.group, period=self.period
            )
        self.exam, self.options = self._exam()
        with bypass_rls():
            self.exam.journal_offerings.add(self.offering)

    def _merge(self, *, target_already_linked=False):
        with bypass_rls():
            if target_already_linked:
                self.exam.journal_offerings.add(self.target)
            counts = Counter()
            EmptyTwinMerge(organization=self.org, actor=self.owner, counts=counts).merge(self.offering, self.target, {})
            self.assertEqual(counts["pairs_merged"], 1)
            return Enrollment.objects.get(offering=self.target, student=self.student)

    def _resolve(self, exam=None):
        with bypass_rls():
            return exam_bridge.resolve_enrollment(
                student=self.student,
                subject_id=self.subject.pk,
                organization=self.org,
                offering_ids=[self.target.pk],
                exam_id=(exam or self.exam).pk,
            )

    def test_empty_merge_receipt_accepts_already_linked_target(self):
        enrollment = self._merge(target_already_linked=True)
        self.assertEqual(self._resolve().pk, enrollment.pk)

    def test_plain_link_without_merge_proof_is_not_authority(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
            Enrollment.objects.create(organization=self.org, offering=self.target, student=self.student)
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
            self.exam.journal_offerings.set([self.target])
        self.assertIsNone(self._resolve())

    def test_other_exam_cannot_borrow_receipt(self):
        self._merge()
        other, _ = self._exam(title="Unreviewed link")
        with bypass_rls():
            other.journal_offerings.add(self.target)
        self.assertIsNone(self._resolve(other))

    def test_source_link_must_have_been_removed(self):
        self._merge()
        with bypass_rls():
            self.exam.journal_offerings.add(self.offering)
        self.assertIsNone(self._resolve())

    def test_reactivated_source_invalidates_receipt(self):
        self._merge()
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=True)
        self.assertIsNone(self._resolve())

    def test_inactive_target_invalidates_receipt(self):
        self._merge()
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.target.pk).update(is_active=False)
        self.assertIsNone(self._resolve())

    def test_target_subject_pin_must_match_merge_receipt(self):
        self._merge()
        with bypass_rls():
            other = Subject.objects.create(organization=self.org, code="LATER", name="Başqa fənn")
            # Raw FK mutation is blocked by the real PG parent-identity trigger.
            # Exercise the resolver's independent snapshot pin without bypassing it.
            self.target.subject = other
            self.assertEqual(merged_offering_ids(self.org, self.subject.pk, [self.target], exam_id=self.exam.pk), set())

    def test_restore_marker_blocks_old_receipt_even_if_source_inactive_again(self):
        self._merge()
        with bypass_rls():
            log_action(
                action=AuditAction.UPDATE,
                user=self.owner,
                organization=self.org,
                obj=self.offering,
                changes={"kind": "twin_merge_empty_restore"},
                new_values={"is_active": True, "keep": str(self.target.pk)},
            )
        self.assertIsNone(self._resolve())

    def _receipt(self, manifest, *, kind="twin_merge_empty", values=None):
        return log_action(
            action=AuditAction.UPDATE,
            user=self.owner,
            organization=self.org,
            obj=self.target,
            changes={"kind": kind, "manifest": manifest},
            new_values=values or {},
        )

    def test_malformed_manifests_cannot_authorize_an_unreviewed_link(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
            Enrollment.objects.create(organization=self.org, offering=self.target, student=self.student)
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
            self.exam.journal_offerings.set([self.target])
            for malformed in (
                ["invalid manifest"],
                {"source": "not-a-uuid", "target": str(self.target.pk), "exam_links": [{"exam": str(self.exam.pk)}]},
                {"source": str(self.offering.pk), "target": str(self.target.pk), "exam_links": "invalid links"},
            ):
                with self.subTest(manifest_type=type(malformed).__name__):
                    self._receipt(malformed)
                    self.assertIsNone(self._resolve())

    def test_latest_merge_companion_cannot_borrow_ancient_matching_subject_pins(self):
        self._merge()
        with bypass_rls():
            log_action(
                action=AuditAction.UPDATE,
                user=self.owner,
                organization=self.org,
                obj=self.target,
                new_values={
                    "source": str(self.offering.pk),
                    "target": str(self.target.pk),
                    "source_subject": str(self.subject.pk),
                    "target_subject": "a-different-reviewed-subject",
                },
            )
            self._receipt(
                {
                    "source": str(self.offering.pk),
                    "target": str(self.target.pk),
                    "exam_links": [{"exam": str(self.exam.pk), "target_added": False}],
                },
                kind="twin_merge_scored",
            )
        self.assertIsNone(self._resolve())

    def _assert_merged_latest(self, category):
        enrollment = self._merge()
        with bypass_rls():
            self.exam.exam_type_extended = category
            self.exam.save(update_fields=["exam_type_extended"])
        older = self._finish(self.exam, self.options, correct=3, started_at=timezone.now() - timedelta(hours=2))
        newer_exam, options = self._exam(category=category)
        with bypass_rls():
            newer_exam.subject = self.canonical
            newer_exam.save(update_fields=["subject"])
            newer_exam.journal_offerings.add(self.target)
        newer = self._finish(newer_exam, options, correct=1)
        sync = journal_sync.sync_final_attempt if category == "final" else midterm_journal_sync.sync_midterm_attempt
        official = official_final_attempts if category == "final" else midterm_journal_sync.official_attempts
        with bypass_rls():
            self.assertEqual(target_identity(older), ("enrollment", enrollment.pk))
            self.assertEqual(target_key(older), target_key(newer))
            status, row = sync(older)
            self.assertEqual(
                [item.pk for item in official(ExamAttempt.objects.filter(pk__in=[older.pk, newer.pk]))], [newer.pk]
            )
            if category == "final":
                self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal("17"))
        expected = journal_sync.SKIP_SUPERSEDED_ATTEMPT if category == "final" else midterm_journal_sync.SUPERSEDED
        self.assertEqual((status, row), (expected, None))

    def test_merged_final_uses_same_target_for_writer_and_latest_selection(self):
        self._assert_merged_latest("final")

    def test_merged_midterm_uses_same_target_for_writer_and_latest_selection(self):
        self._assert_merged_latest("midterm")
