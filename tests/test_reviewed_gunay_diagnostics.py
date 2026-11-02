"""Closed host protocol: fixed native scope, no arbitrary commands or report payloads."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

OPS = Path(__file__).resolve().parents[1] / "scripts/ops"
sys.path.insert(0, str(OPS))
spec = importlib.util.spec_from_file_location("gunay_diagnostic_operator", OPS / "reviewed_gunay_ethnography.py")
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def test_safe_native_literal_guard_only():
    assert operator.safe_failure("CommandError: gunay_academic_graph_changed\n") == "gunay_academic_graph_changed"


@pytest.mark.parametrize(
    "raw",
    [
        "CommandError: gunay_unknown_guard\n",
        "CommandError: gunay_academic_graph_changed\nsecret",
        "secret\nCommandError: gunay_academic_graph_changed\n",
        "CommandError: user@example.com",
        "CommandError: gunay_academic_graph_changed\r\n",
        "CommandError: gunay_academic_graph_changed\n\n",
        "CommandError: gunay_academic_graph_changed token=secret",
        "x" * 257,
        None,
    ],
)
def test_failure_diagnostic_never_echoes_unknown_or_private_text(raw):
    assert operator.safe_failure(raw) == "reviewed_gunay_host_refused"


@pytest.mark.parametrize(
    "stdout,returncode,expected",
    [
        ("", 1, "gunay_academic_graph_changed"),
        ("private-output", 1, "reviewed_gunay_host_refused"),
        ("synthetic-summary", 0, "gunay_native_command_refused"),
    ],
)
def test_failed_command_diagnostic_and_success_stderr_policy(stdout, returncode, expected):
    env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "c" * 40}
    result = SimpleNamespace(
        stdout=stdout, stderr="CommandError: gunay_academic_graph_changed\n", returncode=returncode
    )
    with patch.object(operator, "verify_head"), patch.object(operator.subprocess, "run", return_value=result):
        with pytest.raises(ValueError, match="^" + expected + "$"):
            operator.execute({"actor": "operator"}, env)


def test_safe_guard_allowlist_is_native_literal_subset():
    import ast

    root = OPS.parents[1]
    files = [
        root / "apps/workload/services/reviewed_gunay_ethnography_state.py",
        root / "apps/workload/services/reviewed_gunay_ethnography_repair.py",
        root / "apps/workload/management/commands/repair_reviewed_gunay_ethnography.py",
    ]
    literals = {
        n.value
        for f in files
        for n in ast.walk(ast.parse(f.read_text()))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert operator.SAFE_GUARDS <= literals
    assert operator.SAFE_GUARDS


def test_main_emits_only_closed_guard_or_generic_refusal(capsys):
    with (
        patch.object(operator.Path, "read_bytes", return_value=b'{"inputs": {}}'),
        patch.dict(operator.os.environ, {"GITHUB_EVENT_PATH": "unused"}),
        patch.object(operator, "execute", side_effect=operator.Refused("gunay_academic_graph_changed")),
    ):
        assert operator.main() == 2
    assert capsys.readouterr().err == "gunay_academic_graph_changed\n"
    with (
        patch.object(operator.Path, "read_bytes", return_value=b'{"inputs": {}}'),
        patch.dict(operator.os.environ, {"GITHUB_EVENT_PATH": "unused"}),
        patch.object(operator, "execute", side_effect=ValueError("private exception")),
    ):
        assert operator.main() == 2
    assert capsys.readouterr().err == "reviewed_gunay_host_refused\n"
