import binascii
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
spec = importlib.util.spec_from_file_location(
    "reviewed_targeted_host", ROOT / "scripts/ops/reviewed_targeted_credentials.py"
)
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)


def test_exact_batches_no_mass_or_force_input():
    assert op.COUNTS == {"staff-seven": 7, "magistr-two": 2, "behruz-one": 1}
    with pytest.raises(ValueError):
        op.inputs({"actor": "admin", "batch": "all"})
    with pytest.raises(ValueError):
        op.inputs({"actor": "admin", "batch": "staff-seven", "force": True})


@pytest.mark.parametrize(
    "change",
    [
        {"apply": "yes"},
        {"apply": True},
        {"apply": True, "baseline": "a" * 64},
        {"confirm": "APPLY"},
        {"actor": "bad;cmd"},
    ],
)
def test_reject_unreviewed_inputs(change):
    with pytest.raises(ValueError):
        op.inputs({"actor": "admin", "batch": "staff-seven", **change})


def valid():
    return dict(
        status="dry_run",
        baseline="a" * 64,
        requested=7,
        eligible=3,
        skipped=4,
        issued=0,
        encrypted_sha256="none",
        academic_review_required=0,
    )


def test_safe_closed_summary_only():
    raw = valid()
    assert op.summary(op.PREFIX + json.dumps(raw), batch="staff-seven", apply=False, baseline="") == raw
    raw["password"] = "secret-sentinel"
    with pytest.raises(ValueError):
        op.summary(op.PREFIX + json.dumps(raw), batch="staff-seven", apply=False, baseline="")


@pytest.mark.parametrize(
    "change",
    [
        {"issued": 1},
        {"requested": 100},
        {"eligible": True},
        {"skipped": 5},
        {"status": "applied"},
        {"encrypted_sha256": "secret-sentinel"},
    ],
)
def test_summary_false_claims_refused(change):
    with pytest.raises(ValueError):
        op.summary(op.PREFIX + json.dumps({**valid(), **change}), batch="staff-seven", apply=False, baseline="")


def test_workflow_encrypted_only():
    text = (ROOT / ".github/workflows/reviewed-targeted-credentials.yml").read_text()
    assert "production-deploy" in text
    assert "success() && inputs.apply" in text
    assert "*.enc.json" in text and "retention-days: 1" in text
    assert "persist-credentials: false" in text


def test_local_decoder_authenticated_csv_roundtrip_and_tamper(monkeypatch):
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from core.encrypted_export import encrypt_export

    decoder_spec = importlib.util.spec_from_file_location(
        "targeted_decoder", ROOT / "scripts/ops/decrypt_targeted_credentials.py"
    )
    decoder = importlib.util.module_from_spec(decoder_spec)
    decoder_spec.loader.exec_module(decoder)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    finger = hashlib.sha256(der).hexdigest()
    monkeypatch.setattr(decoder, "FINGERPRINT", finger)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    csv = "ad_soyad_ata_adi,username,ilkin_parol\nPrivate Name,private.user,private-password\n"
    payload = dict(format="wcu-targeted-credentials/1", batch="magistr-two", baseline="a" * 64, csv=csv)
    envelope = encrypt_export(payload, public, fingerprint=finger)
    assert decoder.decode(json.dumps(envelope).encode(), private) == csv
    envelope["ciphertext"] = "invalid"
    with pytest.raises(binascii.Error):
        decoder.decode(json.dumps(envelope).encode(), private)


def test_transport_preserves_preexisting_private_directory(monkeypatch, tmp_path):
    folder = tmp_path / "targeted-credentials"
    folder.mkdir()
    sentinel = folder / "older.enc.json"
    sentinel.write_text("existing-ciphertext")
    monkeypatch.setattr(op, "verify_head", lambda _head: None)
    with pytest.raises(ValueError, match="fresh_output_directory"):
        op.execute(
            dict(actor="admin", batch="staff-seven", apply=True, baseline="a" * 64, confirm="APPLY"),
            dict(GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="a" * 40, RUNNER_TEMP=str(tmp_path)),
        )
    assert sentinel.read_text() == "existing-ciphertext"
