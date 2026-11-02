"""Closed host protocol: fixed native scope, no arbitrary commands or report payloads."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

OPS = Path(__file__).resolve().parents[1] / "scripts/ops"
sys.path.insert(0, str(OPS))
spec = importlib.util.spec_from_file_location("asef_operator", OPS / "reviewed_asef_stream.py")
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def payload(**changes):
    return operator.PREFIX + json.dumps(
        {
            "status": "dry_run",
            "applied": 0,
            "count": 1,
            "baseline": "a" * 64,
            "receipt": "none",
            "protected": "b" * 64,
            "lessons": 30,
            "marks": 485,
            "enrollments": 75,
            "stream_hours": 60,
            "journals": 3,
            **changes,
        }
    )


def test_fixed_dry_summary():
    assert operator.summary(payload(), apply=False, undo="").startswith(operator.PREFIX)


@pytest.mark.parametrize(
    "changes",
    [
        {"marks": 432},
        {"marks": 484},
        {"lessons": True},
        {"arbitrary": "secret"},
        {"protected": "oops"},
        {"status": "applied"},
    ],
)
def test_changed_summary_refused(changes):
    with pytest.raises(ValueError):
        operator.summary(payload(**changes), apply=False, undo="")


@pytest.mark.parametrize("raw", ["extra\n", "[]", "{}", "x" * 5000])
def test_unsafe_output_refused(raw):
    with pytest.raises(ValueError):
        operator.summary(raw, apply=False, undo="")


def test_fixed_native_command_and_deployed_head():
    env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "c" * 40}
    with (
        patch.object(operator, "verify_head") as verify,
        patch.object(
            operator.subprocess, "run", return_value=SimpleNamespace(stdout=payload(), stderr="", returncode=0)
        ) as run,
    ):
        operator.execute({"actor": "operator"}, env)
    verify.assert_called_once_with("c" * 40)
    assert run.call_args.args[0] == [
        "docker",
        "exec",
        operator.CONTAINER,
        "python",
        "manage.py",
        "repair_reviewed_asef_stream",
        "--actor",
        "operator",
    ]


def test_apply_requires_fresh_baseline_and_confirmation():
    with pytest.raises(ValueError):
        operator.inputs({"actor": "operator", "apply": True})
    assert operator.inputs({"actor": "operator", "apply": True, "baseline": "a" * 64, "confirm": "APPLY"})[2]


def test_native_pinned_485_mark_result_is_accepted_by_host_transport():
    from apps.workload.services import reviewed_asef_stream_repair as native

    with patch.object(native.state, "protected", return_value={}):
        result = native.result("dry_run", {}, "a" * 64)
    assert (result["lessons"], result["marks"], result["enrollments"]) == (30, 485, 75)
    output = operator.summary(operator.PREFIX + json.dumps(result), apply=False, undo="")
    assert json.loads(output[len(operator.PREFIX) :])["marks"] == 485


def test_safe_native_literal_guard_only():
    assert operator.safe_failure("CommandError: asef_source_body_changed\n") == "asef_source_body_changed"


@pytest.mark.parametrize(
    "raw",
    [
        "CommandError: asef_unknown_guard\n",
        "CommandError: asef_source_body_changed\nsecret",
        "secret\nCommandError: asef_source_body_changed\n",
        "CommandError: user@example.com",
        "CommandError: asef_source_body_changed\r\n",
        "CommandError: asef_source_body_changed\n\n",
        "CommandError: asef_source_body_changed token=secret",
        "x" * 257,
        None,
    ],
)
def test_failure_diagnostic_never_echoes_unknown_or_private_text(raw):
    assert operator.safe_failure(raw) == "reviewed_asef_host_refused"


@pytest.mark.parametrize(
    "stdout,returncode,expected",
    [
        ("", 1, "asef_source_body_changed"),
        ("private-output", 1, "reviewed_asef_host_refused"),
        (payload(), 0, "asef_native_command_refused"),
    ],
)
def test_failed_command_diagnostic_and_success_stderr_policy(stdout, returncode, expected):
    env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "c" * 40}
    result = SimpleNamespace(stdout=stdout, stderr="CommandError: asef_source_body_changed\n", returncode=returncode)
    with patch.object(operator, "verify_head"), patch.object(operator.subprocess, "run", return_value=result):
        with pytest.raises(ValueError, match="^" + expected + "$"):
            operator.execute({"actor": "operator"}, env)


def test_safe_guard_allowlist_is_native_literal_subset():
    import ast

    root = OPS.parents[1]
    files = [
        root / "apps/workload/services/reviewed_asef_stream_state.py",
        root / "apps/workload/services/reviewed_asef_stream_repair.py",
        root / "apps/workload/management/commands/repair_reviewed_asef_stream.py",
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
        patch.object(operator, "execute", side_effect=operator.Refused("asef_source_body_changed")),
    ):
        assert operator.main() == 2
    assert capsys.readouterr().err == "asef_source_body_changed\n"
    with (
        patch.object(operator.Path, "read_bytes", return_value=b'{"inputs": {}}'),
        patch.dict(operator.os.environ, {"GITHUB_EVENT_PATH": "unused"}),
        patch.object(operator, "execute", side_effect=ValueError("private exception")),
    ):
        assert operator.main() == 2
    assert capsys.readouterr().err == "reviewed_asef_host_refused\n"
