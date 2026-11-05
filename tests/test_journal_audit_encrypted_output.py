"""Exercise the fixed audit's encrypted output inside real read-only PostgreSQL."""

import base64
import gzip
import hashlib
import json
import stat
from decimal import Decimal
from uuid import UUID

from django.db import DatabaseError, connection, transaction

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.prod_ops import journal_integrity_snapshot as snapshot

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def audit_output(monkeypatch, tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    output = tmp_path / "synthetic-audit.enc.json"
    monkeypatch.setenv("AUDIT_PUBLIC_KEY_B64", base64.b64encode(public_pem).decode())
    monkeypatch.setenv("AUDIT_OUTPUT", str(output))
    monkeypatch.setattr(snapshot, "DATA", {})
    monkeypatch.setattr(snapshot, "SCHEMA_GAPS", {})
    monkeypatch.setattr(snapshot, "ORG", "cafe0000-0000-0000-0000-000000000001")
    return output, private_key


def test_main_encrypts_only_after_real_read_only_capture(audit_output, monkeypatch, capsys):
    output, private_key = audit_output
    marker = "SYNTHETIC_PRIVATE_AUDIT_VALUE_DO_NOT_LOG"
    observed = {}

    def collect_synthetic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('transaction_isolation'), txid_current_snapshot()"
            )
            observed["read_only"], observed["isolation"], observed["snapshot_id"] = cursor.fetchone()
        # Even an update that cannot affect any row must be refused. A savepoint
        # isolates the expected PostgreSQL error so the capture can still finish.
        with pytest.raises(DatabaseError) as denied:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE django_migrations SET applied = applied WHERE 1 = 0")
        cause = denied.value.__cause__
        observed["write_denial"] = getattr(cause, "sqlstate", getattr(cause, "pgcode", None))
        snapshot.DATA["synthetic.rows"] = [
            {"id": UUID("cafe0000-0000-0000-0000-000000000002"), "score": Decimal("27.50"), "note": marker}
        ]

    monkeypatch.setattr(snapshot, "collect", collect_synthetic)
    snapshot.main()

    assert observed["read_only"] == "on"
    assert observed["isolation"] == "repeatable read"
    assert observed["write_denial"] == "25006"  # read_only_sql_transaction
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert list(output.parent.iterdir()) == [output]
    envelope_bytes = output.read_bytes()
    assert marker.encode() not in envelope_bytes
    envelope = json.loads(envelope_bytes)
    assert set(envelope) == {"format", "sha256", "nonce", "wrapped_key", "ciphertext"}
    assert envelope["format"] == "wcu-journal-integrity-audit/20261104"
    key = private_key.decrypt(
        base64.b64decode(envelope["wrapped_key"]),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    aad = envelope["format"].encode()
    raw = gzip.decompress(AESGCM(key).decrypt(nonce, ciphertext, aad))
    assert hashlib.sha256(raw).hexdigest() == envelope["sha256"]
    payload = json.loads(raw)
    assert payload["synthetic.rows"] == [
        {"id": "cafe0000-0000-0000-0000-000000000002", "score": "27.50", "note": marker}
    ]
    assert payload["metadata"]["organization_id"] == snapshot.ORG
    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["snapshot_id"] == str(observed["snapshot_id"])
    assert payload["metadata"]["captured_at"]
    assert payload["metadata"]["finished_at"]
    assert payload["metadata"]["schema_gaps"] == {}
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(nonce, ciphertext[:-1] + bytes([ciphertext[-1] ^ 1]), aad)
    logged = capsys.readouterr()
    assert json.loads(logged.out) == {"read_only": True, "counts": {"synthetic.rows": 1}}
    assert marker not in logged.out + logged.err
    assert not logged.err


def test_main_never_overwrites_an_existing_output(audit_output, monkeypatch, capsys):
    output, _private_key = audit_output
    existing = b"EXISTING_ARTIFACT_MUST_REMAIN_UNCHANGED"
    output.write_bytes(existing)
    output.chmod(0o640)
    monkeypatch.setattr(snapshot, "collect", lambda: snapshot.DATA.update({"synthetic.rows": []}))

    with pytest.raises(FileExistsError):
        snapshot.main()

    assert output.read_bytes() == existing
    assert stat.S_IMODE(output.stat().st_mode) == 0o640
    assert list(output.parent.iterdir()) == [output]
    logged = capsys.readouterr()
    assert not logged.out and not logged.err
