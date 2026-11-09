"""Reject native-incompatible private plans before encryption or publication."""

import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def packager():
    path = Path(__file__).resolve().parents[1] / "scripts/ops/package_reaudit_operation.py"
    spec = importlib.util.spec_from_file_location("reaudit_package_limits_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unpacker():
    path = Path(__file__).resolve().parents[1] / "scripts/ops/reaudit_private_transport.py"
    spec = importlib.util.spec_from_file_location("reaudit_unpack_limits_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compressed_bundle(plan, operation="structure"):
    return {
        "format": "reaudit-operation-bundle/2",
        "operation": operation,
        "offering_ids": [],
        "plan_encoding": "gzip",
        "plan": base64.b64encode(gzip.compress(plan, mtime=0)).decode(),
        "plan_sha256": hashlib.sha256(plan).hexdigest(),
        "authority": "",
        "authority_sha256": hashlib.sha256(b"").hexdigest(),
    }


@pytest.mark.parametrize("operation,maximum", [("structure", 1024 * 1024), ("syllabi", 20_000_000)])
def test_oversized_native_plan_refused_before_any_subprocess(packager, tmp_path, monkeypatch, operation, maximum):
    tmp_path.chmod(0o700)
    plan = tmp_path / "plan.json"
    with plan.open("wb") as stream:
        stream.truncate(maximum + 1)
    plan.chmod(0o600)
    monkeypatch.setattr(packager.subprocess, "run", lambda *a, **kw: pytest.fail("Oversized plan reached encryption"))
    with pytest.raises(ValueError, match="private_bounded"):
        packager.package(
            operation=operation, plan_path=plan, key_path=tmp_path / "unused-key", output=tmp_path / "bundle.enc"
        )
    assert not (tmp_path / "bundle.enc").exists()


def test_empty_plan_cannot_be_published(packager, tmp_path):
    tmp_path.chmod(0o700)
    plan = tmp_path / "plan.json"
    plan.write_bytes(b"")
    plan.chmod(0o600)
    with pytest.raises(ValueError, match="nonempty_plan"):
        packager.package(
            operation="cells", plan_path=plan, key_path=tmp_path / "unused-key", output=tmp_path / "bundle.enc"
        )


def test_small_plan_encrypts_with_verified_roundtrip_and_private_output(packager, tmp_path):
    tmp_path.chmod(0o700)
    plan, key, output = (tmp_path / name for name in ("plan.json", "synthetic-key", "bundle.enc"))
    plan.write_bytes(b'{"synthetic":true}')
    key.write_bytes(b"synthetic-test-only-key")
    for path in (plan, key):
        path.chmod(0o600)
    result = packager.package(operation="structure", plan_path=plan, key_path=key, output=output)
    assert result["cipher_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result["plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600
    assert plan.read_bytes() not in output.read_bytes()


def test_v2_unpacks_exact_plain_plan_and_refuses_compressed_oversize(tmp_path):
    path = tmp_path / "bundle.gz"
    raw = b'{"synthetic":true}'
    path.write_bytes(gzip.compress(json.dumps(compressed_bundle(raw)).encode()))
    assert unpacker().unpack(path, "structure")["plan"] == raw
    path.write_bytes(gzip.compress(json.dumps(compressed_bundle(b"x" * (1024 * 1024 + 1))).encode()))
    with pytest.raises(ValueError, match="native_source_budget"):
        unpacker().unpack(path, "structure")


def test_v2_plan_digest_checks_uncompressed_bytes(tmp_path):
    path = tmp_path / "bundle.gz"
    value = compressed_bundle(b"original")
    value["plan"] = base64.b64encode(gzip.compress(b"tampered")).decode()
    path.write_bytes(gzip.compress(json.dumps(value).encode()))
    with pytest.raises(ValueError, match="source_digest"):
        unpacker().unpack(path, "structure")
