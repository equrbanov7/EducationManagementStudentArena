"""Offline executable boundaries for two standalone, fixed-scope workflows."""

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "scripts/ops"
sys.path.insert(0, str(OPS))
spec = importlib.util.spec_from_file_location("reviewed_followup_test", OPS / "reviewed_followup.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
SHA = "a" * 64
RECEIPT = "11111111-2222-3333-4444-555555555555"


def test_fixed_syllabus_registry_and_no_write_inputs():
    name, args = helper.inputs("syllabus", {"actor": "test.admin", "batch": "chair-cells-089"})
    assert name == "export_wcu_syllabus_content"
    assert args == ["--actor", "test.admin", "--batch", "chair-cells-089"]
    name, args = helper.inputs("syllabus", {"actor": "test.admin", "batch": "chair-cells-091"})
    assert name == "export_wcu_syllabus_content"
    assert args == ["--actor", "test.admin", "--batch", "chair-cells-091"]
    for change in ({"batch": "chair-cells-092"}, {"apply": "true"}, {"actor": "x\n::warning::y"}):
        with pytest.raises(ValueError):
            helper.inputs("syllabus", {"actor": "admin", "batch": "chair-cells-001", **change})


def test_onomastics_dry_apply_and_receipt_undo_exact_cli():
    assert helper.inputs("onomastics", {"actor": "admin"}) == (
        "repair_onomastics_roster",
        ["--org", "qku", "--actor", "admin"],
    )
    for apply in (True, "true"):
        _, args = helper.inputs(
            "onomastics", {"actor": "admin", "baseline": SHA, "undo": RECEIPT, "apply": apply, "confirm": "APPLY"}
        )
        assert args == ["--org", "qku", "--actor", "admin", "--baseline", SHA, "--undo", RECEIPT, "--apply"]
    for change in (
        {"apply": True},
        {"apply": True, "confirm": "APPLY"},
        {"baseline": SHA + "\n"},
        {"undo": "--apply"},
        {"teacher": "9526"},
        {"apply": 0},
        {"apply": 0.0},
        {"confirm": "APPLY"},
    ):
        with pytest.raises(ValueError):
            helper.inputs("onomastics", {"actor": "admin", **change})


def test_deployed_head_must_equal_dispatch_checkout_before_operation():
    with mock.patch.object(helper, "command", return_value=json.dumps({"sha": "b" * 40})) as command:
        helper.verify_head("b" * 40)
        assert command.call_args.args[0][-2:] == ["cat", "/app/build-info.json"]
        with pytest.raises(ValueError, match="deployed_head_changed"):
            helper.verify_head("c" * 40)
    with mock.patch.object(helper, "command") as command:
        with pytest.raises(ValueError):
            helper.verify_head("unknown")
        command.assert_not_called()


def test_no_raw_stdout_stderr_on_transport_error_or_timeout():
    for result in (subprocess.CompletedProcess([], 1, "PRIVATE", "CONTACT"), subprocess.TimeoutExpired([], 1)):
        with mock.patch.object(
            helper.subprocess,
            "run",
            **({"side_effect": result} if isinstance(result, Exception) else {"return_value": result}),
        ):
            with pytest.raises(ValueError) as caught:
                helper.command(["docker", "exec", "fixed"])
            assert "PRIVATE" not in str(caught.value) and "CONTACT" not in str(caught.value)


def line(status="dry_run", flag="1", links="10", receipt="none", mode="dry_run"):
    return (
        f"onomastics_roster: mode={mode} baseline={SHA} links={links} "
        f"owner_seminar_access_narrowed={flag} receipt={receipt} status={status}"
    )


def test_safe_summary_requires_mode_dependency_and_no_arbitrary_output():
    assert helper.summary(line(), []) == line()
    assert helper.summary(line(status="applied", mode="apply", receipt=RECEIPT), ["--apply"])
    assert helper.summary(line(flag="0", receipt=RECEIPT), ["--undo", RECEIPT])
    for raw, args in (
        (line() + "\nPRIVATE", []),
        (line(), ["--apply"]),
        (line(flag="0"), []),
        (line(status="applied", mode="apply"), ["--undo", RECEIPT, "--apply"]),
        (line(status="applied", mode="apply"), ["--apply"]),
        (line(status="applied", receipt=RECEIPT), []),
        (line(status="already_present", receipt=RECEIPT), []),
        (line(), ["--baseline", "b" * 64]),
    ):
        with pytest.raises(ValueError):
            helper.summary(raw, args)


def test_main_masks_actor_and_drift_does_not_execute_or_print_inputs(tmp_path, capsys):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"actor": "private.operator"}}))
    with (
        mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_SHA": "a" * 40}),
        mock.patch.object(helper, "verify_head", side_effect=ValueError("PRIVATE")),
        mock.patch.object(helper, "command") as command,
    ):
        assert helper.main("onomastics") == 2
        command.assert_not_called()
    captured = capsys.readouterr()
    assert captured.out == "::add-mask::private.operator\n"
    assert "PRIVATE" not in captured.err and "inspect_receipt_before_retry" in captured.err


