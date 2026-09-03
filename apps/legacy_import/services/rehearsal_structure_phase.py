"""Phase: ``academic_structure`` — departments, speciality (+ programs), groups.

The cohort is classified in one pass by ``rehearsal_structure_source`` and every
target is written by ``rehearsal_structure_targets``; this module owns the batch
accounting.  Targets are materialised in DEPENDENCY order (a department's parent
may carry a HIGHER legacy id, so the tree is topologically sorted first), while
the batch chain is always sealed in strictly ascending ``legacy_pk`` order per
source table — the chain therefore never sees creation order.  A resumed attempt
short-circuits on the recorded observation and replays every sealed batch, so
drift surfaces as ``legacy_rehearsal_batch_replay_mismatch``.

A speciality produces TWO map rows: ``speciality_unit`` (batch-accounted, 1:1
with the source row) and one derived ``speciality_program`` per observed degree
level.  The derived rows carry no batch of their own — they are folded into the
speciality's ``target_digest`` instead, which is what keeps them under cross-run
comparison (SA-1).  No target primary key ever enters a digest: ``OrgUnit.id``
and ``OrgUnit.path`` are per-run random UUIDs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, fields
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch
from core.constants import OrgUnitType

from .batch_accounting import record_batch
from .field_contracts import DEPARTMENT_STRUCTURE_FIELDS, GROUP_STRUCTURE_FIELDS, SPECIALITY_STRUCTURE_FIELDS
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
from .rehearsal_structure_source import build_structure_cohort
from .rehearsal_structure_targets import (  # noqa: F401 — §3.10 re-exports
    DEPARTMENT_ENTITY_TYPE,
    GROUP_ENTITY_TYPE,
    ISSUE_SEVERITY,
    MAX_DEPARTMENT_DEPTH,
    PROGRAM_ENTITY_TYPE,
    SPECIALITY_ENTITY_TYPE,
    Resolved,
    materialise_departments,
    materialise_groups,
    materialise_specialities,
    ordered_departments,
    probe_cancellation,
    severity_for,
)

STRUCTURE_PHASE_KEY = "academic_structure"
STRUCTURE_PHASE_ORDER = 10  # table_plan._DOMAIN_PHASES["academic_structure"]
_SOURCE_DIGEST_NAMESPACE = "legacy-rehearsal-structure-source-v1"
_CLASSIFICATION_DIGEST_NAMESPACE = "legacy-rehearsal-structure-classification-v1"
_TARGET_DIGEST_NAMESPACE = "legacy-rehearsal-structure-target-v1"
_STATE = LegacyEntityMap.State
# Every sealed batch value except its (source_table, sequence) lookup key.
_REPLAY_FIELDS = tuple(item.name for item in fields(PhaseBatchRecord) if item.name not in ("source_table", "sequence"))
_ACCOUNTED_TABLES = (
    ("departments", DEPARTMENT_ENTITY_TYPE, DEPARTMENT_STRUCTURE_FIELDS),
    ("speciality", SPECIALITY_ENTITY_TYPE, SPECIALITY_STRUCTURE_FIELDS),
    ("groups", GROUP_ENTITY_TYPE, GROUP_STRUCTURE_FIELDS),
)


def _chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _assert_university_organization(context: RehearsalContext) -> None:
    """Only a university tenant may own faculty/chair/specialty/group units."""

    from apps.organizations.unit_types import validate_unit_type_for_org

    if validate_unit_type_for_org(getattr(context.organization, "org_type", None), OrgUnitType.FACULTY) is not True:
        raise LegacyRehearsalConfigError("legacy_rehearsal_organization_type_unsupported")


def _recorded_batches(run_id, source_table: str) -> dict[int, LegacyImportBatch]:
    return {b.sequence: b for b in LegacyImportBatch.objects.filter(run_id=run_id, source_table=source_table)}


def _assert_batch_matches(existing: LegacyImportBatch, record: PhaseBatchRecord) -> None:
    if any(getattr(existing, name) != getattr(record, name) for name in _REPLAY_FIELDS):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_replay_mismatch")


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


class AcademicStructurePhase:
    """The academic tree and its program catalogue, accounted row by row."""

    phase_key = STRUCTURE_PHASE_KEY
    order = STRUCTURE_PHASE_ORDER
    source_tables = ("departments", "speciality", "groups")
    entity_types = (DEPARTMENT_ENTITY_TYPE, SPECIALITY_ENTITY_TYPE, PROGRAM_ENTITY_TYPE, GROUP_ENTITY_TYPE)

    def declared_source_rows(self, plan) -> int:
        return sum(plan.entry_for(source_table).expected_rows for source_table in self.source_tables)

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        _assert_university_organization(context)
        cohort = build_structure_cohort(context)

        issue_counts: Counter[tuple[str, str]] = Counter()
        department_units: dict[int, Resolved] = {}
        speciality_units: dict[int, Resolved] = {}
        rows_by_table = {
            "departments": materialise_departments(
                context, cohort, resolved=department_units, issue_counts=issue_counts
            ),
            "speciality": materialise_specialities(
                context, cohort, departments=department_units, resolved=speciality_units, issue_counts=issue_counts
            ),
            "groups": materialise_groups(
                context, cohort, departments=department_units, specialities=speciality_units, issue_counts=issue_counts
            ),
        }

        state_counts: Counter[str] = Counter({_STATE.MIGRATED: 0, _STATE.SKIPPED: 0, _STATE.QUARANTINED: 0})
        batches: list[PhaseBatchRecord] = []
        for source_table, entity_type, contract in _ACCOUNTED_TABLES:
            recorded = _recorded_batches(context.run_id, source_table)
            windows = _chunked(rows_by_table[source_table], context.policy.batch_rows)
            for sequence, window in enumerate(windows, start=1):
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
                context.stdout_note(f"{STRUCTURE_PHASE_KEY}.{source_table}.batch.{sequence}")

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
