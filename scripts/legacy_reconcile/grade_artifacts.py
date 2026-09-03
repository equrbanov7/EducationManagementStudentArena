"""Bal-vərəqi export arxivinin PII-siz, hash/sıxılma səviyyəli uzlaşdırması."""

from __future__ import annotations

import datetime
import hashlib
import re
import zlib
from collections import Counter
from dataclasses import dataclass

from apps.legacy_import.services.legacy_grade_artifact_contracts import (
    ARTIFACT_KIND,
    MATERIALIZATION_DIGEST_NAMESPACE,
    artifact_source_row_hash,
)
from apps.legacy_import.services.rehearsal_contracts import encoded_part, stable_source_value

from .analysis import fmt_int, md_table

SOURCE_SYSTEM = "myedu_mariadb"
SOURCE_TABLE = "balvereqi_logs"
ARTIFACT_MODEL_LABEL = "registrar.legacygradeartifact"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

SOURCE_ARTIFACT_ROWS_SQL = """
SELECT id, owner_id, uniqid, CAST(export_time AS CHAR),
       LOWER(SHA2(CONVERT(data USING utf8mb4), 256)), OCTET_LENGTH(data)
  FROM balvereqi_logs
 ORDER BY id;
"""

TARGET_ARTIFACT_ROWS_SQL = """
WITH selected_run AS (
    SELECT id, organization_id, source_system, snapshot_sha256, transform_version
      FROM legacy_import_legacymigrationrun
     WHERE id = %s AND status = 'succeeded'
)
SELECT a.source_pk::text, a.source_owner_ref, a.source_journal_ref,
       a.source_exported_at_text, a.payload_sha256, a.payload_size_bytes,
       a.payload_zlib, a.source_row_hash, a.materialization_digest,
       a.source_snapshot_sha256, a.transform_version, a.id::text,
       a.requires_exam_center_review, a.artifact_kind, a.source_system, a.source_table,
       m.id::text, m.state, m.target_model_label, m.target_pk, m.source_row_hash,
       o.id::text, o.state, o.target_model_label, o.target_pk, o.source_row_hash
  FROM registrar_legacygradeartifact a
 CROSS JOIN selected_run r
  LEFT JOIN legacy_import_legacyentitymap m
    ON m.organization_id = a.organization_id
   AND m.source_system = a.source_system
   AND m.entity_type = 'legacy_grade_artifact'
   AND m.legacy_pk = a.source_table || ':' || a.source_pk::text
  LEFT JOIN legacy_import_legacyentityobservation o
    ON o.run_id = r.id AND o.entity_map_id = m.id
 WHERE a.organization_id = r.organization_id
   AND a.source_system = r.source_system
   AND a.source_snapshot_sha256 = r.snapshot_sha256
   AND a.transform_version = r.transform_version
 ORDER BY a.source_pk;
"""


def _text(value) -> str:
    return "" if value in (None, "NULL") else str(value)


def _boolean(value) -> bool:
    if type(value) is bool:
        return value
    return _text(value).casefold() in {"1", "t", "true"}


def _source_row(raw) -> tuple:
    if len(raw) != 6:
        raise ValueError("legacy_grade_artifact_source_shape_invalid")
    legacy_pk = int(raw[0])
    owner_ref = str(int(raw[1]))
    journal_ref = _text(raw[2])
    exported = datetime.datetime.fromisoformat(_text(raw[3]))
    payload_sha256 = _text(raw[4])
    payload_size = int(raw[5])
    projected = {
        "id": legacy_pk,
        "owner_id": int(raw[1]),
        "uniqid": journal_ref,
        "data": "",
        "export_time": exported,
    }
    row_hash = artifact_source_row_hash(
        legacy_pk=legacy_pk,
        row=projected,
        payload_sha256=payload_sha256,
        payload_size=payload_size,
    )
    return (
        legacy_pk,
        owner_ref,
        journal_ref,
        exported.isoformat(sep=" "),
        payload_sha256,
        payload_size,
        row_hash,
    )


