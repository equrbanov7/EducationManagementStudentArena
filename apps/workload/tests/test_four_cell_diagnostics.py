"""No exception messages, SQL, arbitrary tokens or forged multiline diagnostics escape."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError
from django.test import SimpleTestCase

from apps.workload.services import four_cell_diagnostics as safe


class FourDiagnosticsTests(SimpleTestCase):
    def test_whitelisted_guard_and_code_location_only(self):
        try:
            raise ValueError("four_cell_audit_byte_budget_exceeded")
        except ValueError as exc:
            fields = safe.describe(exc, "capture")
        self.assertEqual(fields["guard"], "four_cell_audit_byte_budget_exceeded")
        self.assertEqual(fields["class"], "valueerror")
        self.assertEqual(fields["module"], "test_four_cell_diagnostics")
        self.assertEqual(fields["function"], "test_whitelisted_guard_and_code_location_only")
        self.assertGreater(fields["line"], 0)
        line = "four_cell_history_diagnostic: " + safe.render(fields)
        self.assertEqual(safe.parse(line), fields)

    def test_sql_and_pii_exception_values_and_unknown_class_names_are_not_tokens(self):
        for value in [
            "PASSWORD_PRIVATE_CONTACT SELECT * FROM users",
            "four_cell_audit_byte_budget_exceeded\nPRIVATE",
            {"password": "PRIVATE"},
        ]:
            exc = ProgrammingError(value)
            fields = safe.describe(exc, "capture")
            self.assertEqual(fields["guard"], "unclassified")
            self.assertNotIn("PRIVATE", safe.render(fields))
            self.assertNotIn("SELECT", safe.render(fields))
        custom = type("private_contact_person", (Exception,), {})
        fields = safe.describe(custom("PRIVATE"), "untrusted-stage")
        self.assertEqual(fields["class"], "exception")
        self.assertEqual(fields["stage"], "input")

    def test_cause_class_is_finite_and_never_cause_sql_value(self):
        try:
            try:
                raise type("UndefinedColumn", (Exception,), {})("PRIVATE_COLUMN SQL")
            except Exception as cause:
                raise ProgrammingError("PRIVATE SELECT") from cause
        except ProgrammingError as exc:
            fields = safe.describe(exc, "capture")
        self.assertEqual(fields["cause"], "undefinedcolumn")
        self.assertNotIn("PRIVATE", safe.render(fields))

    def test_parser_refuses_unlisted_code_extra_body_duplicate_and_ansi(self):
        fields = safe.describe(ValueError("four_cell_history_row_budget_exceeded"), "capture")
        line = "four_cell_history_diagnostic: " + safe.render(fields)
        for bad in [
            line + " PRIVATE",
            line.replace("guard=four_cell_history_row_budget_exceeded", "guard=PRIVATE"),
            line + "\n" + line,
            "\x1b[0m" + line,
        ]:
            self.assertIsNone(safe.parse(bad))

    def test_actual_command_preserves_safe_guard_but_raw_error_never_reaches_streams(self):
        for exc, expected in [
            (ValueError("four_cell_audit_byte_budget_exceeded"), "guard=four_cell_audit_byte_budget_exceeded"),
            (ProgrammingError("SQL PASSWORD_PRIVATE"), "class=programmingerror"),
        ]:
            stdout, stderr = StringIO(), StringIO()
            with patch("apps.workload.management.commands.export_wcu_four_cell_history.capture", side_effect=exc):
                with self.assertRaisesMessage(CommandError, "four_cell_history_export_refused"):
                    call_command(
                        "export_wcu_four_cell_history",
                        actor="PRIVATE_OPERATOR",
                        public_key="PRIVATE_PATH",
                        output="PRIVATE_PATH",
                        stdout=stdout,
                        stderr=stderr,
                    )
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(expected, stderr.getvalue())
            self.assertNotIn("PRIVATE", stderr.getvalue())
            self.assertNotIn("SQL", stderr.getvalue())

    def test_source28_closed_cause_chain_prefers_known_inner_guard_and_is_cycle_bounded(self):
        cause = ValueError("source28_exact_current_kind_owner_allocation_changed")
        outer = type("ContentError", (ValueError,), {})("reviewed_source28_fresh_history_or_allocation_unavailable")
        outer.__cause__ = cause
        fields = safe.describe(outer, "source28_history")
        self.assertEqual(fields["class"], "contenterror")
        self.assertEqual(fields["guard"], "source28_exact_current_kind_owner_allocation_changed")
        line = "reviewed_source28_diagnostic: " + safe.render(fields)
        self.assertEqual(safe.parse(line, prefix="reviewed_source28_diagnostic"), fields)
        cause.__cause__ = outer
        self.assertEqual(safe.describe(outer, "source28_undo")["guard"], fields["guard"])
        self.assertIsNone(safe.parse(line, prefix="PRIVATE_arbitrary_prefix"))

    def test_english_prefix_is_explicit_and_other_names_stay_closed(self):
        fields = safe.describe(ValueError("source_capture_failed"), "capture")
        line = "english_level_diagnostic: " + safe.render(fields)
        self.assertEqual(safe.parse(line, prefix="english_level_diagnostic"), fields)
        self.assertIsNone(safe.parse(line))
        self.assertIsNone(safe.parse(line, prefix="unreviewed_diagnostic"))
