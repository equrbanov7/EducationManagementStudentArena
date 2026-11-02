"""Offline workflow contract: no selectors, injected commands or unconfirmed writes."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
SPEC = importlib.util.spec_from_file_location("jale_merge_host_contract", ROOT / "scripts/ops/reviewed_jale_merge.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
ENV = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "b" * 40}


@pytest.mark.parametrize(
    "value",
    [
        {"actor": "other"},
        {"command": "shell"},
        {"tenant": "other"},
        {"apply": 1},
        {"apply": "FALSE"},
        {"baseline": "x"},
        {"apply": True},
        {"confirm": "APPLY"},
    ],
)
def test_refuses_unbounded_or_unconfirmed_input(monkeypatch, value):
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    with pytest.raises(ValueError):
        host.execute(value, ENV)


@pytest.mark.parametrize("apply", [False, True])
def test_fixed_route_and_opaque_artifact(monkeypatch, tmp_path, apply):
    import json

    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(host, "verify_head", lambda value: calls.append(["verify", value]))

    def run(args, **kwargs):
        calls.append(args)
        data = {"canonical": 7730, "baseline_sha256": "a" * 64, "holds": [], "eligible": True}
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(data) if "cat" in args else "saved")

    monkeypatch.setattr(host.subprocess, "run", run)
    host.execute({"apply": apply, "baseline": "a" * 64, "confirm": "APPLY" if apply else ""}, ENV)
    assert calls[0] == ["verify", ENV["GITHUB_SHA"]]
    command = calls[1]
    assert "reviewed_jale_merge" in command
    assert ("--apply" in command) == apply
    assert ("--i-know-this-is-production" in command) == apply
    artifact = tmp_path / "jale-merge-report.json"
    assert artifact.exists()
    assert artifact.stat().st_mode & 0o777 == 0o600
