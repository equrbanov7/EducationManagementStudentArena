"""Even plausible lowercase error values must never become public diagnostics."""

import io
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.workload.management.commands import export_wcu_english_level_evidence as command
from apps.workload.services.scoped_snapshot import SnapshotError


class EnglishCommandPrivacyTests(SimpleTestCase):
    def test_error_value_never_reaches_command_output(self):
        for error in (SnapshotError("private_contact"), ValueError("private_fin_sql")):
            stdout, stderr = io.StringIO(), io.StringIO()
            cmd = command.Command(stdout=stdout, stderr=stderr)
            with patch.object(command, "capture", side_effect=error):
                with self.assertRaisesMessage(CommandError, "english_level_evidence_refused"):
                    cmd.handle(actor="actor", file="/private/input", sha256="a" * 64)
            output = stdout.getvalue() + stderr.getvalue()
            self.assertNotIn(error.args[0], output)
            self.assertIn("english_level_diagnostic:", output)
            self.assertIn("guard=unclassified", output)
