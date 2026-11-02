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
spec = importlib.util.spec_from_file_location("elshen_operator", OPS / "reviewed_elshen_duplicates.py")
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def payload(**changes):
    return operator.PREFIX + json.dumps(
        {
            "status": "dry_run",
            "applied": 0,
            "count": 10,
            "contributions": 18,
            "hours": 345,
            "teacher_before": 915,
            "teacher_after": 570,
            "baseline": "a" * 64,
            "receipt": "none",
            "protected": "b" * 64,
            **changes,
        }
    )


def test_fixed_dry_summary():
    assert operator.summary(payload(), apply=False, undo="").startswith(operator.PREFIX)


@pytest.mark.parametrize(
    "changes",
    [{"hours": 344}, {"contributions": True}, {"arbitrary": "secret"}, {"protected": "oops"}, {"status": "applied"}],
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
        "repair_reviewed_elshen_duplicates",
        "--actor",
        "operator",
    ]


def test_apply_requires_fresh_baseline_and_confirmation():
    with pytest.raises(ValueError):
        operator.inputs({"actor": "operator", "apply": True})
    assert operator.inputs({"actor": "operator", "apply": True, "baseline": "a" * 64, "confirm": "APPLY"})[2]


def test_undo_and_idempotent_modes_require_exact_totals():
    receipt = "11111111-2222-3333-4444-555555555555"
    assert operator.summary(
        payload(status="undone", applied=1, receipt=receipt, teacher_before=570, teacher_after=915),
        apply=True,
        undo=receipt,
    )
    assert operator.summary(
        payload(status="already_applied", count=0, contributions=0, hours=0, receipt=receipt, teacher_before=570),
        apply=False,
        undo="",
    )
    with pytest.raises(ValueError):
        operator.summary(payload(status="applied", applied=1, receipt=receipt, teacher_after=540), apply=True, undo="")
