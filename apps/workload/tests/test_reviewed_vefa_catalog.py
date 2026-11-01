"""One separately pinned old-DB fallback, using the unchanged graph safety core."""

import copy
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from apps.workload.services import reviewed_two_catalog_repair as repair
from apps.workload.services import reviewed_two_catalog_state as state
from apps.workload.services import reviewed_vefa_catalog_spec as spec
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError
from apps.workload.services.scoped_snapshot.vefa_catalog_references import collect_vefa_catalog_references
from apps.workload.tests import test_reviewed_two_catalog as fixtures
from apps.workload.tests.test_reviewed_two_catalog_host import host


class VefaCatalogTests(TestCase):
    setUpTestData = classmethod(fixtures.TwoCatalogTests.setUpTestData.__func__)

    def setUp(self):
        fixtures.TwoCatalogTests.setUp(self)
        from apps.workload.services import reviewed_two_catalog_spec as two

        self.pin = copy.deepcopy(two.CASES[0])
        self.pin["source"]["authority"] = "explicit_user_legacy_db_fallback_for_case_without_supplied_official_row"
        self.pin["source"]["official"] = []
        for name, value in {
            "ORG": two.ORG,
            "PERIOD": two.PERIOD,
            "YEAR": two.YEAR,
            "SCHEMA": two.SCHEMA,
            "CASES": [self.pin],
        }.items():
            self.patches.enter_context(patch.object(spec, name, copy.deepcopy(value)))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, contract=spec, resource=spec.RESOURCE, **kwargs)

    def test_single_fallback_apply_repeat_undo_preserves_other_load_and_all_bodies(self):
        before = state.snapshot(self.org, contract=spec)
        other = self.rows[1].subject_id
        dry = self.run_repair()
        self.assertEqual(dry["rows"], 1)
        result = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        after = state.snapshot(self.org, contract=spec)
        self.assertEqual(repair.protected(before), repair.protected(after))
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.rows[1].refresh_from_db()
        self.assertEqual(self.rows[1].subject_id, other)
        pending = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=pending["baseline"])
        self.assertEqual(state.snapshot(self.org, contract=spec), before)

    def test_fallback_never_creates_syllabus_or_fills_any_missing_cell(self):
        labels = (
            "syllabus.Syllabus",
            "syllabus.SyllabusVersion",
            "syllabus.SyllabusSection",
            "registrar.Lesson",
            "registrar.LessonMark",
        )
        counts = {label: apps.get_model(label).objects.count() for label in labels}
        dry = self.run_repair()
        self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(counts, {label: apps.get_model(label).objects.count() for label in labels})

    def test_another_contract_receipt_cannot_undo_the_fallback(self):
        dry = repair.run(organization=self.org, actor=self.actor)
        other = repair.run(organization=self.org, actor=self.actor, apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(RepairError, "exact_receipt"):
            self.run_repair(undo=other["receipt"])
        self.assertEqual(other["status"], "applied")

    def test_readonly_full_graph_and_command_are_single_case_and_safe(self):
        data = collect_vefa_catalog_references()
        self.assertEqual(data["vefa_catalog_reference_scope"][0]["rows"], [self.pin["row_id"]])
        self.assertFalse(data["vefa_catalog_reference_scope"][0]["eligible_for_apply"])
        output = StringIO()
        call_command("repair_reviewed_vefa_catalog", actor=self.actor.username, stdout=output)
        self.assertIn("reviewed_vefa_catalog: status=dry_run rows=1 applied=0", output.getvalue())
        m = host()
        self.assertEqual(
            m.summary(
                output.getvalue().strip(), apply=False, undo="", prefix="reviewed_vefa_catalog: ", expected_rows=1
            ),
            output.getvalue().strip(),
        )
        with self.assertRaises(ValueError):
            m.summary(output.getvalue().strip(), apply=False, undo="")

    def test_missing_canonical_cell_and_wrong_donor_body_still_hold(self):
        self.syllabi[0][1].sections.filter(section_id="desc").update(data={"description": "contrary"})
        with self.assertRaisesRegex(RepairError, "source_body_changed"):
            self.run_repair()
