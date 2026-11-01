"""Additive fixed first/last-ten audit; old25-total-history limit remains unchanged."""

import copy
import hashlib
import json

from django.db import connection, transaction

from .chair_cells_export import _capture, query_budget, save_encrypted  # noqa: F401
from .chair_cells_export.spec import batch_spec as parent_spec
from .scoped_snapshot import SnapshotError

FORMAT = "wcu-journal-cells-part/1"
PARENTS = tuple(f"chair-cells-{number:03}" for number in (40, 43, 53, 64, 65, 66, 67, 68, 69, 70))
PARTS = tuple(f"{parent}-part-{index:03}" for parent in PARENTS for index in (1, 2))
POLICY = "wcu-chair-cells-reviewed-halves/1"


def selection(part):
    if part not in PARTS:
        raise SnapshotError("fixed_journal_part_required")
    name = part.split("-part-")[0]
    parent = parent_spec(name)
    if len(parent["offerings"]) != 20:
        raise SnapshotError("fixed_parent_twenty_roots_required")
    result = copy.deepcopy(parent)
    offset = (int(part.rsplit("-", 1)[1]) - 1) * 10
    result["offerings"] = result["offerings"][offset : offset + 10]
    parent_sha = hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest()
    return result, parent_sha, name


def capture(username, part):
    spec, parent_sha, parent = selection(part)
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            # Spec injection into the existing collector, never a monkeypatch.
            # Its unchanged25 TOTAL courses include both-direction history closure.
            payload = _capture(username, spec, parent)
        payload.update(
            format=FORMAT,
            parent_batch=parent,
            part=part,
            part_count=2,
            partition_policy=POLICY,
            parent_selection_sha256=parent_sha,
        )
        return payload
