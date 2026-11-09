import base64
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "scripts/ops"


@pytest.fixture
def operation(monkeypatch):
    monkeypatch.syspath_prepend(str(OPS))
    path = OPS / "reaudit_remediation.py"
    spec = importlib.util.spec_from_file_location("reaudit_operation_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def values(**extra):
    return {
        "operation": "cells",
        "actor": "operator",
        "release_tag": "reaudit-20261109-test",
        "cipher_sha256": "a" * 64,
        **extra,
    }


def bundle():
    plan = b'{"example":1}'
    return {
        "format": "reaudit-operation-bundle/1",
        "operation": "cells",
        "plan": base64.b64encode(plan).decode(),
        "plan_sha256": hashlib.sha256(plan).hexdigest(),
        "authority": "",
        "authority_sha256": hashlib.sha256(b"").hexdigest(),
        "offering_ids": [],
    }


def test_defaults_cannot_apply(operation):
    value = operation.inputs(values())
    assert value["apply"] is False
    args = operation.native_args(value, {"plan_sha256": "b" * 64}, "/tmp/ems-reaudit-op-1-1")
    assert "--apply" not in args


@pytest.mark.parametrize(
    "extra",
    [
        {"operation": "shell"},
        {"apply": True},
        {"apply": "yes"},
        {"actor": "x;id"},
        {"release_tag": "../main"},
        {"arbitrary": "flag"},
        {"apply": False, "confirm": "APPLY"},
    ],
)
def test_refuses_unreviewed_inputs(operation, extra):
    with pytest.raises(ValueError):
        operation.inputs(values(**extra))


def test_apply_requires_reviewed_baseline(operation):
    value = operation.inputs(values(apply=True, baseline="b" * 64, confirm="APPLY"))
    args = operation.native_args(value, {"plan_sha256": "c" * 64}, "/tmp/ems-reaudit-op-1-1")
    assert args[-1] == "--apply"
    assert args[args.index("--expected-baseline") + 1] == "b" * 64


def test_bundle_tampering_and_wrong_operation_are_rejected(operation, tmp_path):
    module = sys.modules["reaudit_private_transport"]
    value = bundle()
    path = tmp_path / "bundle.gz"
    path.write_bytes(gzip.compress(json.dumps(value).encode()))
    assert module.unpack(path, "cells")["plan"] == b'{"example":1}'
    with pytest.raises(ValueError, match="operation"):
        module.unpack(path, "syllabi")
    value["plan"] = base64.b64encode(b"tampered").decode()
    path.write_bytes(gzip.compress(json.dumps(value).encode()))
    with pytest.raises(ValueError, match="digest"):
        module.unpack(path, "cells")


def test_native_result_cannot_silently_apply_in_dry_run(operation):
    raw = "reaudit_cells: " + json.dumps({"mode": "applied", "baseline": "b" * 64})
    with pytest.raises(ValueError, match="status"):
        operation.safe_summary(raw, "reaudit_cells", operation.inputs(values()))


def test_structure_requires_authority_on_apply(operation):
    value = operation.inputs(values(operation="structure", apply=True, baseline="b" * 64, confirm="APPLY"))
    with pytest.raises(ValueError, match="authority"):
        operation.native_args(value, {"plan_sha256": "c" * 64, "authority": b""}, "/tmp/ems-reaudit-op-1-1")


@pytest.mark.parametrize("audit", ["finals", "duplicate_qb"])
def test_readonly_audit_cannot_receive_any_mutation_argument(operation, audit):
    value = {"operation": audit, "actor": "operator"}
    assert operation.inputs(value)["apply"] is False
    for key, candidate in {
        "apply": True,
        "undo": "a" * 36,
        "baseline": "b" * 64,
        "release_tag": "reaudit-20261109-plan",
    }.items():
        with pytest.raises(ValueError, match="readonly"):
            operation.inputs({**value, key: candidate})


@pytest.mark.parametrize("audit", ["finals", "duplicate_qb"])
def test_readonly_audit_runs_only_its_fixed_command_without_private_asset(operation, tmp_path, monkeypatch, audit):
    event, summary = tmp_path / "event.json", tmp_path / "summary.md"
    event.write_text(json.dumps({"inputs": {"operation": audit, "actor": "operator"}}))
    commands, heads = [], []
    native, prefix = operation.COMMANDS[audit]
    result = {"status": "read_only", "changed": 0}

    def command(args, **kwargs):
        commands.append(args)
        return prefix + ": " + json.dumps(result)

    monkeypatch.setattr(operation, "command", command)
    monkeypatch.setattr(operation, "verify_head", heads.append)
    monkeypatch.setattr(operation, "download", lambda **kw: pytest.fail("Read-only audit must not fetch a bundle"))
    operation.run(
        {
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_SHA": "a" * 40,
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
        }
    )
    base = ["docker", "exec", operation.CONTAINER, "python", operation.RUNNER]
    remote = "/tmp/ems-reaudit-op-1-1"
    assert commands == [
        base + ["prepare", remote],
        base + ["run", remote, native, "--actor", "operator"],
        base + ["cleanup", remote],
    ]
    assert heads == ["a" * 40, "a" * 40]
    assert '"changed": 0' in summary.read_text()


def test_duplicate_audit_refuses_changed_summary(operation, tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"operation": "duplicate_qb", "actor": "operator"}}))
    monkeypatch.setattr(operation, "verify_head", lambda _: None)
    monkeypatch.setattr(
        operation, "command", lambda *args, **kwargs: 'reaudit_duplicate_qb: {"status":"applied","changed":1}'
    )
    with pytest.raises(ValueError, match="must_not_mutate"):
        operation.run(
            {
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_SHA": "a" * 40,
                "GITHUB_RUN_ID": "1",
                "GITHUB_RUN_ATTEMPT": "1",
                "RUNNER_TEMP": str(tmp_path),
            }
        )