def test_encrypted_only_artifact_manifest_and_fresh_directory(tmp_path):
    env = {
        "GITHUB_RUN_ID": "42",
        "GITHUB_RUN_ATTEMPT": "2",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_SHA": "a" * 40,
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }
    envelope = {
        "format": "wcu-workload-envelope/1",
        "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
        "key_sha256": helper.envelope_digest.__globals__["KEY_SHA"],
        "nonce": base64.b64encode(b"x" * 12).decode(),
        "wrapped_key": base64.b64encode(b"x" * 384).decode(),
        "ciphertext": base64.b64encode(b"x" * 16).decode(),
    }
    calls = []

    def command(args):
        calls.append(args)
        if args[:2] == ["docker", "cp"] and args[2].endswith("snapshot.enc.json"):
            Path(args[3]).write_text(json.dumps(envelope))
        return ""

    with mock.patch.object(helper, "command", side_effect=command):
        helper.syllabus(["--actor", "admin", "--batch", "chair-cells-001"], env)
        folder = tmp_path / "syllabus-content-42-2"
        assert {p.name for p in folder.iterdir()} == {"snapshot.enc.json", "capture-manifest.json"}
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in folder.iterdir())
        manifest = json.loads((folder / "capture-manifest.json").read_bytes())
        assert manifest["head_sha"] == env["GITHUB_SHA"] and manifest["eligible_for_apply"] is False
        assert manifest["batch"] == "chair-cells-001"
        assert manifest["encrypted_sha256"] == helper.sha((folder / "snapshot.enc.json").read_bytes())
        assert calls[-1][-4:] == ["rm", "-rf", "--", "/tmp/wcu-syllabus-content-42-2"]
        with pytest.raises(FileExistsError):
            helper.syllabus(["--actor", "admin", "--batch", "chair-cells-001"], env)


def test_standalone_workflow_shapes_and_existing_collectors_unchanged():
    for file, kind, expected in (
        ("syllabus-content-export.yml", "syllabus", {"actor", "batch"}),
        ("reviewed-onomastics-roster.yml", "onomastics", {"actor", "baseline", "undo", "apply", "confirm"}),
    ):
        value = yaml.safe_load((ROOT / ".github/workflows" / file).read_text())
        assert set(value[True]["workflow_dispatch"]["inputs"]) == expected
        assert value["concurrency"] == {"group": "production-deploy", "cancel-in-progress": False}
        job = value["jobs"]["reviewed"]
        assert job["environment"] == "production" and job["timeout-minutes"] == 15
        runs = [step["run"] for step in job["steps"] if "run" in step]
        assert "python3 scripts/ops/reviewed_followup.py " + kind in runs
        assert not any("${{ inputs." in run or "prod-data-ops" in run for run in runs)
        if kind == "syllabus":
            upload = next(step for step in job["steps"] if "upload-artifact@" in step.get("uses", ""))
            assert "*.json" not in upload["with"]["path"] and upload["with"]["retention-days"] == 1
