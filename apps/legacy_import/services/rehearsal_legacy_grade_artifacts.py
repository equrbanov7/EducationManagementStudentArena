"""Köhnə çap olunmuş bal vərəqlərinin sıxılmış immutable arxivi.

``balvereqi_logs`` 52,386 export hadisəsində təxminən 1 GB HTML snapshot
daşıyır. Mətn heç vaxt loga/hesabata çıxmır: UTF-8 baytları hash-lənir, zlib
ilə sıxılır və tenant-scoped append-only modeldə saxlanır. Materializasiya
digest-i sıxılmış baytlardan asılı deyil; payload SHA-256 + açılmamış ölçü
cross-run deterministik sübutdur.
"""

from __future__ import annotations

import datetime
import hashlib
import zlib
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction

from .legacy_grade_artifact_contracts import (
    ARTIFACT_KIND,
    COMPRESSION,
    COMPRESSION_LEVEL,
    MAX_ARTIFACT_BYTES,
    artifact_materialization_digest,
    artifact_source_row_hash,
)
from .legacy_grade_field_contracts import SCORE_SHEET_EXPORT_FIELDS
from .rehearsal_authorizer import LEGACY_GRADE_ARTIFACT_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalEvidenceError,
    RehearsalContext,
)
from .rehearsal_journal_batch import normalized_key
from .rehearsal_journal_offerings_source import legacy_int
from .rehearsal_journal_points_source import attested_rows, legacy_text

ARTIFACT_ENTITY_TYPE = "legacy_grade_artifact"


@dataclass(frozen=True)
class GradeArtifactRequest:
    source_table: str
    source_pk: int
    source_row_hash: str
    payload: dict[str, object]

    @property
    def seal_key(self) -> str:
        return f"{self.source_table}:{self.source_pk}"


def artifact_rows(context: RehearsalContext):
    return attested_rows(
        context,
        contract=SCORE_SHEET_EXPORT_FIELDS,
        source_table=SCORE_SHEET_EXPORT_FIELDS.source_table,
    )


def _exported_at_text(value: object) -> str:
    if type(value) is not datetime.datetime:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value.isoformat(sep=" ")


def _payload_bytes(value: object) -> bytes:
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    try:
        payload = value.encode("utf-8", "strict")
    except UnicodeError:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported") from None
    if not payload or len(payload) > MAX_ARTIFACT_BYTES:
        raise LegacyRehearsalEvidenceError("legacy_grade_artifact_payload_size_invalid")
    return payload


def artifact_requests(context: RehearsalContext, *, rows):
    for legacy_pk, row in rows:
        raw = _payload_bytes(row["data"])
        payload_sha256 = hashlib.sha256(raw).hexdigest()
        payload_size = len(raw)
        yield GradeArtifactRequest(
            source_table=SCORE_SHEET_EXPORT_FIELDS.source_table,
            source_pk=legacy_pk,
            source_row_hash=artifact_source_row_hash(
                legacy_pk=legacy_pk,
                row=row,
                payload_sha256=payload_sha256,
                payload_size=payload_size,
            ),
            payload={
                "artifact_kind": ARTIFACT_KIND,
                "source_owner_ref": str(legacy_int(row["owner_id"])),
                "source_journal_ref": legacy_text(row["uniqid"]),
                "source_exported_at_text": _exported_at_text(row["export_time"]),
                "payload_sha256": payload_sha256,
                "payload_size_bytes": payload_size,
                "payload_zlib": zlib.compress(raw, COMPRESSION_LEVEL),
                "requires_exam_center_review": True,
            },
        )


class LegacyGradeArtifactMaterialiser:
    def __init__(self) -> None:
        self._payloads: dict[tuple[str, ...], dict[str, object]] = {}

    def stage(self, natural_key: tuple, payload: dict[str, object]) -> None:
        key = normalized_key(natural_key)
        if key in self._payloads:
            raise LegacyRehearsalEvidenceError("legacy_grade_artifact_batch_duplicate")
        self._payloads[key] = dict(payload)

    def resolve(self, context, keys) -> dict[tuple[str, ...], str]:
        ordered = list(dict.fromkeys(keys))
        if not ordered:
            return {}
        wanted = {normalized_key(key) for key in ordered}
        model = django_apps.get_model("registrar", "LegacyGradeArtifact")
        rows = model.objects.filter(
            organization=context.organization,
            source_system__in={key[0] for key in ordered},
            source_table__in={key[1] for key in ordered},
            source_pk__in={key[2] for key in ordered},
        ).values_list(
            "pk",
            "source_system",
            "source_table",
            "source_pk",
            "materialization_digest",
            "payload_sha256",
            "payload_size_bytes",
        )
        resolved: dict[tuple[str, ...], str] = {}
        for pk, source_system, source_table, source_pk, digest, payload_hash, payload_size in rows:
            key = normalized_key((source_system, source_table, source_pk))
            if key not in wanted:
                continue
            payload = self._payloads.get(key)
            if (
                payload is None
                or digest != payload["materialization_digest"]
                or payload_hash != payload["payload_sha256"]
                or payload_size != payload["payload_size_bytes"]
            ):
                raise LegacyRehearsalEvidenceError("legacy_grade_artifact_identity_conflict")
            resolved[key] = str(pk)

        missing = [key for key in ordered if normalized_key(key) not in resolved]
        if missing:
            pending = []
            for source_system, source_table, source_pk in missing:
                payload = self._payloads.get(normalized_key((source_system, source_table, source_pk)))
                if payload is None:
                    raise LegacyRehearsalEvidenceError("legacy_grade_artifact_payload_missing")
                pending.append(
                    model(
                        organization=context.organization,
                        source_system=source_system,
                        source_table=source_table,
                        source_pk=source_pk,
                        **payload,
                    )
                )
            with transaction.atomic():
                model.objects.bulk_create(pending)
            for key, instance in zip(missing, pending):
                resolved[normalized_key(key)] = str(instance.pk)

        for key in wanted:
            self._payloads.pop(key, None)
        return resolved


__all__ = [
    "ARTIFACT_ENTITY_TYPE",
    "COMPRESSION",
    "GradeArtifactRequest",
    "LEGACY_GRADE_ARTIFACT_MODEL_LABEL",
    "LegacyGradeArtifactMaterialiser",
    "artifact_materialization_digest",
    "artifact_requests",
    "artifact_rows",
    "artifact_source_row_hash",
]
