"""Syllabus export preserves only finite codes and code locations, never source body."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError
from django.test import SimpleTestCase

from apps.workload.services.four_cell_diagnostics import parse
from apps.workload.services.scoped_snapshot import SnapshotError


class SyllabusDiagnosticsTests(SimpleTestCase):
    def command(self, exc):
        stdout, stderr = StringIO(), StringIO()
        with patch("apps.workload.management.commands.export_wcu_syllabus_content.capture", side_effect=exc):
            with self.assertRaises(CommandError) as caught:
                call_command(
                    "export_wcu_syllabus_content",
                    actor="PRIVATE_OPERATOR",
                    batch="chair-cells-027",
                    public_key="PRIVATE_PATH",
                    output="PRIVATE_PATH",
                    stdout=stdout,
                    stderr=stderr,
                )
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("PRIVATE", stderr.getvalue() + str(caught.exception))
        return str(caught.exception), stderr.getvalue()

    def test_known_snapshot_budget_code_preserved_without_reclassifying_failure(self):
        code, diagnostic = self.command(SnapshotError("syllabus_row_budget_exceeded"))
        self.assertEqual(code, "syllabus_row_budget_exceeded")
        fields = parse(diagnostic, prefix="syllabus_content_diagnostic")
        self.assertEqual(fields["guard"], code)
        self.assertEqual(fields["stage"], "capture")

    def test_value_error_shape_and_database_error_are_safe_but_keep_generic_command_refusal(self):
        for exc, guard, kind in [
            (ValueError("syllabus_body_shape_budget_exceeded"), "syllabus_body_shape_budget_exceeded", "valueerror"),
            (ProgrammingError("PRIVATE_SQL_CONTACT"), "unclassified", "programmingerror"),
        ]:
            code, diagnostic = self.command(exc)
            self.assertEqual(code, "syllabus_content_export_refused")
            fields = parse(diagnostic, prefix="syllabus_content_diagnostic")
            self.assertEqual(fields["guard"], guard)
            self.assertEqual(fields["class"], kind)

    def test_unlisted_snapshot_token_is_never_forwarded_as_guard_or_command_error(self):
        code, diagnostic = self.command(SnapshotError("PRIVATE_CONTACT"))
        self.assertEqual(code, "syllabus_content_export_refused")
        self.assertEqual(parse(diagnostic, prefix="syllabus_content_diagnostic")["guard"], "unclassified")

    def test_encrypt_stage_does_not_expose_key_or_output_path(self):
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("apps.workload.management.commands.export_wcu_syllabus_content.capture", return_value={}),
            patch(
                "apps.workload.management.commands.export_wcu_syllabus_content.save_encrypted",
                side_effect=OSError("PRIVATE_KEY_PATH"),
            ),
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "export_wcu_syllabus_content",
                    actor="x",
                    batch="chair-cells-001",
                    public_key="x",
                    output="x",
                    stdout=stdout,
                    stderr=stderr,
                )
        fields = parse(stderr.getvalue(), prefix="syllabus_content_diagnostic")
        self.assertEqual(fields["stage"], "encrypt")
        self.assertNotIn("PRIVATE", stderr.getvalue())