def _materialization_digest(row) -> str:
    payload = {
        "artifact_kind": _text(row[13]),
        "source_owner_ref": _text(row[1]),
        "source_journal_ref": _text(row[2]),
        "source_exported_at_text": _text(row[3]),
        "payload_sha256": _text(row[4]),
        "payload_size_bytes": int(row[5]),
        "requires_exam_center_review": _boolean(row[12]),
        "source_snapshot_sha256": _text(row[9]),
        "source_row_hash": _text(row[7]),
        "transform_version": _text(row[10]),
    }
    digest = hashlib.sha256(MATERIALIZATION_DIGEST_NAMESPACE)
    for part in (SOURCE_SYSTEM, SOURCE_TABLE, int(row[0])):
        digest.update(encoded_part(str(part)))
    digest.update(encoded_part(_text(row[7])))
    for key in sorted(payload):
        digest.update(encoded_part(key))
        digest.update(encoded_part(stable_source_value(payload[key])))
    return digest.hexdigest()


def _target_payload_valid(row) -> bool:
    try:
        compressed = bytes(row[6])
        raw = zlib.decompress(compressed)
    except (TypeError, ValueError, zlib.error):
        return False
    return len(raw) == int(row[5]) and hashlib.sha256(raw).hexdigest() == _text(row[4])


def _guard_failures(row) -> tuple[str, ...]:
    artifact_pk = _text(row[11])
    checks = {
        "review_required_false": _boolean(row[12]),
        "artifact_kind_invalid": _text(row[13]) == ARTIFACT_KIND,
        "source_system_invalid": _text(row[14]) == SOURCE_SYSTEM,
        "source_table_invalid": _text(row[15]) == SOURCE_TABLE,
        "source_hash_invalid": bool(SHA256_RE.fullmatch(_text(row[7]))),
        "payload_hash_invalid": bool(SHA256_RE.fullmatch(_text(row[4]))),
        "materialization_digest_invalid": _materialization_digest(row) == _text(row[8]),
        "compressed_payload_invalid": _target_payload_valid(row),
        "ledger_map_missing": bool(_text(row[16])),
        "ledger_map_state_invalid": _text(row[17]) == "migrated",
        "ledger_map_label_invalid": _text(row[18]) == ARTIFACT_MODEL_LABEL,
        "ledger_map_target_invalid": _text(row[19]) == artifact_pk,
        "ledger_map_digest_invalid": _text(row[20]) == _text(row[8]),
        "ledger_observation_missing": bool(_text(row[21])),
        "ledger_observation_state_invalid": _text(row[22]) == "migrated",
        "ledger_observation_label_invalid": _text(row[23]) == ARTIFACT_MODEL_LABEL,
        "ledger_observation_target_invalid": _text(row[24]) == artifact_pk,
        "ledger_observation_digest_invalid": _text(row[25]) == _text(row[8]),
    }
    return tuple(code for code, passed in checks.items() if not passed)


@dataclass(frozen=True)
class GradeArtifactReconciliation:
    source_rows: int
    target_rows: int
    source_duplicates: int
    target_duplicates: int
    missing_keys: int
    extra_keys: int
    metadata_mismatches: int
    source_hash_mismatches: int
    source_payload_bytes: int
    target_payload_bytes: int
    guard_failures: dict[str, int]

    @property
    def passed(self) -> bool:
        return (
            not any(
                (
                    self.source_duplicates,
                    self.target_duplicates,
                    self.missing_keys,
                    self.extra_keys,
                    self.metadata_mismatches,
                    self.source_hash_mismatches,
                    sum(self.guard_failures.values()),
                )
            )
            and self.source_payload_bytes == self.target_payload_bytes
        )


def _index(rows, key_index=0):
    indexed = {}
    duplicates = 0
    for row in rows:
        key = int(row[key_index])
        if key in indexed:
            duplicates += 1
        else:
            indexed[key] = row
    return indexed, duplicates


