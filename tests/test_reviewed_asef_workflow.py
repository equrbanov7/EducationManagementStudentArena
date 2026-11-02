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
