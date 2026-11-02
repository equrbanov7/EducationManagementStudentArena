"""Fixed İbrahim host rejects arbitrary scope/output, changed HEAD and unsafe errors."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
spec = importlib.util.spec_from_file_location("ibrahim_host", ROOT / "scripts/ops/reviewed_ibrahim_authorship.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
SHA = "a" * 64
RECEIPT = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "extra",
    [
        {"teacher": 8311},
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
            stdout=f"reviewed_ibrahim_authorship: status=dry_run applied=0 count=18 baseline={SHA} receipt=none\n",
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
    assert args[-3:] == ["repair_reviewed_ibrahim_authorship", "--actor", "reviewed.admin"]


@pytest.mark.parametrize(
    "line",
    [
        f"reviewed_ibrahim_authorship: status=dry_run applied=0 count=27 baseline={SHA} receipt=none",
        f"reviewed_ibrahim_authorship: status=applied applied=1 count=18 baseline={SHA} receipt={RECEIPT}",
        f"reviewed_ibrahim_authorship: status=already_applied applied=0 count=18 baseline={SHA} receipt={RECEIPT}",
        "traceback plaintext",
    ],
)
def test_dry_summary_cannot_claim_applied_or_wrong_count(line):
    with pytest.raises(ValueError):
        host.summary(line, apply=False, undo="")


def test_failure_is_static_allowlisted_only():
    assert host.safe_failure("CommandError: ibrahim_reviewed_cells_changed\n") == "ibrahim_reviewed_cells_changed"
    for raw in [
        "CommandError: ibrahim_arbitrary_secret\n",
        "Traceback: secret",
        "CommandError: ibrahim_reviewed_cells_changed\nsecret",
    ]:
        assert host.safe_failure(raw) == "reviewed_ibrahim_command_refused"


def test_head_failure_stops_before_docker(monkeypatch):
    run = Mock()
    monkeypatch.setattr(host.subprocess, "run", run)
    monkeypatch.setattr(host, "verify_head", Mock(side_effect=ValueError("head_changed")))
    with pytest.raises(ValueError):
        host.execute(
            {"actor": "reviewed.admin"}, {"GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}
        )
    run.assert_not_called()


def test_exact_production_scope_contract():
    import ast
    import json

    code = ast.parse((ROOT / "apps/legacy_import/services/reviewed_ibrahim_state.py").read_text())
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in code.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"ORG", "PERIOD", "SUBJECT", "TEACHER", "OFFERINGS"}
    }
    assert constants["ORG"] == "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
    assert constants["PERIOD"] == "a4f88744-8d49-4772-84ef-c28a96c3b372"
    assert constants["TEACHER"] == 8311
    pins = json.loads((ROOT / "apps/legacy_import/services/reviewed_ibrahim_pins.json").read_text())
    assert len(pins["lessons"]) == 18 and pins["marks_count"] == 243
    assert set(constants["OFFERINGS"]) == set(pins["offerings"])
    assert {p["fields"]["offering_id"] for p in pins["lessons"].values()} == set(constants["OFFERINGS"])
    assert {p["fields"]["organization_id"] for p in pins["lessons"].values()} == {constants["ORG"]}
    assert {p["legacy_pk"] for p in pins["bridge"] if p["entity_type"] == "worker"} == {"872"}
    assert {p["legacy_pk"] for p in pins["bridge"] if p["entity_type"] == "lesson_subject"} == {"847"}
    assert {p["legacy_pk"] for p in pins["bridge"] if p["entity_type"] == "group_unit"} == {"615", "671", "676"}
