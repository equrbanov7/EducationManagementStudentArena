"""Bounded encrypted journal audit with a fresh tenant-scoped read-only transaction."""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.rls import apply_rls_request_context

from ..scoped_snapshot import SnapshotError, encrypt
from ..scoped_snapshot.data import ORG, YEAR
from .collect import SCHEMAS, collect
from .spec import FORMAT, MAX_BYTES, PERIOD, REGISTRY_SHA, batch_spec


def capture(username, batch):
    spec = batch_spec(batch)
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            return _capture(username, spec, batch)


@contextmanager
def query_budget():
    deadline = monotonic() + 120
    count = 0

    def enforce(execute, sql, params, many, context):
        nonlocal count
        count += 2  # The deadline-setting SELECT is also a database statement.
        remaining = int((deadline - monotonic()) * 1000)
        if remaining <= 0 or count > 200:
            raise SnapshotError("query_or_time_budget_exceeded")
        execute("SELECT set_config('statement_timeout', %s, true)", [f"{remaining}ms"], False, context)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(enforce):
        yield


def _capture(username, spec, batch):
    apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
    org = apps.get_model("organizations", "Organization")
    if not org.objects.filter(id=ORG, is_active=True, status="active").exists():
        raise SnapshotError("active_fixed_tenant_required")
    actor = (
        get_user_model()
        .objects.filter(
            Q(profile__organization_id=ORG)
            | Q(memberships__organization_id=ORG, memberships__is_active=True)
            | Q(owned_organizations__id=ORG),
            username=username,
            is_active=True,
            is_superuser=True,
        )
        .values_list("id", flat=True)
        .first()
    )
    if actor is None:
        raise SnapshotError("active_fixed_tenant_superuser_required")
    apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
    data, evidence = collect(spec)
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()[0] != "on":
            raise SnapshotError("readonly_transaction_required")
    return {
        "format": FORMAT,
        "organization_id": ORG,
        "academic_year": YEAR,
        "period_id": PERIOD,
        "batch": batch,
        "registry_sha256": REGISTRY_SHA,
        "captured_at": timezone.now().isoformat(),
        "actor_id": actor,
        "selection": spec,
        "read_only": True,
        "eligible_for_apply": False,
        "correction_coverage": evidence,
        "classification": "Snapshot chair metadata only; unresolved is unassigned. No write authority.",
        "schema_fields": SCHEMAS,
        "data": data,
        "counts": {key: len(rows) for key, rows in data.items()},
    }


def save_encrypted(snapshot, public_key, output):
    plaintext = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()
    # Include base64/envelope overhead in the same128MiB limit as local decrypt.
    if len(plaintext) * 4 // 3 + 4096 > MAX_BYTES:
        raise SnapshotError("encrypted_size_budget_exceeded")
    encoded = json.dumps(encrypt(snapshot, Path(public_key).read_bytes()), sort_keys=True).encode()
    if len(encoded) > MAX_BYTES:
        raise SnapshotError("encrypted_size_budget_exceeded")
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()
