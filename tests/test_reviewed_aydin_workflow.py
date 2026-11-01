"""Fixed host route; no execution in offline tests, no alternate command/source selector."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
SPEC = importlib.util.spec_from_file_location("aydin_host_contract", ROOT / "scripts/ops/reviewed_aydin_lineage.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
HASH = "a" * 64
RECEIPT = "11111111-2222-4333-8444-555555555555"
ENV = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}


def raw(status="dry_run", changed=0, receipt="none", baseline=HASH):
    return f"{host.PREFIX}status={status} applied={changed} baseline={baseline} receipt={receipt}\n"


@pytest.mark.parametrize("value,expected", [(False, False), (True, True), ("false", False), ("true", True)])
def test_actual_github_boolean_and_string_inputs(value, expected):
    _, args, apply, _ = host.inputs(
        {"actor": "operator", "apply": value, "baseline": HASH, "confirm": "APPLY" if expected else ""}
    )
    assert apply is expected
    assert ("--apply" in args) is expected


@pytest.mark.parametrize(
    "extra",
    [
        {"command": "shell"},
        {"tenant": "other"},
        {"targets": "other"},
        {"schedule_sha": HASH},
        {"apply": 1},
        {"apply": "FALSE"},
        {"baseline": "bad"},
        {"undo": "bad"},
        {"apply": True},
        {"confirm": "APPLY"},
    ],
)
def test_closed_input_scope_and_confirmation(extra):
    with pytest.raises(ValueError):
        host.inputs({"actor": "operator", **extra})


@pytest.mark.parametrize(
    "status,apply,undo,changed,receipt",
    [
        ("dry_run", False, "", 0, "none"),
        ("dry_run", False, RECEIPT, 0, "none"),
        ("applied", True, "", 1, RECEIPT),
        ("undone", True, RECEIPT, 1, RECEIPT),
        ("already_applied", False, "", 0, RECEIPT),
        ("already_undone", True, RECEIPT, 0, RECEIPT),
    ],
)
def test_exact_safe_summary(status, apply, undo, changed, receipt):
    assert host.summary(raw(status, changed, receipt), apply=apply, undo=undo, baseline=HASH).startswith(host.PREFIX)


@pytest.mark.parametrize(
    "value",
    [
        raw("applied", 1, RECEIPT),
        raw(receipt=RECEIPT),
        raw(changed=1),
        raw(baseline="bad"),
        raw() + "PRIVATE_GRADE_BODY\n",
    ],
)
def test_dry_cannot_claim_writes_or_extra_output(value):
    with pytest.raises(ValueError):
        host.summary(value, apply=False, undo="")


def test_deployed_head_precedes_the_only_fixed_command(monkeypatch):
    calls = []
    monkeypatch.setattr(host, "verify_head", lambda value: calls.append(("head", value)))

    def command(argv, **options):
        calls.append(("command", argv))
        assert options == dict(capture_output=True, text=True, timeout=180)
        return SimpleNamespace(returncode=0, stdout=raw(), stderr="")

    monkeypatch.setattr(host.subprocess, "run", command)
    host.execute({"actor": "operator", "apply": "false"}, ENV)
    assert calls[0] == ("head", ENV["GITHUB_SHA"])
    assert calls[1][1] == [
        "docker",
        "exec",
        host.CONTAINER,
        "python",
        "manage.py",
        "repair_reviewed_aydin_lineage",
        "--actor",
        "operator",
    ]


def test_head_refusal_prevents_any_cli(monkeypatch):
    def refused(_head):
        raise ValueError("drift")

    monkeypatch.setattr(host, "verify_head", refused)
    monkeypatch.setattr(host.subprocess, "run", lambda *_a, **_kw: pytest.fail("must not execute"))
    with pytest.raises(ValueError):
        host.execute({"actor": "operator"}, ENV)


def test_failure_codes_never_echo_arbitrary_command_output():
    assert host.safe_failure("CommandError: aydin_body_changed\n") == "aydin_body_changed"
    assert host.safe_failure("CommandError: aydin_PRIVATE_PASSWORD\n") == "reviewed_aydin_command_refused"
    assert host.safe_failure("PRIVATE_GRADE_BODY") == "reviewed_aydin_command_refused"


def test_workflow_uses_production_lock_environment_and_pinned_checkout():
    workflow = yaml.safe_load((ROOT / ".github/workflows/reviewed-aydin-lineage.yml").read_text())
    event = workflow.get("on", workflow.get(True))["workflow_dispatch"]
    assert set(event["inputs"]) == {"actor", "baseline", "undo", "apply", "confirm"}
    assert workflow["concurrency"] == {"group": "production-deploy", "cancel-in-progress": False}
    job = workflow["jobs"]["reviewed"]
    assert job["environment"] == "production"
    assert job["steps"][0]["uses"] == "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    assert job["steps"][1]["run"] == "python3 scripts/ops/reviewed_aydin_lineage.py"
