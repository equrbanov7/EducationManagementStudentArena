"""Append-only, hash-chained row accounting for large legacy imports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services import ledger

_CHAIN_VERSION = "legacy-import-batch-chain-v1"


class LegacyBatchError(ledger.LegacyLedgerError):
    """Sanitizasiya edilmiş batch-accounting xətası."""


class LegacyBatchConflictError(LegacyBatchError):
    pass


@dataclass(frozen=True)
class BatchCounts:
    migrated: int
    skipped: int
    quarantined: int

    @property
    def source_rows(self) -> int:
        return self.migrated + self.skipped + self.quarantined


def _persisted_actor(actor: Any):
    user_model = LegacyImportBatch._meta.get_field("recorded_by").remote_field.model
    if not isinstance(actor, user_model) or actor.pk is None:
        raise ledger.LegacyLedgerAuthorizationError("legacy_batch_actor_required")
    if not user_model._default_manager.filter(pk=actor.pk, is_active=True).exists():
        raise ledger.LegacyLedgerAuthorizationError("legacy_batch_actor_required")
    return actor


def _encoded_part(value: object) -> bytes:
    encoded = str(value).encode("utf-8", "strict")
    return len(encoded).to_bytes(8, "big") + encoded


def _chain_digest(*, run: LegacyMigrationRun, values: dict[str, object]) -> str:
    ordered = (
        _CHAIN_VERSION,
        run.pk,
        run.organization_id,
        run.source_system,
        run.snapshot_sha256,
        run.schema_version,
        run.transform_version,
        values["source_table"],
        values["entity_type"],
        values["sequence"],
        values["first_legacy_pk"],
        values["last_legacy_pk"],
        values["source_row_count"],
        values["migrated_count"],
        values["skipped_count"],
        values["quarantined_count"],
        values["contract_fingerprint"],
        values["source_digest"],
        values["classification_digest"],
        values["target_digest"],
        values["previous_chain_digest"],
    )
    digest = hashlib.sha256()
    for part in ordered:
        digest.update(_encoded_part(part))
    return digest.hexdigest()


def _batch_snapshot(batch: LegacyImportBatch) -> dict[str, object]:
    return {
        "source_table": batch.source_table,
        "entity_type": batch.entity_type,
        "sequence": batch.sequence,
        "first_legacy_pk": batch.first_legacy_pk,
        "last_legacy_pk": batch.last_legacy_pk,
        "source_row_count": batch.source_row_count,
        "migrated_count": batch.migrated_count,
        "skipped_count": batch.skipped_count,
        "quarantined_count": batch.quarantined_count,
        "contract_fingerprint": batch.contract_fingerprint,
        "source_digest": batch.source_digest,
        "classification_digest": batch.classification_digest,
        "target_digest": batch.target_digest,
        "previous_chain_digest": batch.previous_chain_digest,
        "chain_digest": batch.chain_digest,
    }


def _validate_integer(value: object, *, code: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise LegacyBatchConflictError(code)
    return value


@transaction.atomic
def record_batch(
    *,
    run_id: Any,
    actor: Any,
    authorize: ledger.LedgerAuthorizer,
    source_table: str,
    entity_type: str,
    sequence: int,
    first_legacy_pk: int,
    last_legacy_pk: int,
    migrated_count: int,
    skipped_count: int,
    quarantined_count: int,
    contract_fingerprint: str,
    source_digest: str,
    classification_digest: str,
    target_digest: str,
) -> LegacyImportBatch:
    """Möhürlənmiş batch-i yaz; exact retry no-op, fərqli retry conflict-dir."""

    sequence = _validate_integer(sequence, code="legacy_batch_sequence_invalid", minimum=1)
    first_legacy_pk = _validate_integer(
        first_legacy_pk,
        code="legacy_batch_first_pk_invalid",
        minimum=1,
    )
    last_legacy_pk = _validate_integer(
        last_legacy_pk,
        code="legacy_batch_last_pk_invalid",
        minimum=1,
    )
    if last_legacy_pk < first_legacy_pk:
        raise LegacyBatchConflictError("legacy_batch_pk_range_invalid")
    migrated_count = _validate_integer(migrated_count, code="legacy_batch_count_invalid")
    skipped_count = _validate_integer(skipped_count, code="legacy_batch_count_invalid")
    quarantined_count = _validate_integer(quarantined_count, code="legacy_batch_count_invalid")
    source_row_count = migrated_count + skipped_count + quarantined_count
    if source_row_count < 1:
        raise LegacyBatchConflictError("legacy_batch_empty")
    if source_row_count > last_legacy_pk - first_legacy_pk + 1:
        raise LegacyBatchConflictError("legacy_batch_count_exceeds_pk_range")

    scope = ledger._get_run_scope(run_id)
    with ledger._locked_scope(scope):
        run = ledger._get_run(run_id, for_update=True)
        recorder = _persisted_actor(actor)
        ledger._authorize(
            actor=recorder,
            organization=run.organization,
            action=ledger.LedgerAction.RECORD_BATCH,
            authorize=authorize,
        )
        ledger._require_active_run(run)
        if run.accounting_mode != LegacyMigrationRun.AccountingMode.BATCH:
            raise LegacyBatchConflictError("legacy_batch_accounting_mode_required")

        predecessor = None
        if sequence > 1:
            predecessor = (
                LegacyImportBatch.objects.select_for_update()
                .filter(
                    run=run,
                    source_table=source_table,
                    sequence=sequence - 1,
                )
                .first()
            )
            if predecessor is None:
                raise LegacyBatchConflictError("legacy_batch_predecessor_missing")
            if predecessor.entity_type != entity_type:
                raise LegacyBatchConflictError("legacy_batch_entity_type_changed")
            if predecessor.contract_fingerprint != contract_fingerprint:
                raise LegacyBatchConflictError("legacy_batch_contract_changed")
            if first_legacy_pk <= predecessor.last_legacy_pk:
                raise LegacyBatchConflictError("legacy_batch_pk_overlap")
        elif (
            LegacyImportBatch.objects.select_for_update()
            .filter(
                run=run,
                source_table=source_table,
                sequence__lt=sequence,
            )
            .exists()
        ):
            raise LegacyBatchConflictError("legacy_batch_sequence_conflict")

        previous_chain_digest = predecessor.chain_digest if predecessor else ""
        values = {
            "source_table": source_table,
            "entity_type": entity_type,
            "sequence": sequence,
            "first_legacy_pk": first_legacy_pk,
            "last_legacy_pk": last_legacy_pk,
            "source_row_count": source_row_count,
            "migrated_count": migrated_count,
            "skipped_count": skipped_count,
            "quarantined_count": quarantined_count,
            "contract_fingerprint": contract_fingerprint,
            "source_digest": source_digest,
            "classification_digest": classification_digest,
            "target_digest": target_digest,
            "previous_chain_digest": previous_chain_digest,
        }
        values["chain_digest"] = _chain_digest(run=run, values=values)
        expected = values

        existing = (
            LegacyImportBatch.objects.select_for_update()
            .filter(
                run=run,
                source_table=source_table,
                sequence=sequence,
            )
            .first()
        )
        if existing is not None:
            if _batch_snapshot(existing) == expected:
                return existing
            raise LegacyBatchConflictError("legacy_batch_retry_conflict")

        if LegacyImportBatch.objects.filter(
            run=run,
            source_table=source_table,
            sequence__gt=sequence,
        ).exists():
            raise LegacyBatchConflictError("legacy_batch_sequence_conflict")

        batch = LegacyImportBatch(
            organization=run.organization,
            run=run,
            recorded_by=recorder,
            **values,
        )
        try:
            batch.full_clean(validate_constraints=True)
            batch.save(force_insert=True)
        except (IntegrityError, ValidationError):
            raise LegacyBatchConflictError("legacy_batch_validation_failed") from None
        return batch


def classified_batch_counts(run: LegacyMigrationRun) -> BatchCounts | None:
    """Batch mode istifadə olunmayıbsa ``None``, əks halda aggregate qaytar."""

    queryset = LegacyImportBatch.objects.filter(run=run)
    if not queryset.exists():
        return None
    totals = queryset.aggregate(
        migrated=Sum("migrated_count"),
        skipped=Sum("skipped_count"),
        quarantined=Sum("quarantined_count"),
    )
    return BatchCounts(
        migrated=int(totals["migrated"] or 0),
        skipped=int(totals["skipped"] or 0),
        quarantined=int(totals["quarantined"] or 0),
    )


def verify_batch_chains(run: LegacyMigrationRun) -> None:
    """Terminal keçiddən əvvəl bütün zənciri Python-da da yenidən hesabla."""

    previous_by_scope: dict[str, LegacyImportBatch] = {}
    batches = LegacyImportBatch.objects.filter(run=run).order_by(
        "source_table",
        "entity_type",
        "sequence",
    )
    for batch in batches:
        scope = batch.source_table
        predecessor = previous_by_scope.get(scope)
        expected_sequence = 1 if predecessor is None else predecessor.sequence + 1
        expected_previous = "" if predecessor is None else predecessor.chain_digest
        if (
            batch.sequence != expected_sequence
            or batch.previous_chain_digest != expected_previous
            or (predecessor is not None and batch.first_legacy_pk <= predecessor.last_legacy_pk)
            or (predecessor is not None and batch.entity_type != predecessor.entity_type)
            or (predecessor is not None and batch.contract_fingerprint != predecessor.contract_fingerprint)
        ):
            raise LegacyBatchConflictError("legacy_batch_chain_invalid")
        values = _batch_snapshot(batch)
        if batch.chain_digest != _chain_digest(run=run, values=values):
            raise LegacyBatchConflictError("legacy_batch_digest_invalid")
        previous_by_scope[scope] = batch


__all__ = [
    "BatchCounts",
    "LegacyBatchConflictError",
    "LegacyBatchError",
    "classified_batch_counts",
    "record_batch",
    "verify_batch_chains",
]
