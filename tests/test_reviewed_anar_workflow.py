"""Fixed Anar host rejects arbitrary scope/output, changed HEAD and unsafe errors."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
spec = importlib.util.spec_from_file_location("anar_host", ROOT / "scripts/ops/reviewed_anar_authorship.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
SHA = "a" * 64
RECEIPT = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "extra",
    [
        {"teacher": 9490},
        {"command": "anything"},
        {"source": "other"},
        {"apply": "yes"},
        {"apply": True},
        {"apply": True, "baseline": SHA, "confirm": "wrong"},
        {"actor": "bad;command"},
        {"undo": "not_uuid"},
    ],
)
def test_rejects_unsafe_or_unconfirmed_inputs(extra):
    with pytest.raises(ValueError):
        host.inputs({"actor": "reviewed.admin", **extra})


def test_fixed_cli_and_safe_summary(monkeypatch):
    run = Mock(
        return_value=Mock(
            returncode=0,
            stderr="",
            stdout=f"reviewed_anar_authorship: status=dry_run applied=0 count=28 baseline={SHA} receipt=none\n",
        )
    )
    verify = Mock()
    monkeypatch.setattr(host, "verify_head", verify)
    monkeypatch.setattr(host.subprocess, "run", run)
    host.execute(
        {"actor": "reviewed.admin"}, {"GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}
    )
    verify.assert_called_once_with("b" * 40)
    args = run.call_args.args[0]
    assert args[-3:] == ["repair_reviewed_anar_authorship", "--actor", "reviewed.admin"]


@pytest.mark.parametrize(
    "line",
    [
        f"reviewed_anar_authorship: status=dry_run applied=0 count=27 baseline={SHA} receipt=none",
        f"reviewed_anar_authorship: status=applied applied=1 count=28 baseline={SHA} receipt={RECEIPT}",
        f"reviewed_anar_authorship: status=already_applied applied=0 count=28 baseline={SHA} receipt={RECEIPT}",
        "traceback plaintext",
    ],
)
def test_dry_summary_cannot_claim_applied_or_wrong_count(line):
    with pytest.raises(ValueError):
        host.summary(line, apply=False, undo="")


def test_failure_is_static_allowlisted_only():
    assert host.safe_failure("CommandError: anar_reviewed_cells_changed\n") == "anar_reviewed_cells_changed"
    for raw in [
        "CommandError: anar_arbitrary_secret\n",
        "Traceback: secret",
        "CommandError: anar_reviewed_cells_changed\nsecret",
    ]:
        assert host.safe_failure(raw) == "reviewed_anar_command_refused"


def test_head_failure_stops_before_docker(monkeypatch):
    run = Mock()
    monkeypatch.setattr(host.subprocess, "run", run)
    monkeypatch.setattr(host, "verify_head", Mock(side_effect=ValueError("head_changed")))
    with pytest.raises(ValueError):
        host.execute(
            {"actor": "reviewed.admin"}, {"GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}
        )
    run.assert_not_called()
