"""Fixed production host contract, fresh hashes, receipt undo and private-output guards."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
SPEC = importlib.util.spec_from_file_location("leyla_workflow_host", ROOT / "scripts/ops/reviewed_leyla_catalog.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
HASH = "a" * 64
SCHEDULE = "b" * 64
RECEIPT = "11111111-2222-4333-8444-555555555555"
NEW_RECEIPT = "22222222-3333-4444-8555-666666666666"
ENV = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}


def raw(status="dry_run", **changes):
    repeated = status.startswith("already_")
    values = dict(
        status=status,
        rows=0 if repeated else 2,
        schedule="none" if repeated else SCHEDULE,
        slots=0 if repeated else 6,
        applied=int(status in {"applied", "undone"}),
        baseline=HASH,
        receipt="none" if status == "dry_run" else NEW_RECEIPT if status == "undone" else RECEIPT,
    )
    values.update(changes)
    return host.PREFIX + " ".join(f"{key}={value}" for key, value in values.items()) + "\n"


@pytest.mark.parametrize(
    "status,apply,undo",
    [
        ("dry_run", False, ""),
        ("dry_run", False, RECEIPT),
        ("applied", True, ""),
        ("undone", True, RECEIPT),
        ("already_applied", False, ""),
        ("already_applied", True, ""),
        ("already_undone", False, ""),
        ("already_undone", True, ""),
        ("already_undone", False, RECEIPT),
        ("already_undone", True, RECEIPT),
    ],
)
def test_exact_service_status_contract(status, apply, undo):
    text = raw(status)
    assert host.summary(text, apply=apply, undo=undo, baseline=HASH).endswith(values_receipt(status))


def values_receipt(status):
    return "receipt=" + ("none" if status == "dry_run" else NEW_RECEIPT if status == "undone" else RECEIPT)


@pytest.mark.parametrize(
    "changes",
    [
        {"rows": 3},
        {"rows": 1},
        {"slots": 5},
        {"slots": 7},
        {"applied": 1},
        {"receipt": RECEIPT},
        {"schedule": "none"},
        {"baseline": "wrong"},
        {"schedule": "B" * 64},
        {"status": "applied"},
    ],
)
def test_summary_changed_scope_mode_and_missing_hashes_fail_closed(changes):
    with pytest.raises(ValueError):
        host.summary(raw(**changes), apply=False, undo="")


@pytest.mark.parametrize("status", ["already_applied", "already_undone"])
@pytest.mark.parametrize(
    "changes", [{"rows": 2}, {"slots": 6}, {"schedule": SCHEDULE}, {"receipt": "none"}, {"applied": 1}]
)
def test_repeat_cannot_claim_writes_or_lose_receipt(status, changes):
    with pytest.raises(ValueError):
        host.summary(raw(status, **changes), apply=False, undo="")


@pytest.mark.parametrize(
    "text", ["secret\n" + raw(), raw() + "secret\n", raw() + "\n", raw()[:-1] + " private=secret", "x" * 4097, "", "\n"]
)
def test_summary_rejects_extra_or_private_output(text):
    with pytest.raises(ValueError):
        host.summary(text, apply=False, undo="")


@pytest.mark.parametrize(
    "status,apply,undo",
    [
        ("undone", True, ""),
        ("applied", True, RECEIPT),
        ("already_applied", False, RECEIPT),
        ("dry_run", True, ""),
        ("applied", False, ""),
    ],
)
def test_summary_status_cannot_cross_forward_undo_or_write_mode(status, apply, undo):
    with pytest.raises(ValueError):
        host.summary(raw(status), apply=apply, undo=undo)


def test_output_must_match_supplied_hashes_and_undo_repeat_receipt():
    with pytest.raises(ValueError, match="baseline_changed"):
        host.summary(raw("applied"), apply=True, undo="", baseline="c" * 64)
    with pytest.raises(ValueError, match="schedule_changed"):
        host.summary(raw("applied"), apply=True, undo="", schedule_sha="c" * 64)
    with pytest.raises(ValueError, match="undo_receipt_changed"):
        host.summary(raw("already_undone"), apply=False, undo=NEW_RECEIPT)
    # An undo write has its own audit receipt, distinct from the original apply.
    assert NEW_RECEIPT in host.summary(raw("undone"), apply=True, undo=RECEIPT)


@pytest.mark.parametrize(
    "key", ["org", "teacher", "group", "offering", "file", "sha256", "source_tag", "hours", "command", "target"]
)
def test_runtime_scope_expansion_is_impossible(key):
    with pytest.raises(ValueError):
        host.inputs({"actor": "superadmin", key: "untrusted"})


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"actor": "--apply"},
        {"actor": "x\nsecret"},
        {"actor": "x", "apply": 1},
        {"actor": "x", "apply": "yes"},
        {"actor": "x", "baseline": True},
        {"actor": "x", "undo": "bad"},
        {"actor": "x", "schedule_sha": "C" * 64},
        {"actor": "x", "apply": True},
        {"actor": "x", "apply": True, "baseline": HASH, "confirm": "APPLY"},
        {"actor": "x", "apply": True, "baseline": HASH, "schedule_sha": SCHEDULE, "confirm": "apply"},
        {"actor": "x", "confirm": "APPLY"},
        {"actor": "x", "undo": RECEIPT, "schedule_sha": SCHEDULE},
    ],
)
def test_bad_inputs_stop_before_production_access(value):
    with pytest.raises(ValueError):
        host.inputs(value)


def test_forward_and_undo_args_are_fixed_cli_flags():
    _, args, apply, undo = host.inputs(
        {"actor": "x", "apply": "true", "baseline": HASH, "schedule_sha": SCHEDULE, "confirm": "APPLY"}
    )
    assert (apply, undo) == (True, "")
    assert args == ["--actor", "x", "--expected-baseline", HASH, "--expected-schedule-sha", SCHEDULE, "--apply"]
    _, args, apply, undo = host.inputs(
        {"actor": "x", "apply": True, "baseline": HASH, "undo": RECEIPT, "confirm": "APPLY"}
    )
    assert undo == RECEIPT and apply
    assert args == ["--actor", "x", "--expected-baseline", HASH, "--undo", RECEIPT, "--apply"]
    assert host.inputs({"actor": "x", "undo": RECEIPT})[2] is False


def test_changed_deployed_head_prevents_even_dry_runtime(monkeypatch):
    monkeypatch.setattr(host, "verify_head", lambda _: (_ for _ in ()).throw(ValueError("deployed_head_changed")))
    calls = []
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="deployed_head_changed"):
        host.execute({"actor": "x"}, ENV)
    assert calls == []


def test_real_head_verifier_rejects_invalid_and_different_running_build(monkeypatch):
    verifier = sys.modules[host.verify_head.__module__]
    calls = []

    def command(argv):
        calls.append(argv)
        return json.dumps({"sha": "c" * 40})

    monkeypatch.setattr(verifier, "command", command)
    with pytest.raises(ValueError, match="pinned_head_required"):
        host.verify_head("not-a-head")
    assert not calls
    with pytest.raises(ValueError, match="deployed_head_changed"):
        host.verify_head("a" * 40)
    assert calls == [["docker", "exec", host.CONTAINER, "cat", "/app/build-info.json"]]
    host.verify_head("c" * 40)


@pytest.mark.parametrize(
    "key,value", [("GITHUB_RUN_ID", "0"), ("GITHUB_RUN_ATTEMPT", "1;echo"), ("GITHUB_RUN_ID", None)]
)
def test_workflow_identity_checked_before_head_and_cli(key, value, monkeypatch):
    calls = []
    monkeypatch.setattr(host, "verify_head", lambda head: calls.append(head))
    with pytest.raises(ValueError):
        host.execute({"actor": "x"}, {**ENV, key: value})
    assert not calls


def test_fixed_runtime_command_and_exact_order(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(host, "verify_head", lambda head: calls.append(("head", head)))

    def run(argv, **kwargs):
        calls.append(("cli", argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=raw(), stderr="")

    monkeypatch.setattr(host.subprocess, "run", run)
    host.execute({"actor": "x"}, ENV)
    assert calls[0] == ("head", ENV["GITHUB_SHA"])
    assert calls[1][1] == [
        "docker",
        "exec",
        host.CONTAINER,
        "python",
        "manage.py",
        "repair_reviewed_leyla_catalog",
        "--actor",
        "x",
    ]
    assert calls[1][2] == {"capture_output": True, "text": True, "timeout": 180}
    assert capsys.readouterr().out == "::add-mask::x\n" + raw()


@pytest.mark.parametrize(
    "stderr",
    [
        "SQL secret password\n",
        "CommandError: leyla_private_password\n",
        "CommandError: leyla_canonical_cells_changed\nsecret",
        "x" * 65537,
    ],
)
def test_untrusted_failure_text_never_becomes_diagnostic(stderr):
    assert host.safe_failure(stderr) == "reviewed_leyla_command_refused"


def test_only_exact_known_service_guard_is_reported():
    assert host.safe_failure("CommandError: leyla_canonical_cells_changed\n") == "leyla_canonical_cells_changed"


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(returncode=0, stdout=raw(), stderr="private"),
        SimpleNamespace(returncode=1, stdout="private", stderr="private"),
        SimpleNamespace(returncode=0, stdout=raw() + "private", stderr=""),
        SimpleNamespace(returncode=0, stdout="x" * 65537, stderr=""),
    ],
)
def test_failed_or_dirty_command_stdout_not_printed(result, monkeypatch, capsys):
    monkeypatch.setattr(host, "verify_head", lambda _: None)
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: result)
    with pytest.raises(ValueError):
        host.execute({"actor": "x"}, ENV)
    assert "private" not in capsys.readouterr().out


def test_main_never_echoes_exception_body(tmp_path, monkeypatch, capsys):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"actor": "x"}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(host, "execute", lambda *a: (_ for _ in ()).throw(RuntimeError("private SQL password")))
    assert host.main() == 2
    assert capsys.readouterr().err == "reviewed_leyla_host_refused\n"


def test_workflow_is_standalone_production_serialized_without_assets_or_secrets():
    raw_workflow = (ROOT / ".github/workflows/reviewed-leyla-catalog.yml").read_text()
    workflow = yaml.safe_load(raw_workflow)
    dispatch = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    assert set(dispatch) == {"actor", "baseline", "schedule_sha", "undo", "apply", "confirm"}
    assert dispatch["apply"]["default"] is False
    assert workflow["concurrency"] == {"group": "production-deploy", "cancel-in-progress": False}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["reviewed"]
    assert job["environment"] == "production" and job["runs-on"] == ["self-hosted"]
    assert "reviewed_leyla_catalog.py" in raw_workflow
    assert "secrets." not in raw_workflow and "github.event.inputs" not in raw_workflow
    assert job["steps"][0]["with"]["persist-credentials"] is False
