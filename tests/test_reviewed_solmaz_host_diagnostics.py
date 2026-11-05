"""Closed host phase codes; production pins/confirmation/redaction stay enforced."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

OPS = Path(__file__).resolve().parents[1] / "scripts/ops"
sys.path.insert(0, str(OPS))
ACTOR = "fixture.private.admin"
SECRET = "PRIVATE_EXCEPTION_KEY_TOKEN_AND_BODY"


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    yield


@pytest.fixture
def wired(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("solmaz_diagnostic_host", OPS / "reviewed_solmaz_catalog.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    cipher, plain = b"sealed fixture", b'{"fixture":"private source"}'
    monkeypatch.setattr(host, "CIPHER_SHA", hashlib.sha256(cipher).hexdigest())
    monkeypatch.setattr(host, "SOURCE_SHA", hashlib.sha256(plain).hexdigest())
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"actor": ACTOR, "apply": False}}))
    env = {
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "RUNNER_TEMP": str(tmp_path),
        "STAFF_PLAN_KEY": SECRET,
        "GH_TOKEN": SECRET,
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(host.os, "umask", lambda mask: None)
    calls = []

    def verify_head(head):
        calls.append("head")
        assert head == "a" * 40

    def download(**kwargs):
        calls.append("download")
        assert (kwargs["repo"], kwargs["tag"], kwargs["asset"]) == (host.REPO, host.TAG, host.ASSET)
        assert kwargs["sha256"] == host.CIPHER_SHA and kwargs["max_bytes"] == host.MAX_SOURCE
        kwargs["target"].write_bytes(cipher)
        return kwargs["target"]

    summary = "reviewed_solmaz_catalog: " + " ".join(
        f"{name}={value}"
        for name, value in dict(
            status="dry_run",
            baseline="b" * 64,
            after_baseline="b" * 64,
            receipt="none",
            applied=0,
            new_source_versions=0,
            new_shares=0,
            teacher_hours=180,
            source_sha256=host.SOURCE_SHA,
            protected_models=13,
            protected_rows=512,
        ).items()
    )

    def run(argv, **kwargs):
        if argv[0] == "openssl":
            calls.append("decrypt")
            assert "-aes-256-cbc" in argv and argv[argv.index("-iter") + 1] == "200000"
            assert argv[-2:] == ["-pass", "env:STAFF_PLAN_KEY"]
            assert SECRET not in " ".join(argv)
            Path(argv[argv.index("-out") + 1]).write_bytes(plain)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        calls.append("native")
        assert argv[:6] == ["docker", "exec", host.CONTAINER, "python", "manage.py", "repair_reviewed_solmaz_catalog"]
        assert "--apply" not in argv and argv[-1] == host.SOURCE_SHA
        return SimpleNamespace(returncode=0, stdout=summary, stderr="")

    def command(argv):
        calls.append("cleanup" if "rm" in argv else "mkdir")

    def transfer(*args, **kwargs):
        calls.append("transfer")
        assert args[0].read_bytes() == plain and args[2] == host.SOURCE_SHA

    monkeypatch.setattr(host, "verify_head", verify_head)
    monkeypatch.setattr(host, "download", download)
    monkeypatch.setattr(host, "command", command)
    monkeypatch.setattr(host, "write_private_source", transfer)
    monkeypatch.setattr(host.subprocess, "run", run)
    return host, calls, tmp_path, summary


def fail(*args, **kwargs):
    raise RuntimeError(SECRET + " " + ACTOR)


def assert_failure(host, tmp_path, capsys, code, *, mask=True):
    assert host.main() == 2
    captured = capsys.readouterr()
    assert captured.err == code + "\n"
    # Existing GitHub mask registration is the only actor-bearing control line.
    assert captured.out == ("::add-mask::" + ACTOR + "\n" if mask else "")
    assert SECRET not in captured.err + captured.out and ACTOR not in captured.err
    assert not (tmp_path / "reviewed-solmaz-123-1").exists()


@pytest.mark.parametrize(
    "attribute,code",
    [
        ("verify_head", "solmaz_host_deployed_head_refused"),
        ("download", "solmaz_host_download_refused"),
        ("write_private_source", "solmaz_host_transfer_refused"),
    ],
)
def test_host_boundary_reports_only_its_phase(wired, monkeypatch, capsys, attribute, code):
    host, calls, tmp_path, _ = wired
    monkeypatch.setattr(host, attribute, fail)
    assert_failure(host, tmp_path, capsys, code)
    assert "native" not in calls


def test_missing_key_is_distinct_and_never_decrypts(wired, monkeypatch, capsys):
    host, calls, tmp_path, _ = wired
    monkeypatch.delenv("STAFF_PLAN_KEY")
    assert_failure(host, tmp_path, capsys, "solmaz_host_key_missing")
    assert "decrypt" not in calls and "native" not in calls


@pytest.mark.parametrize("kind", ["timeout", "exit", "plaintext_hash"])
def test_decryption_failure_never_exposes_openssl_output(wired, monkeypatch, capsys, kind):
    host, calls, tmp_path, _ = wired
    real_run = host.subprocess.run

    def run(argv, **kwargs):
        assert argv[0] == "openssl"
        if kind == "timeout":
            raise subprocess.TimeoutExpired([SECRET, ACTOR], 30, output=SECRET, stderr=SECRET)
        if kind == "exit":
            return SimpleNamespace(returncode=1, stdout=SECRET, stderr=SECRET)
        result = real_run(argv, **kwargs)
        Path(argv[argv.index("-out") + 1]).write_text(SECRET)
        return result

    monkeypatch.setattr(host.subprocess, "run", run)
    assert_failure(host, tmp_path, capsys, "solmaz_host_decrypt_refused")
    assert "native" not in calls and "transfer" not in calls


def test_cipher_pin_remains_enforced(wired, monkeypatch, capsys):
    host, calls, tmp_path, _ = wired
    monkeypatch.setattr(host, "CIPHER_SHA", "0" * 64)
    assert_failure(host, tmp_path, capsys, "solmaz_host_download_refused")
    assert "decrypt" not in calls


@pytest.mark.parametrize(
    "kind,code",
    [
        ("exception", "solmaz_host_command_refused"),
        ("stderr", "solmaz_host_command_refused"),
        ("budget", "solmaz_host_command_refused"),
        ("unknown_native", "solmaz_command_refused"),
        ("known_native", "solmaz_current_evidence_unavailable"),
        ("summary", "solmaz_host_summary_refused"),
    ],
)
def test_native_and_summary_failures_remain_closed(wired, monkeypatch, capsys, kind, code):
    host, _, tmp_path, summary = wired
    real_run = host.subprocess.run

    def run(argv, **kwargs):
        if argv[0] == "openssl":
            return real_run(argv, **kwargs)
        if kind == "exception":
            raise subprocess.TimeoutExpired([SECRET, ACTOR], 540, output=SECRET, stderr=SECRET)
        if kind == "known_native":
            return SimpleNamespace(
                returncode=1, stdout=SECRET, stderr="CommandError: solmaz_current_evidence_unavailable\n"
            )
        return SimpleNamespace(
            returncode=int(kind == "unknown_native"),
            stdout=SECRET * 70000 if kind == "budget" else SECRET if kind == "summary" else summary,
            stderr=SECRET if kind in {"stderr", "unknown_native"} else "",
        )

    monkeypatch.setattr(host.subprocess, "run", run)
    assert_failure(host, tmp_path, capsys, code)


def test_success_still_requires_safe_summary_and_dry_default(wired, capsys):
    host, calls, tmp_path, summary = wired
    assert host.main() == 0
    assert calls == ["head", "download", "decrypt", "mkdir", "transfer", "native", "cleanup"]
    captured = capsys.readouterr()
    assert captured.err == "" and captured.out == "::add-mask::" + ACTOR + "\n" + summary + "\n"
    assert SECRET not in captured.out
    assert not (tmp_path / "reviewed-solmaz-123-1").exists()


@pytest.mark.parametrize(
    "inputs",
    [
        {"actor": ACTOR, "apply": True},
        {"actor": ACTOR, "apply": True, "baseline": "b" * 64, "confirm": "WRONG"},
        {"actor": ACTOR, "apply": False, "baseline": SECRET},
    ],
)
def test_apply_confirmation_and_baseline_guards_are_not_bypassed(wired, capsys, inputs):
    host, calls, tmp_path, _ = wired
    (tmp_path / "event.json").write_text(json.dumps({"inputs": inputs}))
    assert_failure(host, tmp_path, capsys, "solmaz_host_refused", mask=False)
    assert calls == []


def test_unknown_phase_or_native_exception_cannot_smuggle_text(wired, monkeypatch, capsys):
    host, _, _, _ = wired
    with pytest.raises(host.HostPhaseRefused, match="^solmaz_host_refused$"):
        with host.phase(SECRET):
            fail()
    monkeypatch.setattr(host, "execute", lambda *a: (_ for _ in ()).throw(host.Refused(SECRET)))
    assert host.main() == 2
    assert capsys.readouterr().err == "solmaz_command_refused\n"


@pytest.mark.parametrize("primary_failure", [False, True])
def test_cleanup_failure_is_redacted_without_replacing_primary_phase(wired, monkeypatch, capsys, primary_failure):
    host, _, tmp_path, summary = wired
    remove = host.shutil.rmtree

    def cleanup(folder):
        remove(folder)
        fail()

    monkeypatch.setattr(host.shutil, "rmtree", cleanup)
    if primary_failure:
        monkeypatch.setattr(host, "download", fail)
        assert_failure(host, tmp_path, capsys, "solmaz_host_download_refused")
    else:
        assert host.main() == 2
        captured = capsys.readouterr()
        assert captured.err == "solmaz_host_transfer_refused\n"
        assert captured.out == "::add-mask::" + ACTOR + "\n" + summary + "\n"
        assert SECRET not in captured.out + captured.err
