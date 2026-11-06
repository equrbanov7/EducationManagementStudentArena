"""RİM 2026-11-06: ``repair_applications_20261106`` — MR-236 əkiz birləşməsi + workflow bağlantısı."""

from __future__ import annotations

import pathlib
from collections import Counter

from django.test import SimpleTestCase

from apps.registrar import applications_repair_2026_11_06 as repair

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

        with mock.patch.object(repair, "Merger") as merger:
            repair.run(organization=object(), actor=object(), counts=Counter())
        merger.return_value.run.assert_called_once()
