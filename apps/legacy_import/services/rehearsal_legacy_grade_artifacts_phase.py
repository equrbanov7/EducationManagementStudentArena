"""Phase 49: çap olunmuş köhnə bal vərəqlərini immutable arxivə köçür."""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationRun

from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_batch import Decision, JournalBatchWriter
from .rehearsal_legacy_grade_artifacts import (
    ARTIFACT_ENTITY_TYPE,
    LEGACY_GRADE_ARTIFACT_MODEL_LABEL,
    LegacyGradeArtifactMaterialiser,
    artifact_materialization_digest,
    artifact_requests,
    artifact_rows,
)
from .rehearsal_legacy_grade_facts_phase import LEGACY_GRADE_FACTS_PHASE_KEY
from .rehearsal_legacy_grade_facts_source import SOURCE_SYSTEM
from .rehearsal_legacy_grade_facts_target import severity_for
from .rehearsal_structure_phase import probe_cancellation

LEGACY_GRADE_ARTIFACTS_PHASE_KEY = "legacy_grade_artifacts"
LEGACY_GRADE_ARTIFACTS_PHASE_ORDER = 49
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-grade-artifacts-v1"
REQUIRED_PHASE_KEYS = frozenset({LEGACY_GRADE_FACTS_PHASE_KEY})

_STATE = LegacyEntityMap.State
DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "legacy_grade_artifacts_materialised",
        _STATE.SKIPPED: "legacy_grade_artifacts_skipped",
        _STATE.QUARANTINED: "legacy_grade_artifacts_unresolved",
    }
)


def recorded_decisions(context) -> dict[str, tuple[str, str, str]]:
    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id,
        entity_map__entity_type=ARTIFACT_ENTITY_TYPE,
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {legacy_pk: (state, digest, label) for legacy_pk, state, digest, label in rows.iterator(chunk_size=10_000)}


class LegacyGradeArtifactsPhase:
    """Hər ``balvereqi_logs`` export-unu itkisiz, sıxılmış sübuta çevir."""

    phase_key = LEGACY_GRADE_ARTIFACTS_PHASE_KEY
    order = LEGACY_GRADE_ARTIFACTS_PHASE_ORDER
    source_tables = ()
    entity_types = (ARTIFACT_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        run = LegacyMigrationRun.objects.only("snapshot_sha256", "transform_version").get(pk=context.run_id)
        recorded = recorded_decisions(context)
        materialiser = LegacyGradeArtifactMaterialiser()
        writer = JournalBatchWriter(
            context,
            entity_type=ARTIFACT_ENTITY_TYPE,
            source_table="balvereqi_logs",
            severity_for=severity_for,
            materialiser=materialiser,
        )
        decisions: list[tuple[str, str, str, str]] = []

        for request in artifact_requests(context, rows=artifact_rows(context)):
            probe_cancellation(context)
            previous = recorded.get(request.seal_key)
            if previous is not None:
                decisions.append((request.seal_key, *previous))
                continue
            natural_key = (SOURCE_SYSTEM, request.source_table, request.source_pk)
            payload = {
                **request.payload,
                "source_snapshot_sha256": run.snapshot_sha256,
                "source_row_hash": request.source_row_hash,
                "transform_version": run.transform_version,
            }
            digest = artifact_materialization_digest(
                natural_key=natural_key,
                source_row_hash=request.source_row_hash,
                payload=payload,
            )
            payload["materialization_digest"] = digest
            materialiser.stage(natural_key, payload)
            writer.add(
                Decision(
                    seal_key=request.seal_key,
                    state=_STATE.MIGRATED,
                    digest=digest,
                    label=LEGACY_GRADE_ARTIFACT_MODEL_LABEL,
                    natural_key=natural_key,
                )
            )
            decisions.append(
                (
                    request.seal_key,
                    str(_STATE.MIGRATED),
                    digest,
                    LEGACY_GRADE_ARTIFACT_MODEL_LABEL,
                )
            )
        writer.flush()

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)
            state_counts[self.derived_state_key(state)] += 1
        context.stdout_note(f"{self.phase_key}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(writer.issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "LEGACY_GRADE_ARTIFACTS_PHASE_KEY",
    "LEGACY_GRADE_ARTIFACTS_PHASE_ORDER",
    "LegacyGradeArtifactsPhase",
]
