"""RİM 2026-11-07b: ``repair_applications_20261107b`` — MR-221 əkiz birləşməsi, MR-188 alt qrup payları + workflow."""

from __future__ import annotations

import pathlib
from collections import Counter
from unittest import mock

from django.test import SimpleTestCase

from apps.registrar import applications_repair_2026_11_07b as repair
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class ApplicationsRepair1107bTest(SimpleTestCase):
    def test_pairs_are_ids_only_and_keep_target_marks(self):
        for pair in repair.MR221_PAIRS:
            self.assertEqual(set(pair), {"source", "target", "target_marks"})
            self.assertEqual(pair["target_marks"], "keep")

    def test_split_lists_do_not_overlap(self):
        yegane, gunay = (set(students) for students in repair.MR188_SPLIT.values())
        self.assertEqual((len(yegane), len(gunay)), (10, 9))
        self.assertFalse(yegane & gunay)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_applications_20261107b\n", text)
        self.assertIn('[ "$COMMAND" = "repair_applications_20261107b" ]', text)

    def test_run_merges_then_splits(self):
        with mock.patch.object(repair, "Merger") as merger, mock.patch.object(repair, "split_mr188") as split:
            repair.run(organization=object(), actor=object(), counts=Counter())
        merger.return_value.run.assert_called_once()
        split.assert_called_once()


class MR188SplitTest(_GuestRosterBase):
    def _patch(self, owner, split):
        return (
            mock.patch.object(repair, "MR188_OFFERING", str(self.offering.pk)),
            mock.patch.object(repair, "MR188_OWNER", owner),
            mock.patch.object(repair, "MR188_SPLIT", split),
        )

    def test_each_share_gets_its_subgroup_and_owner_keeps_unassigned(self):
        from apps.registrar.journal_shares import journal_scope
        from apps.registrar.models import CourseOffering, Enrollment, JournalShare

        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=self.teacher)
            self.offering.refresh_from_db()
            JournalShare.objects.create(organization=self.org, offering=self.offering, teacher=self.teacher, kinds=[])
            JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.coordinator, kinds=[]
            )
            if not Enrollment.objects.filter(offering=self.offering, student=self.guest).exists():
                Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.guest)
            rows = list(Enrollment.objects.filter(offering=self.offering, status="enrolled").order_by("pk"))
        self.assertGreaterEqual(len(rows), 2)
        split = {self.teacher.pk: (rows[0].student_id,), self.coordinator.pk: (rows[1].student_id,)}
        patches = self._patch(self.teacher.pk, split)
        with patches[0], patches[1], patches[2], bypass_rls():
            counts = Counter()
            repair.split_mr188(organization=self.org, actor=self.coordinator, counts=counts)
            self.assertEqual((counts["mr188_shares_split"], counts["mr188_students_assigned"]), (2, 2))
            other = journal_scope(self.coordinator, CourseOffering.objects.get(pk=self.offering.pk))
            self.assertEqual(other.enrollment_ids, frozenset({str(rows[1].pk)}))
            owner = journal_scope(self.teacher, CourseOffering.objects.get(pk=self.offering.pk))
            self.assertIn(str(rows[0].pk), owner.enrollment_ids)
            self.assertNotIn(str(rows[1].pk), owner.enrollment_ids)
            again = Counter()
            repair.split_mr188(organization=self.org, actor=self.coordinator, counts=again)
            self.assertEqual(again["mr188_share_already_split"], 2)

    def test_changed_owner_is_skipped(self):
        patches = self._patch(-1, {})
        with patches[0], patches[1], patches[2], bypass_rls():
            counts = Counter()
            repair.split_mr188(organization=self.org, actor=self.coordinator, counts=counts)
        self.assertEqual(counts["mr188_offering_changed_skipped"], 1)
