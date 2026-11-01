"""Independent encrypted diagnostic schema cannot be mistaken for full recovery authority."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/ops/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload():
    scope = dict(
        rows=[],
        row_count=0,
        total_raw_bytes=0,
        strict_total_budget=8 * 1024 * 1024,
        strict_per_row_budget=1024 * 1024,
        raw_json_fetched=False,
        history_cleared_for_apply=False,
    )
    return dict(
        format="wcu-recovery-audit-diagnostic/1",
        organization_id="526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
        captured_at="2026-11-01T10:00:00+00:00",
        read_only=True,
        eligible_for_apply=False,
        absence_claim=False,
        raw_body_included=False,
        data={"four": scope, "source28": copy.deepcopy(scope)},
    )


@pytest.mark.parametrize("key", ["eligible_for_apply", "absence_claim", "raw_body_included"])
def test_diagnostic_cannot_claim_recovery_authority(key):
    value = payload()
    value[key] = True
    with pytest.raises(ValueError):
        load("recovery_audit_diagnostic_scope").validate(value)


def test_distinct_format_no_raw_json_or_extra_scope():
    scope = load("recovery_audit_diagnostic_scope")
    scope.validate(payload())
    for value in ({**payload(), "format": "wcu-four-cell-history/1"}, {**payload(), "raw_json": "secret"}):
        with pytest.raises(ValueError):
            scope.validate(value)
    value = payload()
    value["data"]["four"]["history_cleared_for_apply"] = True
    with pytest.raises(ValueError):
        scope.validate(value)


@pytest.mark.parametrize("version", [1, 2])
def test_actual_crypto_roundtrip_is_private_and_normal_syllabus_decoder_refuses(tmp_path, monkeypatch, version):
    from apps.workload.services import scoped_snapshot

    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    import hashlib

    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(scoped_snapshot, "KEY_FINGERPRINT", hashlib.sha256(der).hexdigest())
    value = payload()
    if version == 2:
        value["format"] = "wcu-recovery-audit-diagnostic/2"
        for section in value["data"].values():
            section["receipt_semantic_previews"] = []
    encoded = json.dumps(scoped_snapshot.encrypt(value, public)).encode()
    secret = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    decoder = load("decrypt_recovery_audit_diagnostic")
    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    import hashlib

    monkeypatch.setattr(decoder, "KEY_FINGERPRINT", hashlib.sha256(der).hexdigest())
    decoded = decoder.decrypt_snapshot(encoded, secret)
    assert decoded == value
    target = decoder.write_new_snapshot(decoded, tmp_path)
    assert target.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError):
        load("syllabus_content_scope").validate(decoded)


def test_workflow_has_actor_only_selector_and_encrypted_only_output():
    host = load("recovery_audit_diagnostic_export")
    for values in ({"actor": "superadmin", "offering": "anything"}, {"actor": "superadmin", "apply": True}):
        with pytest.raises(ValueError):
            host.inputs(values)
    text = (ROOT / ".github/workflows/recovery-audit-diagnostic.yml").read_text()
    assert "group: production-deploy" in text
    assert "cancel-in-progress: false" in text
    assert "/snapshot.enc.json" in text and "/capture-manifest.json" in text
    assert "recovery_audit_diagnostic_export.py" in text
