"""Phase 47: bütün köhnə yekun/imtahan faktlarını clamp-siz arxivləşdir."""

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
from .rehearsal_journal_enrollments_phase import (
    JOURNAL_ENROLLMENT_ENTITY_TYPE,
    JOURNAL_ENROLLMENTS_PHASE_KEY,
)
from .rehearsal_journal_finals_phase import JOURNAL_FINALS_PHASE_KEY
from .rehearsal_journal_lock_phase import JOURNAL_LOCK_PHASE_KEY
from .rehearsal_journal_points_source import migrated_index
from .rehearsal_legacy_grade_facts_source import (
    POINT_STREAMS,
    SOURCE_SYSTEM,
    attempt_enrollment_candidates,
    attempt_requests,
    attempt_rows,
    group_mismatch_keys,
    journal_metadata,
    point_requests,
    summary_conflicts,
    summary_requests,
    yekun_evidence_rows,
)
from .rehearsal_legacy_grade_facts_target import (
    LEGACY_GRADE_FACT_MODEL_LABEL,
    LegacyGradeFactMaterialiser,
    fact_materialization_digest,
    severity_for,
)
from .rehearsal_structure_phase import probe_cancellation

LEGACY_GRADE_FACTS_PHASE_KEY = "legacy_grade_facts"
LEGACY_GRADE_FACTS_PHASE_ORDER = 47
LEGACY_GRADE_FACT_ENTITY_TYPE = "legacy_grade_fact"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-grade-facts-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_ENROLLMENTS_PHASE_KEY, JOURNAL_FINALS_PHASE_KEY, JOURNAL_LOCK_PHASE_KEY})

_STATE = LegacyEntityMap.State
DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "legacy_grade_facts_materialised",
        _STATE.SKIPPED: "legacy_grade_facts_skipped",
        _STATE.QUARANTINED: "legacy_grade_facts_unresolved",
    }
)


def recorded_decisions(context) -> dict[str, tuple[str, str, str]]:
    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id,
        entity_map__entity_type=LEGACY_GRADE_FACT_ENTITY_TYPE,
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {legacy_pk: (state, digest, label) for legacy_pk, state, digest, label in rows.iterator(chunk_size=10_000)}


class LegacyGradeFactsPhase:
    """Xam grade evidence hər halda MIGRATED olur; mapping problemi metadata-dır."""

    phase_key = LEGACY_GRADE_FACTS_PHASE_KEY
    order = LEGACY_GRADE_FACTS_PHASE_ORDER
    source_tables = ()
    entity_types = (LEGACY_GRADE_FACT_ENTITY_TYPE,)
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
        journals_by_id, journals_by_uniqid = journal_metadata(context)
        enrollments = migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE)
        mismatches = group_mismatch_keys(context)
        summary_rows = list(yekun_evidence_rows(context))
        conflicts = summary_conflicts(summary_rows, journals_by_id=journals_by_id, enrollments=enrollments)

        recorded = recorded_decisions(context)
        materialiser = LegacyGradeFactMaterialiser()
        decisions: list[tuple[str, str, str, str]] = []
        issue_counts: Counter[tuple[str, str]] = Counter()

        summary_writer = self._writer(context, "yekun", materialiser)
        for request in summary_requests(
            context,
            rows=summary_rows,
            journals_by_id=journals_by_id,
            enrollments=enrollments,
            mismatches=mismatches,
            conflicting_enrollments=conflicts,
        ):
            probe_cancellation(context)
            self._record(
                request=request,
                writer=summary_writer,
                materialiser=materialiser,
                recorded=recorded,
                decisions=decisions,
                snapshot_sha256=run.snapshot_sha256,
                transform_version=run.transform_version,
            )
        summary_writer.flush()
        issue_counts.update(summary_writer.issue_counts)

        for stream, contract, is_archive in POINT_STREAMS:
            writer = self._writer(context, contract.source_table, materialiser)
            for request in point_requests(
                context,
                rows=stream(context),
                contract=contract,
                is_archive=is_archive,
                journals_by_uniqid=journals_by_uniqid,
                enrollments=enrollments,
                mismatches=mismatches,
            ):
                probe_cancellation(context)
                self._record(
                    request=request,
                    writer=writer,
                    materialiser=materialiser,
                    recorded=recorded,
                    decisions=decisions,
                    snapshot_sha256=run.snapshot_sha256,
                    transform_version=run.transform_version,
                )
            writer.flush()
            issue_counts.update(writer.issue_counts)

        candidates = attempt_enrollment_candidates(journals_by_uniqid, enrollments)
        attempt_writer = self._writer(context, "imthngrscxsblr", materialiser)
        for request in attempt_requests(
            context,
            rows=attempt_rows(context),
            candidates=candidates,
            mismatches=mismatches,
        ):
            probe_cancellation(context)
            self._record(
                request=request,
                writer=attempt_writer,
                materialiser=materialiser,
                recorded=recorded,
                decisions=decisions,
                snapshot_sha256=run.snapshot_sha256,
                transform_version=run.transform_version,
            )
        attempt_writer.flush()
        issue_counts.update(attempt_writer.issue_counts)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)
            state_counts[self.derived_state_key(state)] += 1
        context.stdout_note(f"{LEGACY_GRADE_FACTS_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    @staticmethod
    def _writer(context, source_table, materialiser):
        return JournalBatchWriter(
            context,
            entity_type=LEGACY_GRADE_FACT_ENTITY_TYPE,
            source_table=source_table,
            severity_for=severity_for,
            materialiser=materialiser,
        )

    @staticmethod
    def _record(*, request, writer, materialiser, recorded, decisions, snapshot_sha256, transform_version) -> None:
        previous = recorded.get(request.seal_key)
        if previous is not None:
            decisions.append((request.seal_key, *previous))
            return
        natural_key = (SOURCE_SYSTEM, request.source_table, request.source_pk)
        payload = {
            **request.payload,
            "source_snapshot_sha256": snapshot_sha256,
            "source_row_hash": request.source_row_hash,
            "transform_version": transform_version,
            "requires_exam_center_review": True,
        }
        digest = fact_materialization_digest(
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
                label=LEGACY_GRADE_FACT_MODEL_LABEL,
                rule_codes=request.rule_codes,
                natural_key=natural_key,
            )
        )
        decisions.append((request.seal_key, str(_STATE.MIGRATED), digest, LEGACY_GRADE_FACT_MODEL_LABEL))


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "LEGACY_GRADE_FACTS_PHASE_KEY",
    "LEGACY_GRADE_FACTS_PHASE_ORDER",
    "LEGACY_GRADE_FACT_ENTITY_TYPE",
    "LegacyGradeFactsPhase",
]
