"""Unexpected repair failures expose code metadata without private values."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "run_guarded_repair.py"
spec = importlib.util.spec_from_file_location("guarded_repair_diagnostics", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_unexpected_exception_has_safe_class_and_code_location(capsys):
    namespace = {}
    exec(
        compile(
            'def fail(*args):\n    raise AttributeError("private teacher SQL password")\n',
            "/app/apps/workload/services/reviewed_batch_objections.py",
            "exec",
        ),
        namespace,
    )
    with (
        patch.object(runner.sys, "argv", ["runner", "repair_reviewed_workload_batch"]),
        patch.object(runner, "prepare_connection"),
        patch("django.core.management.execute_from_command_line", namespace["fail"]),
        patch("django.db.connections") as connections,
    ):
        assert runner.main() == 1
    output = capsys.readouterr()
    assert output.err.splitlines() == [
        "CommandError: fixed_repair_unexpected_attributeerror",
        "fixed_repair_exception: class=attributeerror module=reviewed_batch_objections function=fail line=2",
    ]
    assert "private" not in output.err
    assert "password" not in output.err
    connections.close_all.assert_called_once_with()


def test_management_command_systemexit_keeps_its_status(capsys):
    with (
        patch.object(runner.sys, "argv", ["runner", "repair_reviewed_workload_batch"]),
        patch.object(runner, "prepare_connection"),
        patch("django.core.management.execute_from_command_line", side_effect=SystemExit(2)),
        patch("django.db.connections") as connections,
    ):
        with pytest.raises(SystemExit) as exc:
            runner.main()
    assert exc.value.code == 2
    assert capsys.readouterr().err == ""
    connections.close_all.assert_called_once_with()
