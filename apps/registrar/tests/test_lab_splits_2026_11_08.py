"""Sahib 2026-11-08: Mexanika fizika lab qrupları — plan ids-only, əmr dry-run, prod-data-ops-a qoşulub."""

import io
import json
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls

PLAN = Path(__file__).resolve().parents[1] / "lab_splits_2026_11_08.json"


class LabSplitsCommandTest(_LabWorld, TestCase):
    def test_plan_is_ids_only(self):
        data = json.loads(PLAN.read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"lab", "shares"})
        for spec in data["lab"].values():
            self.assertEqual(set(spec), {"offering", "legacy", "groups"})
            self.assertTrue(all(len(pk) == 36 for ids in spec["groups"].values() for pk in ids))

    def test_dry_run_reports_missing_offerings(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
        out = io.StringIO()
        call_command("apply_lab_splits_20261108", "--org", self.org.slug, "--actor", self.owner.username, stdout=out)
        self.assertIn("phys_k_ing_offering_missing=1", out.getvalue())

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - apply_lab_splits_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "apply_lab_splits_20261108" ]', text)
        self.assertRegex(text, r"\n            [a-z0-9_|]*\|apply_lab_splits_20261108[|)]")
