"""Fixed one-slot transport, exact service JSON outcomes and protected-data invariants."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
RECEIPT = "11111111-1111-4111-8111-111111111111"


def load():
    spec = importlib.util.spec_from_file_location("farida_slot_host_test", ROOT / "scripts/ops/reviewed_farida_slot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def value(status="dry_run", undo=False):
    changed = status in {"parked", "undone"}
    result = dict(
        status=status,
        baseline="a" * 64,
        receipt=None if status == "dry_run" and not undo else RECEIPT,
        slots_changed=int(changed),
        slots_created=0,
        slots_deleted=0,
        lessons_changed=0,
        marks_changed=0,
        credits_changed=0,
        original_docx_slots_preserved=5,
    )
    if status == "dry_run":
        result["planned_slots"] = 1
    elif changed:
        result["after_baseline"] = "b" * 64
    return result


def raw(result):
    return "reviewed_farida_slot: " + json.dumps(result)


@pytest.mark.parametrize(
    "status,apply,undo",
    [
        ("dry_run", False, False),
        ("parked", True, False),
        ("already_parked", False, False),
        ("already_parked", True, False),
        ("dry_run", False, True),
        ("undone", True, True),
        ("already_undone", False, True),
        ("already_undone", True, True),
    ],
)
def test_service_actual_keys_statuses_and_counts(status, apply, undo):
    expected = value(status, undo)
    assert load().summary(raw(expected), apply=apply, undo=undo) == expected


@pytest.mark.parametrize(
    "key,changed",
    [
        ("slots_changed", 0),
        ("slots_created", 1),
        ("slots_deleted", 1),
        ("lessons_changed", 1),
        ("marks_changed", 1),
        ("credits_changed", 1),
        ("original_docx_slots_preserved", 4),
        ("slots_created", False),
        ("baseline", "invalid"),
        ("after_baseline", None),
        ("receipt", None),
    ],
)
def test_reject_changed_protected_data_or_original_docx_slots(key, changed):
    result = value("parked")
    result[key] = changed
    with pytest.raises(ValueError):
        load().summary(raw(result), apply=True, undo=False)


@pytest.mark.parametrize(
    "status,apply,undo",
    [
        ("parked", False, False),
        ("undone", False, True),
        ("parked", True, True),
        ("undone", True, False),
        ("dry_run", True, False),
        ("already_parked", False, True),
    ],
)
def test_mode_mismatch_is_rejected(status, apply, undo):
    with pytest.raises(ValueError):
        load().summary(raw(value(status, undo)), apply=apply, undo=undo)


def test_unexpected_missing_duplicate_and_multiline_summary_keys_are_rejected():
    host = load()
    dry = value()
    invalid = [
        raw(dry) + "\nextra",
        raw({**dry, "after_baseline": "b" * 64}),
        raw({**value("parked"), "planned_slots": 1}),
        raw({**dry, "planned_slots": True}),
        raw({k: v for k, v in dry.items() if k != "planned_slots"}),
        raw(dry)[:-1] + ',"marks_changed":0}',
        raw({**dry, "status": []}),
        "x" * 8193,
    ]
    for text in invalid:
        with pytest.raises(ValueError):
            host.summary(text, apply=False, undo=False)


def test_fixed_inputs_need_fresh_baseline_and_explicit_apply_confirmation():
    host = load()
    for extra in ("file", "sha256", "slot", "teacher", "organization", "source_tag", "command"):
        with pytest.raises(ValueError):
            host.inputs({"actor": "ops.admin", extra: "untrusted"})
    for changed in (
        {"apply": True},
        {"apply": True, "baseline": "a" * 64},
        {"apply": "yes"},
        {"confirm": "APPLY"},
        {"undo": "untrusted"},
        {"baseline": False},
    ):
        with pytest.raises(ValueError):
            host.inputs({"actor": "ops.admin", **changed})
    assert host.inputs({"actor": "ops.admin", "apply": True, "baseline": "a" * 64, "confirm": "APPLY"})[2] is True


def environment(tmp_path):
    return {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": str(tmp_path)}


def prepared_host(tmp_path, monkeypatch, result):
    host = load()
    commands, runs = [], []
    monkeypatch.setattr(host, "verify_head", lambda head: commands.append(["verify_head", head]))
    monkeypatch.setattr(host, "command", lambda argv: commands.append(argv))

    def source(folder, env):
        path = folder / "source.json"
        path.write_text("fixed test only")
        return path

    def execute(argv, **kwargs):
        runs.append(argv)
        return SimpleNamespace(returncode=0, stdout=raw(result), stderr="")

    monkeypatch.setattr(host, "source", source)
    monkeypatch.setattr(host.subprocess, "run", execute)
    return host, commands, runs


def test_execute_uses_exact_command_source_sha_and_cleans_private_files(tmp_path, monkeypatch):
    result = value("parked")
    host, commands, runs = prepared_host(tmp_path, monkeypatch, result)
    assert (
        host.execute(
            {"actor": "ops.admin", "baseline": "a" * 64, "apply": True, "confirm": "APPLY"}, environment(tmp_path)
        )
        == result
    )
    assert len(runs) == 1
    argv = runs[0]
    assert argv[:6] == ["docker", "exec", host.CONTAINER, "python", "manage.py", "repair_reviewed_farida_slot"]
    assert argv[argv.index("--sha256") + 1] == host.SOURCE_SHA
    assert argv[argv.index("--file") + 1] == "/tmp/wcu-farida-slot-7-2/source.json"
    assert commands[0] == ["verify_head", "a" * 40]
    assert commands[-1][-1] == "/tmp/wcu-farida-slot-7-2"
    assert not (tmp_path / "farida-slot-7-2").exists()


@pytest.mark.parametrize("failure", ["source", "baseline", "undo", "timeout"])
def test_failed_source_baseline_undo_or_timeout_cleans_private_files(tmp_path, monkeypatch, failure):
    host, commands, runs = prepared_host(tmp_path, monkeypatch, value())
    inputs = {"actor": "ops.admin"}
    if failure == "source":
        monkeypatch.setattr(host, "source", lambda *args: (_ for _ in ()).throw(ValueError("release_asset_missing")))
    elif failure == "baseline":
        inputs["baseline"] = "b" * 64
    elif failure == "undo":
        inputs["undo"] = "22222222-2222-4222-8222-222222222222"
        monkeypatch.setattr(
            host.subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout=raw(value(undo=True)), stderr=""),
        )
    else:
        monkeypatch.setattr(
            host.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("docker", 180))
        )
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        host.execute(inputs, environment(tmp_path))
    assert not (tmp_path / "farida-slot-7-2").exists()
    assert commands[-1][-1] == "/tmp/wcu-farida-slot-7-2"
    if failure == "source":
        assert not runs


def test_failure_guard_is_closed_and_never_echoes_arbitrary_stderr():
    host = load()
    assert (
        host.source_failure("reviewed_farida_slot_guard: farida_slot_fresh_baseline_required").guard
        == "farida_slot_fresh_baseline_required"
    )
    assert host.source_failure("reviewed_farida_slot_guard: secretpassword").guard is None
    assert (
        host.source_failure(
            "reviewed_farida_slot_guard: farida_slot_fresh_baseline_required\nreviewed_farida_slot_guard: farida_slot_source_sha_required"
        ).guard
        is None
    )


def test_workflow_and_source_pins_are_exact_and_business_service_is_reused():
    host = load()
    text = (ROOT / ".github/workflows/reviewed-farida-slot.yml").read_text()
    assert "group: production-deploy" in text and "cancel-in-progress: false" in text
    assert "persist-credentials: false" in text and "retention-days" not in text
    assert "github.token" in text and "STAFF_PLAN_KEY" in text and "reviewed_farida_slot.py" in text
    assert host.TAG == "reviewed-farida-inferred-slot-20261101"
    assert host.ASSET == "reviewed-farida-inferred-slot-source.json.enc"
    assert host.SOURCE_SHA == "037d18ad93ea111a34de0ca6699afddabc4a16f73b2d5a70743b226251cea397"
    assert host.CIPHER_SHA == "0ccf7065eb1d9479671ddb8c5009196f0e46b291435161c1b371aecffd3db48d"


@pytest.mark.parametrize("wrong_hash", [False, True])
def test_source_download_is_fixed_cipher_only_and_secret_stays_in_environment(tmp_path, monkeypatch, wrong_hash):
    import hashlib
    import stat

    host = load()
    downloads, calls = [], []
    plaintext = b'{"fixed":"test payload"}'
    monkeypatch.setattr(host, "SOURCE_SHA", "a" * 64 if wrong_hash else hashlib.sha256(plaintext).hexdigest())

    def download(**kwargs):
        downloads.append(kwargs)
        kwargs["target"].write_bytes(b"ciphertext")
        return kwargs["target"]

    def decrypt(argv, **kwargs):
        calls.append((argv, kwargs))
        Path(argv[argv.index("-out") + 1]).write_bytes(plaintext)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(host, "download", download)
    monkeypatch.setattr(host.subprocess, "run", decrypt)
    env = {"GH_TOKEN": "opaque-test-token", "STAFF_PLAN_KEY": "private-test-key"}
    if wrong_hash:
        with pytest.raises(ValueError, match="farida_slot_fixed_source_changed"):
            host.source(tmp_path, env)
    else:
        path = host.source(tmp_path, env)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert downloads[0]["repo"] == host.REPO and downloads[0]["tag"] == host.TAG
    assert downloads[0]["asset"] == host.ASSET and downloads[0]["sha256"] == host.CIPHER_SHA
    assert downloads[0]["max_bytes"] == 1024 * 1024
    argv, kwargs = calls[0]
    assert argv[argv.index("-pass") + 1] == "env:STAFF_PLAN_KEY"
    assert env["STAFF_PLAN_KEY"] not in argv and env["GH_TOKEN"] not in argv
    assert kwargs["env"] is env and kwargs["capture_output"] is True
