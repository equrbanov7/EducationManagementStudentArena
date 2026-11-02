"""Actual host -> shared validator -> executable embedded writer -> native command order."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

OPS = Path(__file__).resolve().parents[1] / "scripts/ops"
sys.path.insert(0, str(OPS))
import private_container_source as transport  # noqa: E402


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    yield


def host_module(name):
    spec = importlib.util.spec_from_file_location("transport_" + name, OPS / (name + ".py"))
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    return host


def native_summary(name):
    if name == "own_base_syllabus_bank":
        return dict(
            status="dry_run",
            baseline="a" * 64,
            receipt=None,
            cases=5,
            versions_created=0,
            shares_created=0,
            skip_approved=0,
            skip_existing=0,
            ready=5,
            protected_graph="b" * 64,
        )
    return dict(
        status="dry_run",
        baseline="a" * 64,
        receipt=None,
        cases=2,
        versions_created=0,
        versions_archived=0,
        source_hours=60,
        official_hours=45,
        graph="b" * 64,
    )


def wire_host(monkeypatch, tmp_path, name, namespace):
    host = host_module(name)
    payload = b'{"opaque_source_fixture":"private content never goes into argv"}'
    digest = hashlib.sha256(payload).hexdigest()
    run = str(60_000_000_000 + int(hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8], 16))
    remote = Path(f"/tmp/wcu-{namespace}-{run}-1")
    assert not remote.exists()
    writer_uid = os.geteuid() or 65534
    writer_gid = os.getegid() if os.geteuid() else 65534
    events = []
    real_run = subprocess.run

    def command(args):
        assert args[:3] == ["docker", "exec", host.CONTAINER]
        if args[3:6] == ["mkdir", "-m", "700"]:
            assert args[6] == str(remote)
            remote.mkdir(mode=0o700)
            if os.geteuid() == 0:
                os.chown(remote, writer_uid, writer_gid)
        elif args[3:6] == ["rm", "-rf", "--"]:
            assert args[6] == str(remote)
            shutil.rmtree(remote, ignore_errors=True)
        else:
            raise AssertionError("Unexpected transport command")

    def source(folder, env):
        path = folder / "source.json"
        path.write_bytes(payload)
        path.chmod(0o600)
        return path

    def demote():
        os.setgroups([])
        os.setgid(writer_gid)
        os.setuid(writer_uid)

    def run_command(args, **kwargs):
        if args[:3] == ["docker", "exec", "-i"]:
            assert args[3:6] == [host.CONTAINER, "python", "-c"]
            assert args[6] == transport.WRITER
            assert args[7:] == [str(remote / "source.json"), digest, str(len(payload)), str(transport.MAX_BYTES)]
            assert kwargs["input"] == payload
            options = {k: kwargs[k] for k in ("input", "capture_output", "timeout")}
            if os.geteuid() == 0:
                options["preexec_fn"] = demote
            result = real_run([sys.executable, "-c", args[6], *args[7:]], **options)
            events.append(("writer", result.returncode))
            if result.returncode == 0:
                receipt = json.loads(result.stdout)
                assert receipt == dict(uid=writer_uid, mode=0o600, size=len(payload), sha256=digest)
                assert payload not in str(args).encode()
            return result
        assert args[:5] == ["docker", "exec", host.CONTAINER, "python", "manage.py"]
        expected = "recover_own_base_syllabi" if name == "own_base_syllabus_bank" else "recover_reviewed_pervin_syllabi"
        assert args[5] == expected and "--apply" not in args
        assert events == [("writer", 0)]
        assert (remote / "source.json").read_bytes() == payload
        assert stat.S_IMODE((remote / "source.json").stat().st_mode) == 0o600
        events.append(("native", expected))
        return SimpleNamespace(returncode=0, stdout=json.dumps(native_summary(name)), stderr="")

    monkeypatch.setattr(host, "SOURCE_SHA", digest)
    monkeypatch.setattr(host, "source", source)
    monkeypatch.setattr(host, "verify_head", lambda head: head == "c" * 40)
    monkeypatch.setattr(host, "command", command)
    monkeypatch.setattr(subprocess, "run", run_command)
    env = dict(GITHUB_RUN_ID=run, GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="c" * 40, RUNNER_TEMP=str(tmp_path))
    return host, env, events, remote


@pytest.mark.parametrize(
    "name,namespace", [("own_base_syllabus_bank", "reviewed-ownbase"), ("reviewed_pervin_syllabi", "reviewed-pervin")]
)
def test_real_embedded_writer_completes_before_native(monkeypatch, tmp_path, name, namespace):
    host, env, events, remote = wire_host(monkeypatch, tmp_path, name, namespace)
    result = host.execute({"actor": "fixture-admin", "apply": False}, env)
    assert result["status"] == "dry_run"
    assert events[0] == ("writer", 0) and events[1][0] == "native"
    assert not remote.exists()


@pytest.mark.parametrize(
    "name,namespace", [("own_base_syllabus_bank", "reviewed-ownbase"), ("reviewed_pervin_syllabi", "reviewed-pervin")]
)
def test_embedded_writer_refusal_prevents_native_and_cleans(monkeypatch, tmp_path, name, namespace):
    host, env, events, remote = wire_host(monkeypatch, tmp_path, name, namespace)
    # Deliberately reproduce the missing embedded allowlist while outer validator remains correct.
    monkeypatch.setattr(transport, "WRITER", transport.WRITER.replace("|" + namespace, ""))
    with pytest.raises(ValueError, match="private_source_write_failed"):
        host.execute({"actor": "fixture-admin", "apply": False}, env)
    assert events == [("writer", 2)]
    assert not remote.exists()


@pytest.mark.parametrize("namespace", ["reviewed-ownbase", "reviewed-pervin"])
def test_only_exact_numeric_namespace_paths_allowed(namespace):
    assert re.fullmatch(transport.PATH_PATTERN, f"/tmp/wcu-{namespace}-123-1/source.json")
    for path in (
        f"/tmp/wcu-{namespace}-extra-123-1/source.json",
        f"/tmp/wcu-{namespace}-0-1/source.json",
        f"/tmp/wcu-{namespace}-123-0/source.json",
        f"/tmp/wcu-{namespace}-123-1/source.json/extra",
        f"/tmp/wcu-{namespace}-123-1/../source.json",
        f"/tmp/wcu-{namespace}-123-1/other.json",
        f"/tmp/wcu-{namespace}-123-1/source.json;id",
    ):
        assert re.fullmatch(transport.PATH_PATTERN, path) is None
