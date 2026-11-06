"""RİM 2026-11-06: ``repair_applications_20261106`` — MR-236 əkiz birləşməsi + workflow bağlantısı."""

from __future__ import annotations

import pathlib
from collections import Counter

from django.test import SimpleTestCase

from apps.registrar import applications_repair_2026_11_06 as repair
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class ApplicationsRepair1106Test(SimpleTestCase):
    def test_pairs_are_ids_only_and_keep_target_marks(self):
        for pair in repair.MR236_PAIRS:
            self.assertEqual(set(pair), {"source", "target", "target_marks"})
            self.assertEqual(pair["target_marks"], "keep")

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_applications_20261106\n", text)
        self.assertIn('[ "$COMMAND" = "repair_applications_20261106" ]', text)

    def test_run_delegates_to_merger(self):
        from unittest import mock

        with (
            mock.patch.object(repair, "Merger") as merger,
            mock.patch.object(repair, "release_murad_shares") as release,
        ):
            repair.run(organization=object(), actor=object(), counts=Counter())
        release.assert_called_once()
        merger.return_value.run.assert_called_once()


class MuradSharesTest(_GuestRosterBase):
    def test_owner_shares_are_deactivated_so_owner_sees_full_journal(self):
        from unittest import mock

        from apps.registrar.models import JournalShare

        with bypass_rls():
            share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.teacher, kinds=[]
            )
        with (
            mock.patch.object(repair, "MURAD_TEACHER", self.teacher.pk),
            mock.patch.object(repair, "MURAD_OFFERINGS", (str(self.offering.pk),)),
            bypass_rls(),
        ):
            counts = Counter()
            repair.release_murad_shares(organization=self.org, actor=self.coordinator, counts=counts)
            self.assertEqual((counts["murad_shares_deactivated"], counts["murad_offerings_fixed"]), (1, 1))
            self.assertFalse(JournalShare.objects.get(pk=share.pk).is_active)
            again = Counter()
            repair.release_murad_shares(organization=self.org, actor=self.coordinator, counts=again)
            self.assertEqual(again["murad_offering_already_full"], 1)
