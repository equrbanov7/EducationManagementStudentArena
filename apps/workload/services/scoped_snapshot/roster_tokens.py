"""Unlinkable-between-snapshots student-set comparison; no identifiers in output."""

import hashlib
import hmac
from collections import defaultdict


def tokenize(records, *, secret, organization, group_fields):
    if len(secret) < 32:
        raise ValueError("snapshot_secret_too_short")
    grouped = defaultdict(set)
    for record in records:
        if record["student_id"] is None:
            raise ValueError("student_reference_missing")
        # Deliberately independent of group/period: one student has the same opaque
        # token across all tenant-local groups in this snapshot. Secret is not exported.
        message = f"{organization}:student:{record['student_id']}".encode()
        token = hmac.new(secret, message, hashlib.sha256).hexdigest()
        grouped[tuple(record[field] for field in group_fields)].add(token)
    return [
        {**dict(zip(group_fields, fields)), "count": len(tokens), "student_tokens": sorted(tokens)}
        for fields, tokens in sorted(grouped.items(), key=lambda pair: tuple(str(x) for x in pair[0]))
    ]
