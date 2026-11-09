"""Real PG read-only capture and authenticated envelopes with byte-bounded shards."""

import base64
import hashlib
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.legacy_import.services import reaudit_snapshot as export
from core.rls import bypass_rls


@pytest.fixture(scope="module")
def recipient():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key()
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return private, pem, hashlib.sha256(der).hexdigest()


def decrypt(path, private):
    envelope = json.loads(path.read_bytes())
    metadata = {key: envelope[key] for key in ("format", "cipher", "key_sha256")}
    key = private.decrypt(
        base64.b64decode(envelope["wrapped_key"]),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    raw = AESGCM(key).decrypt(
        base64.b64decode(envelope["nonce"]),
        base64.b64decode(envelope["ciphertext"]),
        json.dumps(metadata, sort_keys=True).encode(),
    )
    return raw, json.loads(raw)


def prepare(tmp_path, monkeypatch, recipient, bodies):
    assert connection.vendor == "postgresql"
    with bypass_rls():
        actor = get_user_model().objects.create_user("synthetic-byte-operator")
        organization = apps.get_model("organizations", "Organization").objects.create(
            id=export.ORG,
            name="Synthetic byte capture",
            slug="synthetic-bytes",
            owner=actor,
        )
        audit = apps.get_model("audit", "AuditLog")
        rows = [
            audit.objects.create(
                organization=organization,
                user=actor,
                action="update",
                changes={"synthetic": body},
            )
            for body in bodies
        ]
    public = tmp_path / "synthetic-public.pem"
    public.write_bytes(recipient[1])
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    monkeypatch.setattr(export, "KEY_FINGERPRINT", recipient[2])
    monkeypatch.setattr(export, "validate_actor", lambda _: actor.pk)
    monkeypatch.setattr(
        export,
        "SCHEMAS",
        {"audit.AuditLog": {"fields": ["id", "changes", "created_at"]}},
    )
    monkeypatch.setattr(
        export,
        "scoped_query",
        lambda *_: audit.objects.filter(pk__in=[row.pk for row in rows]),
    )
    return public, output, rows


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("pooled", [False, True])
def test_one_query_page_yields_contiguous_authenticated_byte_shards(tmp_path, monkeypatch, recipient, settings, pooled):
    settings.RLS_TRANSACTION_SCOPED = pooled
    marker = "Əşü😀-private-synthetic-"
    public, output, rows = prepare(tmp_path, monkeypatch, recipient, [marker * 30 for _ in range(12)])
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", 1600)
    assert export.CHUNK_ROWS == 2000
    with CaptureQueriesContext(connection) as queries:
        result = export.capture("operator", public, output)
    assert result["shards"] == 12 and result["rows"] == 12
    assert sum('"audit_auditlog"' in row["sql"] and "LIMIT 2000" in row["sql"] for row in queries) == 1
    assert not any(row["sql"].lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")) for row in queries)
    manifest = json.loads((output / "manifest.json").read_bytes())
    assert manifest["complete"] and manifest["read_only"]
    assert [shard["page"] for shard in manifest["shards"]] == list(range(12))
    observed = []
    for shard in manifest["shards"]:
        path = output / shard["file"]
        raw, payload = decrypt(path, recipient[0])
        assert len(raw) <= export.MAX_CHUNK_BYTES
        assert hashlib.sha256(raw).hexdigest() == shard["plaintext_sha256"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == shard["sha256"]
        assert payload["page"] == shard["page"] and len(payload["rows"]) == shard["rows"] == 1
        assert marker.encode() not in path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
        observed.extend(payload["rows"])
    assert [row["id"] for row in observed] == sorted(str(row.pk) for row in rows)
    assert all(row["changes"]["synthetic"] == marker * 30 for row in observed)


@pytest.mark.django_db(transaction=True)
def test_single_oversize_row_refuses_without_complete_manifest(tmp_path, monkeypatch, recipient):
    public, output, _ = prepare(tmp_path, monkeypatch, recipient, ["ə😀" * 400])
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", 1000)
    with pytest.raises(ValueError, match="snapshot_chunk_budget_exceeded"):
        export.capture("operator", public, output)
    assert not (output / "manifest.json").exists()
    assert list(output.iterdir()) == []


@pytest.mark.django_db(transaction=True)
def test_total_bytes_still_refuse_after_a_partial_encrypted_capture(tmp_path, monkeypatch, recipient):
    public, output, _ = prepare(tmp_path, monkeypatch, recipient, ["ə😀" * 120] * 3)
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", 1600)
    monkeypatch.setattr(export, "MAX_TOTAL_BYTES", 1700)
    with pytest.raises(ValueError, match="snapshot_total_byte_budget_exceeded"):
        export.capture("operator", public, output)
    assert not (output / "manifest.json").exists()
    assert len(list(output.glob("*.enc.json"))) == 1


def test_exact_utf8_limit_and_page_digit_boundary(monkeypatch):
    context = {"format": "synthetic-ə"}
    rows = [{"id": index, "value": "ə😀" * 30} for index in range(3)]
    limit = len(export.encode({**context, "page": 9, "rows": rows[:2]}))
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", limit)
    chunks = list(export.byte_chunks(context, rows, 9))
    assert [payload["page"] for payload, _raw in chunks] == [9, 10]
    assert [len(payload["rows"]) for payload, _raw in chunks] == [2, 1]
    assert len(chunks[0][1]) == limit
    assert all(len(raw) <= limit and raw == export.encode(payload) for payload, raw in chunks)
    assert [row for payload, _raw in chunks for row in payload["rows"]] == rows


def test_single_row_one_byte_over_boundary_refuses(monkeypatch):
    row = {"id": 1, "text": "ə😀"}
    exact = len(export.encode({"page": 0, "rows": [row]}))
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", exact)
    assert len(list(export.byte_chunks({}, [row], 0))[0][1]) == exact
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", exact - 1)
    with pytest.raises(ValueError, match="snapshot_chunk_budget_exceeded"):
        list(export.byte_chunks({}, [row], 0))