@pytest.mark.parametrize("undo,status", [("", "undone"), ("00000000-0000-0000-0000-000000000001", "applied")])
def test_native_result_direction_must_match_request(operation, undo, status):
    value = operation.inputs(values(apply=True, baseline="b" * 64, confirm="APPLY", undo=undo))
    raw = "reaudit_cells: " + json.dumps({"mode": status, "baseline": "b" * 64})
    with pytest.raises(ValueError, match="status"):
        operation.safe_summary(raw, "reaudit_cells", value)


@pytest.mark.parametrize("status,undo", [("applied", ""), ("undone", "00000000-0000-0000-0000-000000000001")])
def test_native_write_requires_receipt(operation, status, undo):
    value = operation.inputs(values(apply=True, baseline="b" * 64, confirm="APPLY", undo=undo))
    for receipt in (None, "invalid"):
        raw = "reaudit_cells: " + json.dumps({"mode": status, "baseline": "b" * 64, "receipt": receipt})
        with pytest.raises(ValueError, match="receipt"):
            operation.safe_summary(raw, "reaudit_cells", value)


def test_failed_remote_stop_preserves_local_private_files(operation, tmp_path, monkeypatch):
    folder = tmp_path / "reaudit-op-1-1"
    folder.mkdir()
    private = folder / "plan.json"
    private.write_text("synthetic")

    def refused(*args, **kwargs):
        raise ValueError("remote_stop_unconfirmed")

    monkeypatch.setattr(operation, "command", refused)
    with pytest.raises(ValueError, match="stop_unconfirmed"):
        operation.cleanup({"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "RUNNER_TEMP": str(tmp_path)})
    assert private.read_text() == "synthetic"


@pytest.mark.parametrize(
    "name,status,extra",
    [
        ("cells", "dry_run", {"complete": False, "pending": 0, "applied": 0}),
        ("cells", "already_reconciled", {"pending": 0, "applied": 0}),
        ("structure", "no_changes", {"changed": 0}),
        ("syllabi", "no_verified_actions", {"actions": [], "held": [{"code": "source_unknown"}]}),
    ],
)
def test_native_no_write_results_do_not_require_receipts(operation, name, status, extra):
    value = operation.inputs(values(operation=name, apply=True, baseline="b" * 64, confirm="APPLY"))
    key = "mode" if name == "cells" else "status"
    result = {key: status, "baseline": "b" * 64, "receipt": None, **extra}
    prefix = operation.COMMANDS[name][1]
    assert operation.safe_summary(prefix + ": " + json.dumps(result), prefix, value) == result


@pytest.mark.parametrize(
    "name,status,undo",
    [
        ("cells", "applied", False),
        ("cells", "undone", True),
        ("cells", "already_undone", True),
        ("syllabi", "applied", False),
        ("syllabi", "already_present", False),
        ("syllabi", "undone", True),
        ("structure", "applied", False),
        ("structure", "already_applied", False),
        ("structure", "undone", True),
        ("structure", "already_undone", True),
    ],
)
def test_native_receipted_status_parity(operation, name, status, undo):
    receipt = "00000000-0000-0000-0000-000000000001"
    value = operation.inputs(
        values(operation=name, apply=True, baseline="b" * 64, confirm="APPLY", undo=receipt if undo else "")
    )
    prefix = operation.COMMANDS[name][1]
    result = {"mode" if name == "cells" else "status": status, "baseline": "b" * 64, "receipt": receipt}
    assert operation.safe_summary(prefix + ": " + json.dumps(result), prefix, value) == result
