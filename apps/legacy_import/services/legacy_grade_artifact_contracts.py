"""Legacy bal-vərəqi artifact-ları üçün Django-dan asılı olmayan müqavilə.

Importer və read-only reconciliation CLI eyni hash/digest funksiyalarını
işlədir. Bu modul qəsdən model, settings və Django app registry-si import etmir;
beləliklə reconciliation CLI hətta ``--help`` zamanı da DB konteksti qaldırmır.
"""

from __future__ import annotations

import hashlib

from .legacy_grade_field_contracts import SCORE_SHEET_EXPORT_FIELDS
from .rehearsal_contracts import encoded_part, stable_source_value

ARTIFACT_KIND = "score_sheet_export"
COMPRESSION = "zlib"
COMPRESSION_LEVEL = 9
MAX_ARTIFACT_BYTES = 1 << 20
MATERIALIZATION_DIGEST_NAMESPACE = b"legacy-grade-artifact-materialization-v1\x00"
SOURCE_ROW_DIGEST_NAMESPACE = b"legacy-grade-artifact-source-row-v1\x00"


def artifact_source_row_hash(*, legacy_pk: int, row, payload_sha256: str, payload_size: int) -> str:
    """Böyük ``data`` sahəsini məzmun hash-i və ölçü ilə möhürlə."""

    digest = hashlib.sha256(SOURCE_ROW_DIGEST_NAMESPACE)
    for part in (
        SCORE_SHEET_EXPORT_FIELDS.fingerprint,
        SCORE_SHEET_EXPORT_FIELDS.source_table,
        str(legacy_pk),
    ):
        digest.update(encoded_part(part))
    for field_name in SCORE_SHEET_EXPORT_FIELDS.allowed_fields:
        digest.update(encoded_part(field_name))
        if field_name == "data":
            value = f"sha256:{payload_sha256}:bytes:{payload_size}"
        else:
            value = stable_source_value(row[field_name])
        digest.update(encoded_part(value))
    return digest.hexdigest()


def artifact_materialization_digest(*, natural_key: tuple, source_row_hash: str, payload) -> str:
    """Importer və reconciliation üçün ortaq deterministik artifact möhürü."""

    digest = hashlib.sha256(MATERIALIZATION_DIGEST_NAMESPACE)
    for part in natural_key:
        digest.update(encoded_part(str(part)))
    digest.update(encoded_part(source_row_hash))
    deterministic = {key: value for key, value in payload.items() if key != "payload_zlib"}
    for key in sorted(deterministic):
        digest.update(encoded_part(key))
        digest.update(encoded_part(stable_source_value(deterministic[key])))
    return digest.hexdigest()


__all__ = [
    "ARTIFACT_KIND",
    "COMPRESSION",
    "COMPRESSION_LEVEL",
    "MATERIALIZATION_DIGEST_NAMESPACE",
    "MAX_ARTIFACT_BYTES",
    "SOURCE_ROW_DIGEST_NAMESPACE",
    "artifact_materialization_digest",
    "artifact_source_row_hash",
]
