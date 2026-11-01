"""Pinned read-only inventory: identities, never authority for corrective writes."""

import hashlib
import json
from pathlib import Path

from ..scoped_snapshot import SnapshotError

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
FORMAT = "wcu-journal-cells/1"
REGISTRY_SHA = "1783da2b28d6a669266d09f7c313ea8a4d1b59a80e76b730f2dcda20a0cc7b87"
MAX_OFFERINGS = 25
MAX_MARKS = 250000
MAX_ROWS = 300000
MAX_BYTES = 128 * 1024 * 1024


def batch_spec(name):
    encoded = Path(__file__).with_name("batches.json").read_bytes()
    if hashlib.sha256(encoded).hexdigest() != REGISTRY_SHA:
        raise SnapshotError("registry_fingerprint_mismatch")
    registry = json.loads(encoded)
    spec = registry["batches"].get(name)
    if spec is None or not 1 <= len(spec["offerings"]) <= MAX_OFFERINGS:
        raise SnapshotError("pinned_batch_required")
    return spec
