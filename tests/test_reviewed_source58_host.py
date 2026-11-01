"""No network/Docker: fixed release, HEAD-first, boolean semantics and safe finite output."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
SPEC = importlib.util.spec_from_file_location("source58_host", ROOT / "scripts/ops/reviewed_source58.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
SHA = "a" * 64
BASE = dict(
    baseline=SHA,
    source_cells="58",
    target_enrollments="44",
    source_raw_hours="116",
    missing_lessons="9",
    missing_marks="58",
)
BATCH = "source58-20261101-180000-abcdef01"


def raw(fields, apply=False):
    return (
        "source58: mode="
        + ("apply" if apply else "dry_run")
        + " "
        + " ".join(f"{k}={v}" for k, v in sorted(fields.items()))
        + "\n"
    )


@pytest.mark.parametrize("apply,expected", [(False, False), (True, True), ("false", False), ("true", True)])
def test_github_real_boolean_and_event_strings(apply, expected):
    _, argv, result, _ = host.inputs(
        dict(actor="operator", apply=apply, baseline=SHA, confirm="APPLY" if expected else "")
    )
    assert result is expected and ("--apply" in argv) is expected


@pytest.mark.parametrize(
    "change",
    [
        dict(command="shell"),
        dict(targets=[]),
        dict(source_sha256=SHA),
        dict(tag="other"),
        dict(apply=1),
        dict(apply="FALSE"),
        dict(apply=True),
        dict(confirm="APPLY"),
        dict(undo=BATCH),
        dict(receipt_sha256=SHA),
        dict(undo="source58-bad", receipt_sha256=SHA),
        dict(actor="--help"),
    ],
)
def test_inputs_cannot_widen_scope_or_make_false_apply(change):
    with pytest.raises(ValueError):
        host.inputs(dict(actor="operator", **change) if "actor" not in change else change)


def test_exact_apply_and_dry_counter_summaries_preserve_signed_reconciliation():
    dry = dict(BASE, source_effect="111", cache_reconciliation="-99")
    assert host.summary(raw(dry), apply=False, undo=False, baseline=SHA) == dry
    applied = dict(BASE, batch=BATCH, receipt_sha256="b" * 64, created_marks="58", created_lessons="9")
    assert host.summary(raw(applied, True), apply=True, undo=False, baseline=SHA) == applied
    repeated = dict(
        BASE, missing_marks="0", missing_lessons="0", already_done="1", created_marks="0", created_lessons="0"
    )
    assert host.summary(raw(repeated), apply=False, undo=False) == repeated


@pytest.mark.parametrize(
    "change",
    [
        dict(source_cells="57"),
        dict(missing_marks="57"),
        dict(source_effect="117"),
        dict(cache_reconciliation="PRIVATE"),
        dict(unknown_intent="0"),
    ],
)
def test_partial_or_unknown_summary_never_reaches_logs(change):
    with pytest.raises(ValueError):
        host.summary(
            raw({**BASE, "source_effect": "116", "cache_reconciliation": "0", **change}), apply=False, undo=False
        )


def test_unknown_raw_error_and_extra_lines_are_redacted():
    assert (
        host.safe_failure("CommandError: reviewed_source58_unlocatable_history_requires_review\n")
        == "reviewed_source58_unlocatable_history_requires_review"
    )
    assert host.safe_failure("CommandError: reviewed_source58_PRIVATE_PERSON\n") == "source58_command_refused"
    assert host.safe_failure("Traceback PRIVATE_SOURCE_BODY") == "source58_command_refused"
    with pytest.raises(ValueError):
        host.summary(
            raw(dict(BASE, source_effect="116", cache_reconciliation="0")) + "PRIVATE_BODY\n", apply=False, undo=False
        )


def test_undo_requires_original_full_receipt_sha_and_exact_counts():
    _, args, apply, undo = host.inputs(dict(actor="operator", undo=BATCH, receipt_sha256=SHA))
    assert not apply and undo and args[-2:] == ["--receipt-sha256", SHA]
    value = dict(baseline=SHA, deleted_marks="58", deleted_lessons="9", already_undone="0")
    assert host.summary(raw(value), apply=False, undo=True) == value
    value.update(deleted_marks="0", deleted_lessons="0", already_undone="1")
    assert host.summary(raw(value), apply=False, undo=True) == value


def test_deployed_head_is_verified_before_source_download_or_docker_write(tmp_path):
    env = dict(GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="b" * 40, RUNNER_TEMP=str(tmp_path))
    with (
        patch.object(host, "verify_head", side_effect=ValueError("wrong_head")),
        patch.object(host, "source") as source,
        patch.object(host, "command") as command,
    ):
        with pytest.raises(ValueError, match="wrong_head"):
            host.execute(dict(actor="operator"), env)
    source.assert_not_called()
    command.assert_not_called()


def test_fixed_default_dry_command_uid_transport_and_cleanup(tmp_path, capsys):
    env = dict(GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="b" * 40, RUNNER_TEMP=str(tmp_path))

    def prepare(folder, env):
        target = folder / "source.json"
        target.write_bytes(b"PRIVATE_SOURCE_BYTES")
        return target

    response = SimpleNamespace(
        returncode=0, stdout=raw(dict(BASE, source_effect="116", cache_reconciliation="0")), stderr=""
    )
    with (
        patch.object(host, "verify_head"),
        patch.object(host, "source", side_effect=prepare),
        patch.object(host, "write_private_source") as transport,
        patch.object(host, "command") as command,
        patch.object(host.subprocess, "run", return_value=response) as run,
    ):
        result = host.execute(dict(actor="operator", apply="false"), env)
    argv = run.call_args.args[0]
    assert argv[:6] == ["docker", "exec", host.CONTAINER, "python", "manage.py", "repair_reviewed_source58"]
    assert "--apply" not in argv and argv[-1] == host.SOURCE_SHA
    assert transport.call_args.args[1] == "/tmp/wcu-source58-qb-1-1/source.json"
    assert command.call_args.args[0][-2:] == ["--", "/tmp/wcu-source58-qb-1-1"]
    assert result["source_cells"] == "58" and not (tmp_path / "source58-qb-1-1").exists()
    assert "PRIVATE_SOURCE_BYTES" not in capsys.readouterr().out


def test_cipher_and_plaintext_pins_both_required(tmp_path):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    cipher = folder / "cipher.enc"
    cipher.write_bytes(b"fixed cipher")
    plaintext = b'{"synthetic":"PRIVATE_BODY"}'

    def decrypt(argv, **kwargs):
        Path(argv[argv.index("-out") + 1]).write_bytes(plaintext)
        return SimpleNamespace(returncode=0)

    with (
        patch.object(host, "download", return_value=cipher) as download,
        patch.object(host, "CIPHER_SHA", hashlib.sha256(cipher.read_bytes()).hexdigest()),
        patch.object(host, "SOURCE_SHA", hashlib.sha256(plaintext).hexdigest()),
        patch.object(host.subprocess, "run", side_effect=decrypt),
    ):
        assert host.source(folder, dict(GH_TOKEN="not_logged", STAFF_PLAN_KEY="not_logged")).stat().st_mode & 0o077 == 0
    assert download.call_args.kwargs["tag"] == host.TAG and download.call_args.kwargs["asset"] == host.ASSET
    with (
        patch.object(host, "download", return_value=cipher),
        patch.object(host.subprocess, "run") as run,
        pytest.raises(ValueError),
    ):
        host.source(folder, dict(GH_TOKEN="not_logged", STAFF_PLAN_KEY="not_logged"))
    run.assert_not_called()


def test_source58_private_transport_path_is_closed_on_host_and_container():
    import private_container_source as transfer

    remote = "/tmp/wcu-source58-qb-123-1/source.json"
    assert re.fullmatch(transfer.PATH_PATTERN, remote)
    assert "source58-qb" in transfer.WRITER
    assert not re.fullmatch(transfer.PATH_PATTERN, "/tmp/wcu-source58-qb-other/source.json")


def test_actual_nonroot_private_writer_creates_0600_source58_file():
    import private_container_source as transfer

    if os.geteuid() == 0:
        pytest.skip("This actual-UID contract requires a non-root test process")
    folder = Path("/tmp") / f"wcu-source58-qb-{os.getpid()}-{uuid.uuid4().int}"
    folder.mkdir(mode=0o700)
    payload = b'{"synthetic":"PRIVATE_STDIN_BODY"}'
    sha = hashlib.sha256(payload).hexdigest()
    target = folder / "source.json"
    try:
        result = subprocess.run(
            [sys.executable, "-c", transfer.WRITER, str(target), sha, str(len(payload)), str(transfer.MAX_BYTES)],
            input=payload,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == dict(uid=os.geteuid(), size=len(payload), mode=0o600, sha256=sha)
        assert target.read_bytes() == payload and target.stat().st_mode & 0o777 == 0o600
        assert b"PRIVATE_STDIN_BODY" not in result.stdout + result.stderr
    finally:
        shutil.rmtree(folder)


def test_workflow_defaults_dry_and_preserves_production_mutex():
    doc = yaml.safe_load((ROOT / ".github/workflows/reviewed-source58-qb.yml").read_text())
    event = doc.get("on", doc.get(True))
    assert event["workflow_dispatch"]["inputs"]["apply"]["default"] is False
    assert set(event["workflow_dispatch"]["inputs"]) == {
        "actor",
        "baseline",
        "undo",
        "receipt_sha256",
        "apply",
        "confirm",
    }
    assert doc["concurrency"] == dict(group="production-deploy", **{"cancel-in-progress": False})
    assert doc["permissions"] == {"contents": "read"}
    job = doc["jobs"]["reviewed"]
    assert job["environment"] == "production" and job["runs-on"] == ["self-hosted"]
    assert job["steps"][0]["with"]["persist-credentials"] is False
    assert job["steps"][-1]["if"] == "always()"
