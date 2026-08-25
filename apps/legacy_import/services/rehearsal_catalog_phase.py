"""Phase: ``academic_catalog`` — lessons, curricula and their plan rows.

The cohort is classified in one pass by ``rehearsal_catalog_source`` and every
target is written by ``rehearsal_catalog_targets``; this module owns the batch
accounting.  The three tables are ONE derivation unit (E-1): ``Subject.ects``
comes from ``curricula_plan.kredit`` and ``Curriculum.admission_year`` comes
from the ``groups`` rows that reference the curriculum, so splitting them into
two phases would force a target round-trip for no gain.

Targets are materialised in DEPENDENCY order — subjects, then curricula, then
the plan rows that need both — while the batch chain is always sealed in
strictly ascending ``legacy_pk`` order per source table, so the chain never sees
creation order.  A resumed attempt short-circuits on the recorded observation
and replays every sealed batch, so drift surfaces as
``legacy_rehearsal_batch_replay_mismatch``.

No target primary key ever enters a digest: ``Subject.id``, ``Curriculum.id``
and ``CurriculumSubject.id`` are per-run random UUIDs.  The ``Program`` rows this
phase resolves against are read from THIS run's ``speciality_program`` maps, so
a catalogue run can never silently bind itself to a foreign run's targets.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, fields
from types import MappingProxyType

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyImportBatch

from .batch_accounting import record_batch
from .field_contracts import CURRICULUM_CATALOG_FIELDS, CURRICULUM_PLAN_FIELDS, LESSON_CATALOG_FIELDS
from .rehearsal_catalog_source import build_catalog_cohort
from .rehearsal_catalog_targets import (  # noqa: F401 — §3.9 re-exports
    CURRICULUM_ENTITY_TYPE,
    ISSUE_SEVERITY,
    PLAN_ROW_ENTITY_TYPE,
    SUBJECT_ENTITY_TYPE,
    TargetRef,
    materialise_curricula,
    materialise_plan_rows,
    materialise_subjects,
    probe_cancellation,
    severity_for,
)
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseBatchRecord,
    PhaseReport,
    RehearsalContext,
)

# Imported rather than repeated: ``phase_report_from_ledger`` rebuilds every
# batch-accounted phase under this one namespace, so a local copy that drifted
# would silently break ``--emit-report-only``.
from .rehearsal_identity_phase import _PHASE_DIGEST_NAMESPACE as PHASE_DIGEST_NAMESPACE
from .rehearsal_structure_phase import PROGRAM_ENTITY_TYPE, STRUCTURE_PHASE_KEY

CATALOG_PHASE_KEY = "academic_catalog"
CATALOG_PHASE_ORDER = 12  # after structure (10, supplies Program), before identity (20)
REQUIRED_PHASE_KEYS = frozenset({STRUCTURE_PHASE_KEY})
_SOURCE_DIGEST_NAMESPACE = "legacy-rehearsal-catalog-source-v1"
_CLASSIFICATION_DIGEST_NAMESPACE = "legacy-rehearsal-catalog-classification-v1"
_TARGET_DIGEST_NAMESPACE = "legacy-rehearsal-catalog-target-v1"
_INDEX_AMBIGUOUS = "legacy_rehearsal_catalog_index_ambiguous"
_STATE = LegacyEntityMap.State
# Every sealed batch value except its (source_table, sequence) lookup key.
_REPLAY_FIELDS = tuple(item.name for item in fields(PhaseBatchRecord) if item.name not in ("source_table", "sequence"))
_ACCOUNTED_TABLES = (
    ("lessons", SUBJECT_ENTITY_TYPE, LESSON_CATALOG_FIELDS),
    ("curricula", CURRICULUM_ENTITY_TYPE, CURRICULUM_CATALOG_FIELDS),
    ("curricula_plan", PLAN_ROW_ENTITY_TYPE, CURRICULUM_PLAN_FIELDS),
)


def _chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _recorded_batches(run_id, source_table: str) -> dict[int, LegacyImportBatch]:
    return {b.sequence: b for b in LegacyImportBatch.objects.filter(run_id=run_id, source_table=source_table)}


def _assert_batch_matches(existing: LegacyImportBatch, record: PhaseBatchRecord) -> None:
    if any(getattr(existing, name) != getattr(record, name) for name in _REPLAY_FIELDS):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_replay_mismatch")


def program_map_index(context: RehearsalContext) -> dict[str, TargetRef]:
    """``"{speciality_id}:{degree}"`` → the program THIS run derived (§3.9)."""

    maps = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            state=_STATE.MIGRATED,
            entity_map__entity_type=PROGRAM_ENTITY_TYPE,
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    program_model = django_apps.get_model("registrar", "Program")
    codes = {
        str(row["id"]): str(row["code"])
        for row in program_model.objects.filter(
            organization=context.organization, pk__in=[target_pk for _legacy_pk, target_pk in maps]
        ).values("id", "code")
    }
    index: dict[str, TargetRef] = {}
    claimed: set[str] = set()
    for legacy_pk, target_pk in maps:
        code = codes.get(str(target_pk))
        if code is None:
            continue  # a map whose target this tenant does not own resolves nothing
        # Two ledger keys pointing at one Program makes the lookup a coin toss.
        if legacy_pk in index or str(target_pk) in claimed:
            raise LegacyRehearsalEvidenceError(_INDEX_AMBIGUOUS)
        claimed.add(str(target_pk))
        index[legacy_pk] = TargetRef(str(target_pk), code)
    return index


def _window_record(*, contract, entity_type, source_table, sequence, window, state_counts) -> PhaseBatchRecord:
    """Seal one window of already-materialised rows into a batch record."""

    source_chain = OrderedDigest(_SOURCE_DIGEST_NAMESPACE)
    classification_chain = OrderedDigest(_CLASSIFICATION_DIGEST_NAMESPACE)
    target_chain = OrderedDigest(_TARGET_DIGEST_NAMESPACE)
    window_counts: Counter[str] = Counter()
    for item in window:
        legacy_pk_text = str(item.legacy_pk)
        window_counts[item.state] += 1
        state_counts[item.state] += 1
        source_chain.advance(legacy_pk_text, item.source_row_hash)
        classification_chain.advance(legacy_pk_text, item.state, item.decision_token)
        target_chain.advance(legacy_pk_text, item.target_model_label, item.semantic_digest)
    return PhaseBatchRecord(
        source_table=source_table,
        entity_type=entity_type,
        sequence=sequence,
        first_legacy_pk=window[0].legacy_pk,
        last_legacy_pk=window[-1].legacy_pk,
        migrated_count=window_counts[_STATE.MIGRATED],
        skipped_count=window_counts[_STATE.SKIPPED],
        quarantined_count=window_counts[_STATE.QUARANTINED],
        contract_fingerprint=contract.fingerprint,
        source_digest=source_chain.hexdigest(),
        classification_digest=classification_chain.hexdigest(),
        target_digest=target_chain.hexdigest(),
    )


class AcademicCatalogPhase:
    """The subject and curriculum catalogue, accounted row by row."""

    phase_key = CATALOG_PHASE_KEY
    order = CATALOG_PHASE_ORDER
    source_tables = ("lessons", "curricula", "curricula_plan")
    entity_types = (SUBJECT_ENTITY_TYPE, CURRICULUM_ENTITY_TYPE, PLAN_ROW_ENTITY_TYPE)

    def declared_source_rows(self, plan) -> int:
        return sum(plan.entry_for(source_table).expected_rows for source_table in self.source_tables)

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, not Config: the orchestrator finishes the run FAILED with
            # this precise code instead of leaving it RUNNING.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        programs = program_map_index(context)
        cohort = build_catalog_cohort(context)
        issue_counts: Counter[tuple[str, str]] = Counter()
        subjects: dict[int, TargetRef] = {}
        curricula: dict[int, TargetRef] = {}
        rows_by_table = {
            "lessons": materialise_subjects(context, cohort, resolved=subjects, issue_counts=issue_counts),
            "curricula": materialise_curricula(
                context,
                cohort,
                programs=programs,
                resolved=curricula,
                claimed_keys=set(),
                issue_counts=issue_counts,
            ),
            "curricula_plan": materialise_plan_rows(
                context, cohort, curricula=curricula, subjects=subjects, issue_counts=issue_counts
            ),
        }

        state_counts: Counter[str] = Counter({_STATE.MIGRATED: 0, _STATE.SKIPPED: 0, _STATE.QUARANTINED: 0})
        batches: list[PhaseBatchRecord] = []
        for source_table, entity_type, contract in _ACCOUNTED_TABLES:
            recorded = _recorded_batches(context.run_id, source_table)
            for sequence, window in enumerate(_chunked(rows_by_table[source_table], context.policy.batch_rows), 1):
                probe_cancellation(context)
                record = _window_record(
                    contract=contract,
                    entity_type=entity_type,
                    source_table=source_table,
                    sequence=sequence,
                    window=window,
                    state_counts=state_counts,
                )
                existing = recorded.get(sequence)
                if existing is not None:
                    _assert_batch_matches(existing, record)
                record_batch(run_id=context.run_id, actor=context.actor, authorize=context.authorize, **asdict(record))
                batches.append(record)
                context.stdout_note(f"{CATALOG_PHASE_KEY}.{source_table}.batch.{sequence}")

        phase_chain = OrderedDigest(PHASE_DIGEST_NAMESPACE)
        for record in batches:
            phase_chain.advance(
                record.source_table,
                str(record.sequence),
                record.source_digest,
                record.classification_digest,
                record.target_digest,
            )
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=self.source_tables,
            declared_source_rows=self.declared_source_rows(context.plan),
            observed_source_rows=sum(len(rows) for rows in rows_by_table.values()),
            batches=tuple(batches),
            state_counts=MappingProxyType(dict(state_counts)),
            issue_counts=MappingProxyType(dict(issue_counts)),
            # ``phase_report_from_ledger`` rebuilds this field as the migrated
            # count and the report digest covers it, so the live pass must report
            # the same number even though no ACCOUNT is staged here.
            staged_account_count=state_counts[_STATE.MIGRATED],
            phase_digest=phase_chain.hexdigest(),
        )
