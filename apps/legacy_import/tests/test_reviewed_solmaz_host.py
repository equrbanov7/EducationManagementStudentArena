"""Offline closed inputs, privacy and strict one-source host summary contract."""

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/ops"))
loader = importlib.util.spec_from_file_location(
    "solmaz_host_test", ROOT / "scripts/ops/reviewed_solmaz_catalog.py"
)
host = importlib.util.module_from_spec(loader)
loader.loader.exec_module(host)


class SolmazHostTests(TestCase):
    def raw(self, **changes):
        fields = dict(
            status="dry_run",
            baseline="a" * 64,
            after_baseline="a" * 64,
            receipt="none",
            applied="0",
            new_source_versions="0",
            new_shares="0",
            teacher_hours="180",
            source_sha256=host.SOURCE_SHA,
            protected_models="8",
            protected_rows="550",
        )
        fields.update(changes)
        return (
            "reviewed_solmaz_catalog: "
            + " ".join(f"{k}={v}" for k, v in fields.items())
            + "\n"
        )

    def test_inputs_dry_default_and_boolean_strings_no_arbitrary_scope(self):
        self.assertFalse(host.inputs({"actor": "operator"})[2])
        self.assertFalse(host.inputs({"actor": "operator", "apply": "false"})[2])
        self.assertTrue(
            host.inputs(
                {
                    "actor": "operator",
                    "apply": "true",
                    "confirm": "APPLY",
                    "baseline": "a" * 64,
                }
            )[2]
        )
        for value in (
            {"teacher": 7722},
            {"actor": "operator", "command": "shell"},
            {"actor": "operator", "manifest": "other"},
            {"actor": "operator", "apply": 1},
            {"actor": "operator", "apply": True},
            {"actor": "operator", "baseline": "abc"},
            {"actor": "operator; echo leak"},
        ):
            with self.assertRaises(ValueError):
                host.inputs(value)

    def test_summary_exact_counts_source_budget_and_receipt(self):
        self.assertEqual(
            host.summary(self.raw(), apply=False, undo=False)["teacher_hours"], "180"
        )
        receipt = "11111111-1111-4111-8111-111111111111"
        applied = self.raw(
            status="applied",
            after_baseline="b" * 64,
            receipt=receipt,
            applied="1",
            new_source_versions="1",
            new_shares="2",
            teacher_hours="165",
        )
        self.assertEqual(
            host.summary(applied, apply=True, undo=False)["receipt"], receipt
        )
        for changes in (
            {"new_shares": "3"},
            {"teacher_hours": "165"},
            {"source_sha256": "b" * 64},
            {"protected_rows": "20001"},
            {"receipt": receipt},
            {"new_source_versions": "2"},
        ):
            with self.assertRaises(ValueError):
                host.summary(self.raw(**changes), apply=False, undo=False)
        with self.assertRaises(ValueError):
            host.summary(applied, apply=False, undo=False)
        with self.assertRaises(ValueError):
            host.summary(self.raw() + "private body\n", apply=False, undo=False)

    def test_safe_failure_exposes_only_compiled_guard_codes(self):
        self.assertEqual(
            host.safe_failure("CommandError: solmaz_source_packet_changed\n"),
            "solmaz_source_packet_changed",
        )
        self.assertEqual(
            host.safe_failure("CommandError: solmaz_secret_private_body\n"),
            "solmaz_command_refused",
        )
        self.assertEqual(
            host.safe_failure("Traceback private grade source body"),
            "solmaz_command_refused",
        )

    def test_deployment_drift_stops_before_download_or_container_execution(self):
        with (
            patch.object(host, "verify_head", side_effect=ValueError("drift")),
            patch.object(host, "source") as source,
            patch.object(host, "command") as command,
        ):
            with self.assertRaises(ValueError):
                host.execute(
                    {"actor": "operator"},
                    {
                        "GITHUB_RUN_ID": "123",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": "a" * 40,
                    },
                )
            source.assert_not_called()
            command.assert_not_called()

    def test_pin_helper_identity_guards_are_closed_literals_not_hidden(self):
        for code in (
            "solmaz_exact_official_rows_changed",
            "solmaz_group_identity_changed",
            "solmaz_subject_identity_changed",
            "solmaz_exact_teacher_allocations_changed",
            "solmaz_course_identity_changed",
            "solmaz_original_syllabi_changed",
            "solmaz_original_draft_or_approved_version_changed",
        ):
            self.assertEqual(host.safe_failure("CommandError: " + code + "\n"), code)
        for text in (
            "CommandError: solmaz_group_identity_changed private value\n",
            "CommandError: solmaz_not_a_compiled_pin_guard\n",
            "CommandError: solmaz_group_identity_changed\nextra private body",
        ):
            self.assertEqual(host.safe_failure(text), "solmaz_command_refused")