def reconcile_grade_artifacts(source, target, *, run_id) -> GradeArtifactReconciliation:
    source_rows = [_source_row(row) for row in source.query("bal-vərəqi artifact metadata", SOURCE_ARTIFACT_ROWS_SQL)]
    query = getattr(target, "iter_query", None)
    if callable(query):
        target_stream = query(
            "immutable bal-vərəqi artifact-ləri",
            TARGET_ARTIFACT_ROWS_SQL,
            (str(run_id),),
            chunk_size=100,
        )
    else:
        target_stream = target.query(
            "immutable bal-vərəqi artifact-ləri",
            TARGET_ARTIFACT_ROWS_SQL,
            (str(run_id),),
        )
    source_index, source_duplicates = _index(source_rows)
    target_index = {}
    target_duplicates = 0
    target_rows = 0
    target_payload_bytes = 0
    guard_failures: Counter[str] = Counter()
    for row in target_stream:
        target_rows += 1
        target_payload_bytes += int(row[5])
        guard_failures.update(_guard_failures(row))
        key = int(row[0])
        if key in target_index:
            target_duplicates += 1
            continue
        compact = list(row)
        compact[6] = b""  # açılmış/sıxılmış payload guard-dan sonra RAM-da saxlanmır
        target_index[key] = tuple(compact)
    source_keys = set(source_index)
    target_keys = set(target_index)
    shared = source_keys & target_keys
    metadata_mismatches = 0
    source_hash_mismatches = 0
    for key in shared:
        source_row = source_index[key]
        target_row = target_index[key]
        if source_row[1:6] != (
            _text(target_row[1]),
            _text(target_row[2]),
            _text(target_row[3]),
            _text(target_row[4]),
            int(target_row[5]),
        ):
            metadata_mismatches += 1
        if source_row[6] != _text(target_row[7]):
            source_hash_mismatches += 1

    return GradeArtifactReconciliation(
        source_rows=len(source_rows),
        target_rows=target_rows,
        source_duplicates=source_duplicates,
        target_duplicates=target_duplicates,
        missing_keys=len(source_keys - target_keys),
        extra_keys=len(target_keys - source_keys),
        metadata_mismatches=metadata_mismatches,
        source_hash_mismatches=source_hash_mismatches,
        source_payload_bytes=sum(row[5] for row in source_rows),
        target_payload_bytes=target_payload_bytes,
        guard_failures=dict(sorted(guard_failures.items())),
    )


def render_grade_artifact_reconciliation(result: GradeArtifactReconciliation) -> str:
    verdict = "✅ TAM TUTUR" if result.passed else "🔴 UYĞUNSUZLUQ VAR"
    rows = [
        ["Mənbə export sətri", fmt_int(result.source_rows)],
        ["Immutable hədəf artifact-ı", fmt_int(result.target_rows)],
        ["Mənbə payload baytı", fmt_int(result.source_payload_bytes)],
        ["Hədəfdə möhürlənmiş açılmamış bayt", fmt_int(result.target_payload_bytes)],
        ["Çatışmayan mənbə açarı", fmt_int(result.missing_keys)],
        ["Artıq hədəf açarı", fmt_int(result.extra_keys)],
        ["Metadata uyğunsuzluğu", fmt_int(result.metadata_mismatches)],
        ["Müstəqil source hash uyğunsuzluğu", fmt_int(result.source_hash_mismatches)],
        ["Sıxılma / ledger / tenant / digest pozuntusu", fmt_int(sum(result.guard_failures.values()))],
    ]
    guard_rows = [[f"`{code}`", fmt_int(count)] for code, count in result.guard_failures.items()]
    return "\n".join(
        [
            "## 4B. Çap olunmuş bal-vərəqi arxivinin itkisizlik sübutu",
            "",
            "> Xam HTML və fərdi məlumat hesabatda göstərilmir. Hər export-un source PK-si,",
            "> UTF-8 SHA-256-si, açılmamış ölçüsü və zlib-dən geri açılan baytları yoxlanır.",
            "",
            md_table(["Invariant", "Say"], rows),
            "",
            f"**Nəticə: {verdict}.**",
            *(["", "### Guard pozuntuları", "", md_table(["Kod", "Say"], guard_rows)] if guard_rows else []),
        ]
    )


__all__ = [
    "GradeArtifactReconciliation",
    "SOURCE_ARTIFACT_ROWS_SQL",
    "TARGET_ARTIFACT_ROWS_SQL",
    "reconcile_grade_artifacts",
    "render_grade_artifact_reconciliation",
]
