"""Private payloads use default APPUID stdin transport, never docker cp or argv."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import private_container_source as transport  # noqa: E402

REMOTE = "/tmp/wcu-blank-draft-syllabus-1-1/source.json"
PAYLOAD = b'{"private_synthetic_sentinel":"NEVER_LOG_ME"}'
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def source(tmp_path):
    path = tmp_path / "source.json"
    path.write_bytes(PAYLOAD)
    path.chmod(0o600)
    return path


def test_only_stdin_carries_payload_and_receipt_proves_app_uid(tmp_path):
    path = source(tmp_path)
    receipt = dict(uid=1000, mode=0o600, size=len(PAYLOAD), sha256=SHA)
    with patch.object(
        transport.subprocess,
        "run",
        return_value=SimpleNamespace(returncode=0, stdout=json.dumps(receipt).encode(), stderr=b""),
    ) as run:
        assert transport.write_private_source(path, REMOTE, SHA, container="app-fixture") == receipt
    argv = run.call_args.args[0]
    assert argv[:6] == ["docker", "exec", "-i", "app-fixture", "python", "-c"]
    assert "--user" not in argv and "cp" not in argv
    assert "NEVER_LOG_ME" not in " ".join(argv)
    assert run.call_args.kwargs["input"] == PAYLOAD
    assert "O_EXCL" in transport.WRITER and "O_NOFOLLOW" in transport.WRITER


@pytest.mark.parametrize("change", ["symlink", "public_mode", "digest", "empty", "oversized"])
def test_invalid_private_local_source_never_contacts_docker(tmp_path, change):
    path = source(tmp_path)
    expected = SHA
    if change == "symlink":
        alias = tmp_path / "alias.json"
        alias.symlink_to(path)
        path = alias
    elif change == "public_mode":
        path.chmod(0o644)
    elif change == "digest":
        expected = "a" * 64
    elif change == "empty":
        path.write_bytes(b"")
    else:
        with path.open("wb") as stream:
            stream.truncate(transport.MAX_BYTES + 1)
    with patch.object(transport.subprocess, "run") as run, pytest.raises(ValueError):
        transport.write_private_source(path, REMOTE, expected, container="app-fixture")
    run.assert_not_called()


@pytest.mark.parametrize(
    "remote,container", [("/tmp/else/source.json", "app"), (REMOTE, "--user=root"), (REMOTE + ";id", "app")]
)
def test_arbitrary_target_or_injected_container_is_rejected(tmp_path, remote, container):
    with patch.object(transport.subprocess, "run") as run, pytest.raises(ValueError):
        transport.write_private_source(source(tmp_path), remote, SHA, container=container)
    run.assert_not_called()


@pytest.mark.parametrize(
    "changed",
    [
        {"uid": 0},
        {"uid": True},
        {"mode": 0o644},
        {"mode": 384.0},
        {"sha256": "a" * 64},
        {"size": 1},
        {"raw_body": "NEVER_LOG_ME"},
    ],
)
def test_invalid_remote_receipt_is_refused_without_disclosing_source(tmp_path, changed):
    receipt = {**dict(uid=1000, mode=0o600, size=len(PAYLOAD), sha256=SHA), **changed}
    result = SimpleNamespace(returncode=0, stdout=json.dumps(receipt).encode(), stderr=b"")
    with patch.object(transport.subprocess, "run", return_value=result), pytest.raises(ValueError) as caught:
        transport.write_private_source(source(tmp_path), REMOTE, SHA, container="app-fixture")
    assert "NEVER_LOG_ME" not in str(caught.value)


@pytest.mark.parametrize(
    "failure", [FileNotFoundError("secret"), subprocess.TimeoutExpired("docker", 1), OSError("secret")]
)
def test_transport_errors_are_closed_without_payload_or_stderr(tmp_path, failure):
    with patch.object(transport.subprocess, "run", side_effect=failure), pytest.raises(ValueError) as caught:
        transport.write_private_source(source(tmp_path), REMOTE, SHA, container="app-fixture")
    assert "secret" not in str(caught.value) and "NEVER_LOG_ME" not in str(caught.value)


HOSTS = [
    ("blank_draft_syllabus_restore", "blank-draft-syllabus", "recover_blank_draft_syllabi"),
    ("reviewed_half_pair_hours", "half-pair-hours", "repair_reviewed_half_pair_hours"),
    ("reviewed_farida_slot", "farida-slot", "repair_reviewed_farida_slot"),
]


def load(name):
    definition = importlib.util.spec_from_file_location(
        "private_source_host_" + name, ROOT / "scripts/ops" / (name + ".py")
    )
    host = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(host)
    return host


@pytest.mark.parametrize("name,prefix,management", HOSTS)
def test_copy_failure_cleans_both_locations_without_management(tmp_path, monkeypatch, name, prefix, management):
    host = load(name)
    commands = []
    monkeypatch.setattr(host, "verify_head", lambda head: None)
    monkeypatch.setattr(host, "command", lambda argv: commands.append(argv))

    def plaintext(folder, env):
        return source(folder)

    monkeypatch.setattr(host, "source", plaintext)
    monkeypatch.setattr(
        host, "write_private_source", lambda *a, **k: (_ for _ in ()).throw(ValueError("private_source_write_failed"))
    )
    with patch.object(host.subprocess, "run") as run:
        with pytest.raises(ValueError, match="private_source_write_failed"):
            host.execute(
                {"actor": "fixture.admin"},
                dict(GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="a" * 40, RUNNER_TEMP=str(tmp_path)),
            )
        run.assert_not_called()
    assert not (tmp_path / (prefix + "-1-1")).exists()
    assert commands[-1][-2:] == ["--", "/tmp/wcu-" + prefix + "-1-1"]
    assert not any(management in argv or "cp" in argv for argv in commands)
