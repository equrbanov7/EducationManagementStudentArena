"""Encrypted roster plan routing and guarded Bash arguments; no production access."""

from django.test import SimpleTestCase

from . import test_reviewed_source_workflow as workflow_helpers

ROOT = workflow_helpers.ROOT


class TspxRosterWorkflowTests(SimpleTestCase):
    command = "repair_tspx_legacy_roster"
    prefix = "tspx-roster"
    filename = "tspx_roster"
    shell = workflow_helpers.ReviewedSourceWorkflowTests.shell

    def invoke(self, **kwargs):
        return self.shell(COMMAND=self.command, ROSTER_TAG=self.prefix + "-20261030", **kwargs)

    def test_fixed_manifest_needs_no_source_lines_but_apply_needs_baseline(self):
        result = self.invoke(ROW_GROUP="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"/tmp/{self.filename}_42.json", result.stdout)
        self.assertNotIn("--lines", result.stdout)
        self.assertNotEqual(self.invoke(APPLY="true").returncode, 0)
        result = self.invoke(APPLY="true", ROW_SUBJECT="b" * 64)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_exact_undo_token_and_fresh_baseline_are_accepted(self):
        batch = self.prefix + "-20261030-020304-abcdef12"
        self.assertIn("--undo\n" + batch, self.invoke(ROW_SUBJECT=batch).stdout)
        self.assertNotEqual(self.invoke(ROW_SUBJECT=batch, APPLY="true").returncode, 0)
        self.assertEqual(self.invoke(ROW_SUBJECT=batch + ":" + "b" * 64, APPLY="true").returncode, 0)
        for value in (batch + "\n", "source-20261030-020304-abcdef12", batch + ";uname"):
            self.assertNotEqual(self.invoke(ROW_SUBJECT=value).returncode, 0)

    def test_encrypted_asset_cleanup_and_filtered_runner_are_wired(self):
        result = self.invoke(script="reviewed_source_asset.sh", output='printf "%s:%s" "$asset" "$target"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{self.prefix}.json.enc:/tmp/{self.filename}_42.json")
        workflow = (ROOT / ".github/workflows/prod-data-ops.yml").read_text()
        self.assertIn("          - " + self.command, workflow)
        self.assertIn(f"/tmp/{self.filename}_*.json", workflow)
        self.assertIn(f'[ "$COMMAND" = "{self.command}" ]', workflow)


class Si135RosterWorkflowTests(TspxRosterWorkflowTests):
    command = "repair_si135_legacy_roster"
    prefix = "si135-roster"
    filename = "si135_roster"


class BiMu536RosterWorkflowTests(TspxRosterWorkflowTests):
    command = "repair_bi_mu536_legacy_roster"
    prefix = "bimu536-roster"
    filename = "bi_mu536_roster"
