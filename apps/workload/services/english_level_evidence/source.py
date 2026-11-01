"""Only the fixed reviewed encrypted-source plaintext may enter this metadata audit."""

import hashlib
import json
import re
import stat
from pathlib import Path

from apps.workload.services.scoped_snapshot import SnapshotError

from . import spec
from .identity import fin, fingerprint

HEADER = set(
    "format organization_id academic_year period_id namespace institutional_identifier_rule source_container captured_at source_query_sha256 source_rows_sha256 roster_proof_sha256 source_ids_sha256 records".split()
)
FIELDS = set("id institutional_identifier normalized_fin fin_present fin_valid fin_sha256 source_row_sha256".split())


def load(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SnapshotError("english_level_private_source_file_required")
    raw = path.read_bytes()
    if len(raw) > spec.MAX_BYTES or expected != spec.SOURCE_SHA or hashlib.sha256(raw).hexdigest() != spec.SOURCE_SHA:
        raise SnapshotError("english_level_source_digest_required")
    try:
        value = json.loads(raw)
        if set(value) != HEADER or (
            value["format"],
            value["organization_id"],
            value["academic_year"],
            value["period_id"],
            value["namespace"],
        ) != (
            spec.SOURCE_FORMAT,
            spec.ORG,
            spec.YEAR,
            spec.PERIOD,
            "myedu_new.students.id",
        ):
            raise ValueError
        rows = value["records"]
        ids = [row["id"] for row in rows]
        if (
            len(rows) != spec.SOURCE_COUNT
            or ids != sorted(set(ids))
            or any(type(pk) is not int or pk <= 0 for pk in ids)
        ):
            raise ValueError
        if hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest() != spec.SOURCE_IDS_SHA:
            raise ValueError
        for row in rows:
            if (
                set(row) != FIELDS
                or row["institutional_identifier"] != str(row["id"])
                or not re.fullmatch("[0-9a-f]{64}", row["source_row_sha256"])
            ):
                raise ValueError
            if type(row["fin_valid"]) is not bool or type(row["fin_present"]) is not bool:
                raise ValueError
            if row["normalized_fin"] != fin(row["normalized_fin"]):
                raise ValueError
            if (
                (row["fin_valid"] and not row["fin_present"])
                or row["fin_valid"] != bool(row["normalized_fin"])
                or row["fin_sha256"] != fingerprint(row["normalized_fin"])
            ):
                raise ValueError
        return value
    except (KeyError, ValueError, TypeError):
        raise SnapshotError("english_level_source_schema_refused") from None
