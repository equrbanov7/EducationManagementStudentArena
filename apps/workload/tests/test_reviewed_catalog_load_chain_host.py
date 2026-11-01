"""One host job never applies without the exact authenticated PRE graph."""

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def module():
    with patch.dict(sys.modules), patch.object(sys, "path", [str(ROOT / "scripts/ops"), *sys.path]):
        spec = importlib.util.spec_from_file_location(
            "fixed_chain_host_test", ROOT / "scripts/ops/reviewed_catalog_load_chain.py"
        )
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result


class ChainHostTests(TestCase):
    def setUp(self):
        self.host = module()
        self.inputs = {"actor": "source.actor", "expected_graph": "b" * 64, "apply": "true", "confirm": "APPLY"}

    def line(self, status):
        return (
            "reviewed_catalog_load_chain: status="
            + status
            + " rows="
            + ("0" if status == "already_applied" else "3")
            + " applied="
            + str(int(status == "applied"))
            + " baseline="
            + "a" * 64
            + " receipt="
            + ("none" if status == "dry_run" else "00000000-0000-4000-8000-000000000001")
            + " graph="
            + "b" * 64
            + " models=50 protected_rows=600"
        )

    def test_exact_pre_graph_then_one_apply_baseline_and_zero_write_repeat(self):
        with patch.object(
            self.host, "execute", side_effect=[self.line(s) for s in ("dry_run", "applied", "already_applied")]
        ) as cli:
            result = self.host.run(self.inputs, {})
        self.assertEqual(result["status"], "already_applied")
        self.assertEqual([c.args[0]["apply"] for c in cli.call_args_list], ["false", "true", "false"])
        self.assertEqual(cli.call_args_list[1].args[0]["baseline"], "a" * 64)
        self.assertTrue(all(c.kwargs["command"] == "repair_reviewed_catalog_load_chain" for c in cli.call_args_list))

    def test_changed_pre_graph_or_missing_approval_never_applies(self):
        with patch.object(self.host, "execute", return_value=self.line("dry_run")) as cli:
            with self.assertRaises(ValueError):
                self.host.run({**self.inputs, "expected_graph": "c" * 64}, {})
            self.assertEqual(cli.call_count, 1)
        with patch.object(self.host, "execute") as cli:
            for value in (
                {**self.inputs, "expected_graph": ""},
                {**self.inputs, "apply": True},
                {**self.inputs, "teacher": "other"},
                {**self.inputs, "confirm": ""},
            ):
                with self.assertRaises(ValueError):
                    self.host.run(value, {})
            cli.assert_not_called()

    def test_failed_repeat_or_wrong_scope_never_reapplies(self):
        with patch.object(
            self.host,
            "execute",
            side_effect=[
                self.line("dry_run"),
                self.line("applied"),
                self.line("already_applied").replace("rows=0", "rows=3"),
            ],
        ) as cli:
            with self.assertRaises(ValueError):
                self.host.run(self.inputs, {})
        self.assertEqual(sum(c.args[0]["apply"] == "true" for c in cli.call_args_list), 1)
