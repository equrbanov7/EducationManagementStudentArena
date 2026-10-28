"""Tam təhvil köhnə payla yazını saxlamır; undo yalnız öz arxivləşdirdiyi payları qaytarır."""

from apps.registrar import handover_actions, journal_access, journal_shares
from apps.registrar.models import CourseOffering, JournalShare, TeachingHandover
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase


class HandoverJournalSharesTests(HandoverBase):
    def setUp(self):
        with bypass_rls():
            self.old_share = JournalShare.objects.create(
                organization=self.org, offering=self.offering_a, teacher=self.old_teacher, source="legacy", kinds=[]
            )
            self.target_share = JournalShare.objects.create(
                organization=self.org,
                offering=self.offering_a,
                teacher=self.new_teacher,
                source="legacy",
                kinds=["seminar"],
            )
            self.other_share = JournalShare.objects.create(
                organization=self.org, offering=self.offering_a, teacher=self.other_teacher, kinds=["lab"]
            )

    def _fresh(self):
        return CourseOffering.objects.get(pk=self.offering_a.pk)

    def _undo(self, record_id):
        return handover_actions.revert(
            actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv təyinatı geri qaytar"
        )

    def test_handover_removes_old_write_and_target_restriction_but_keeps_other_shares(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            offering = self._fresh()
            self.assertTrue(journal_access.can_observe_journal(self.old_teacher, offering))
            self.assertFalse(journal_access.can_edit_journal(self.old_teacher, offering))
            self.assertFalse(journal_access.is_direct_editor(self.old_teacher, offering))
            self.assertTrue(journal_access.is_direct_editor(self.new_teacher, offering))
            self.assertTrue(journal_shares.journal_scope(self.new_teacher, offering).full)
            self.other_share.refresh_from_db()
            self.assertTrue(self.other_share.is_active)
            self.assertTrue(journal_access.can_edit_journal(self.other_teacher, offering))
            record = TeachingHandover.objects.get(pk=record_id)
            self.assertEqual(set(record.deactivated_share_ids), {str(self.old_share.pk), str(self.target_share.pk)})

    def test_undo_restores_same_share_ids_kinds_and_enrollments(self):
        with bypass_rls():
            enrollment = self.offering_a.enrollments.first()
            self.old_share.enrollments.add(enrollment)
            record_id = self._reassign()["handover_ids"][0]
            self._undo(record_id)
            offering = self._fresh()
            self.assertEqual(offering.instructor_id, self.old_teacher.pk)
            self.assertTrue(journal_access.can_edit_journal(self.old_teacher, offering))
            for share in (self.old_share, self.target_share, self.other_share):
                share.refresh_from_db()
                self.assertTrue(share.is_active)
            self.assertEqual(self.target_share.kinds, ["seminar"])
            self.assertEqual(list(self.old_share.enrollments.values_list("pk", flat=True)), [enrollment.pk])

    def test_undo_conflict_does_not_overwrite_new_share_or_owner(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            replacement = JournalShare.objects.create(
                organization=self.org, offering=self.offering_a, teacher=self.old_teacher, kinds=["lecture"]
            )
            with self.assertRaises(handover_actions.HandoverError) as error:
                self._undo(record_id)
            self.assertEqual(error.exception.code, "share_state_changed")
            self.assertEqual(self._fresh().instructor_id, self.new_teacher.pk)
            replacement.refresh_from_db()
            self.old_share.refresh_from_db()
            self.assertTrue(replacement.is_active)
            self.assertFalse(self.old_share.is_active)
            self.assertFalse(TeachingHandover.objects.get(pk=record_id).is_reverted)

    def test_failed_bulk_rolls_back_share_deactivation(self):
        with bypass_rls():
            with self.assertRaises(handover_actions.HandoverError):
                handover_actions.bulk_reassign(
                    actor=self.rim,
                    organization=self.org,
                    items=[
                        {"offering_id": self.offering_a.pk, "new_instructor_id": self.new_teacher.pk},
                        {"offering_id": self.offering_past.pk, "new_instructor_id": self.new_teacher.pk},
                    ],
                    reason="Bir neçə fənnin təhvili",
                )
            self.assertEqual(self._fresh().instructor_id, self.old_teacher.pk)
            self.old_share.refresh_from_db()
            self.target_share.refresh_from_db()
            self.assertTrue(self.old_share.is_active)
            self.assertTrue(self.target_share.is_active)
            self.assertFalse(TeachingHandover.objects.filter(offering=self.offering_a).exists())

    def test_manual_old_owner_share_is_also_revoked_on_full_handover(self):
        with bypass_rls():
            self.old_share.source = "manual"
            self.old_share.save(update_fields=["source"])
            self._reassign()
            self.assertFalse(journal_access.can_edit_journal(self.old_teacher, self._fresh()))

    def test_audit_records_exact_deactivated_share_ids(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            audit = AuditLog.objects.filter(resource_type="registrar.teaching_handover", resource_id=record_id).get()
            self.assertEqual(
                set(audit.changes["deactivated_share_ids"]), {str(self.old_share.pk), str(self.target_share.pk)}
            )
