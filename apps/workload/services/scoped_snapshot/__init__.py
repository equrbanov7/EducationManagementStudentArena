"""Fixed-tenant read-only snapshot and authenticated public-key envelope."""

import base64
import hashlib
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.rls import apply_rls_request_context

from .data import ORG, YEAR, collect
from .journal_diagnostics import collect_journal_diagnostics

KEY_FINGERPRINT = "f21b002d94fdd65fb346e557e6eb85109f60bda3afa8d8c5a2a14e4b9fc922bf"
FORMAT = "wcu-workload-snapshot/1"


class SnapshotError(ValueError):
    pass


def capture(username):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        # Fixed tenant, no bypass, including when invoked from a superuser ops shell.
        apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
        actor = (
            get_user_model()
            .objects.filter(username=username, is_active=True, is_superuser=True)
            .values_list("id", flat=True)
            .first()
        )
        if actor is None:
            raise SnapshotError("active_superuser_required")
        apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
        data = collect(student_secret=os.urandom(32))
        data["journal_access_diagnostics"] = collect_journal_diagnostics(data)
        if not data["tasks"]:
            raise SnapshotError("fixed_org_tasks_missing")
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise SnapshotError("readonly_transaction_required")
        return {
            "format": FORMAT,
            "organization_id": ORG,
            "academic_year": YEAR,
            "captured_at": timezone.now().isoformat(),
            "actor_id": actor,
            "coverage": {
                "current_chairs": len({r["chair_id"] for r in data["tasks"]}),
                "current_tasks": len(data["tasks"]),
                "official_source_chairs": 14,
                "official_source_status": "external reconciliation coverage14/18; not a live completeness assertion",
            },
            "schema_fields": {key: sorted({field for row in values for field in row}) for key, values in data.items()},
            "fingerprints": "MD5 opaque change detectors, not cryptographic integrity; AES-GCM authenticates export",
            "student_set_tokens": "HMAC-SHA256 with random per-snapshot secret, never exported; same student stable only within this snapshot; exact group IDs preserved, no aliases or parent/child/sector merge",
            "data": data,
        }


def encrypt(snapshot, public_key_bytes):
    public = serialization.load_pem_public_key(public_key_bytes)
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise SnapshotError("rsa_key_invalid")
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != KEY_FINGERPRINT:
        raise SnapshotError("public_key_fingerprint_mismatch")
    plaintext = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    metadata = {
        "format": "wcu-workload-envelope/1",
        "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
        "key_sha256": KEY_FINGERPRINT,
    }
    aad = json.dumps(metadata, sort_keys=True).encode()
    wrapped = public.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return {
        **metadata,
        "nonce": base64.b64encode(nonce).decode(),
        "wrapped_key": base64.b64encode(wrapped).decode(),
        "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, plaintext, aad)).decode(),
    }


def save_encrypted(snapshot, public_key, output):
    envelope = encrypt(snapshot, Path(public_key).read_bytes())
    encoded = json.dumps(envelope, sort_keys=True).encode()
    # O_EXCL prevents overwriting an old snapshot;0600 from creation, no plaintext file.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()
