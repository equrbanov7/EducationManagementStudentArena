"""Phase C evidence: batch-chain reconciliation, histograms and provenance.

Every check here recomputes the accounting from a source that is independent of
the one it is compared against: the hash chain is replayed in Python, the batch
aggregate is compared with the run's declared source rows and per-table plan
expectations, and the per-state totals are cross-checked against the immutable
observations.  ``finish_run`` re-runs the same gates; these exist only so the
orchestrator can emit a precise failure code first.

``phase_report_from_ledger`` rebuilds a phase report purely from the sealed
batch rows, which is what ``--emit-report-only`` regenerates a report from.
A phase that accounts for no source table (``source_tables = ()``) owns no
batch chain at all, so its report is rebuilt from its immutable observations
instead; see ``_derived_phase_report_from_ledger``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from django.db.models import Count, Sum

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue, LegacyMigrationRun

from .batch_accounting import LegacyBatchError, classified_batch_counts, verify_batch_chains
from .rehearsal_contracts import (
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseBatchRecord,
    PhaseReport,
    RehearsalPhase,
)

# Imported rather than repeated so a future change inside the phase can never
# silently diverge from a regenerated report artifact.
from .rehearsal_identity_phase import _PHASE_DIGEST_NAMESPACE as PHASE_DIGEST_NAMESPACE

_STATES = (
    LegacyEntityMap.State.MIGRATED,
    LegacyEntityMap.State.SKIPPED,
    LegacyEntityMap.State.QUARANTINED,
)
_BLOCKING_SEVERITIES = (
    LegacyMigrationIssue.Severity.ERROR,
    LegacyMigrationIssue.Severity.CRITICAL,
)
_CLOSED_REVIEW_STATUSES = (
    LegacyMigrationIssue.ReviewStatus.RESOLVED,
    LegacyMigrationIssue.ReviewStatus.WAIVED,
)


def _batch_records(run: LegacyMigrationRun, source_table: str) -> list[PhaseBatchRecord]:
    return [
        PhaseBatchRecord(
            source_table=batch.source_table,
            entity_type=batch.entity_type,
            sequence=batch.sequence,
            first_legacy_pk=batch.first_legacy_pk,
            last_legacy_pk=batch.last_legacy_pk,
            migrated_count=batch.migrated_count,
            skipped_count=batch.skipped_count,
            quarantined_count=batch.quarantined_count,
            contract_fingerprint=batch.contract_fingerprint,
            source_digest=batch.source_digest,
            classification_digest=batch.classification_digest,
            target_digest=batch.target_digest,
        )
        for batch in LegacyImportBatch.objects.filter(run=run, source_table=source_table).order_by("sequence")
    ]


def _derived_phase_report_from_ledger(run: LegacyMigrationRun, *, phase: RehearsalPhase, plan) -> PhaseReport:
    """Rebuild a derived phase from its immutable observations (no batch chain).

    Two optional phase attributes are honoured through ``getattr`` so the
    ``RehearsalPhase`` protocol keeps a single mandatory shape:
    ``derived_digest_namespace`` (the chain namespace the phase itself used) and
    ``derived_state_key(state)`` (the token a ledger state is counted under).
    Neither is part of the registry fingerprint: they change how evidence is
    labelled, never what a phase may write.
    """

    namespace = getattr(phase, "derived_digest_namespace", PHASE_DIGEST_NAMESPACE)
    key_for = getattr(phase, "derived_state_key", None)
    # Üçüncü opsional hook (SA-2 ailəsi): ``derived_ledger_sort_key`` fazanın
    # zəncirini yeridiyi sıranı verir.  Defolt rəqəmsal qalır; ``journal_offerings``
    # kimi mətn-açarlı (uniqid) fazalar leksikoqrafik sıra bildirir.  Fingerprint-ə
    # daxil deyil: sübutun ETİKETLƏNMƏSİNİ dəyişir, yazıla bilənləri yox.
    sort_key = getattr(phase, "derived_ledger_sort_key", None)
    if not callable(sort_key):
        sort_key = int
    rows = list(
        run.entity_observations.filter(entity_map__entity_type__in=tuple(phase.entity_types)).values_list(
            "entity_map__legacy_pk",
            "state",
            "source_row_hash",
            "target_model_label",
        )
    )
    try:
        # ``legacy_pk`` is text in the ledger; the phase declares its own order.
        ordered = sorted(rows, key=lambda row: sort_key(row[0]))
    except (TypeError, ValueError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_derived_legacy_pk_invalid") from None
    chain = OrderedDigest(namespace)
    counts: Counter[str] = Counter()
    for legacy_pk, state, row_hash, target_label in ordered:
        chain.advance(legacy_pk, str(state), row_hash, target_label)
        counts[key_for(state) if callable(key_for) else str(state)] += 1
    return PhaseReport(
        phase_key=phase.phase_key,
        order=phase.order,
        source_tables=(),
        declared_source_rows=phase.declared_source_rows(plan),
        observed_source_rows=0,
        batches=(),
        state_counts=dict(counts),
        issue_counts={},
        staged_account_count=0,
        phase_digest=chain.hexdigest(),
    )


def phase_report_from_ledger(run: LegacyMigrationRun, *, phase: RehearsalPhase, plan) -> PhaseReport:
    """Rebuild one phase report from the sealed batch chain, in phase order."""

    if not tuple(phase.source_tables):
        return _derived_phase_report_from_ledger(run, phase=phase, plan=plan)
    records: list[PhaseBatchRecord] = []
    for source_table in phase.source_tables:
        records.extend(_batch_records(run, source_table))
    if not records:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_row_count_mismatch")
    state_counts = {
        str(LegacyEntityMap.State.MIGRATED): sum(record.migrated_count for record in records),
        str(LegacyEntityMap.State.SKIPPED): sum(record.skipped_count for record in records),
        str(LegacyEntityMap.State.QUARANTINED): sum(record.quarantined_count for record in records),
    }
    chain = OrderedDigest(PHASE_DIGEST_NAMESPACE)
    for record in records:
        chain.advance(
            record.source_table,
            str(record.sequence),
            record.source_digest,
            record.classification_digest,
            record.target_digest,
        )
    return PhaseReport(
        phase_key=phase.phase_key,
        order=phase.order,
        source_tables=tuple(phase.source_tables),
        declared_source_rows=phase.declared_source_rows(plan),
        observed_source_rows=sum(state_counts.values()),
        batches=tuple(records),
        state_counts=dict(state_counts),
        # Issue counts are always re-derived from the ledger (SPEC C5), never
        # from a phase pass that may have short-circuited observed rows.
        issue_counts={},
        staged_account_count=state_counts[str(LegacyEntityMap.State.MIGRATED)],
        phase_digest=chain.hexdigest(),
    )


def normalized_phase_report(report: PhaseReport) -> PhaseReport:
    """Coerce ``TextChoices`` state keys to plain text for the report validator.

    A phase counts states with ``LegacyEntityMap.State`` members, which compare
    and hash like their values but are not ``str`` instances by ``type()``.  The
    report module validates strictly by exact type, so the seam normalises here
    instead of loosening that validation.
    """

    return replace(
        report,
        state_counts={str(state): int(count) for state, count in report.state_counts.items()},
    )


def reconcile_run(run: LegacyMigrationRun, *, phases, plan) -> None:
    """C1-C4: replay the chain and cross-check it against the observations."""

    try:
        verify_batch_chains(run)
    except LegacyBatchError:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_chain_invalid") from None
    counts = classified_batch_counts(run)
    if counts is None or counts.source_rows != run.source_row_count:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_reconciliation_mismatch")
    per_table = {
        row["source_table"]: row["total"]
        for row in LegacyImportBatch.objects.filter(run=run)
        .values("source_table")
        .annotate(total=Sum("source_row_count"))
    }
    for phase in phases:
        for source_table in phase.source_tables:
            if per_table.get(source_table, 0) != plan.entry_for(source_table).expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_reconciliation_mismatch")
    # C4 compares the batch aggregate with the observations it accounts for.  A
    # derived target row (one that is 1:1 with an already-accounted source row)
    # carries no batch of its own, so counting it here would guarantee a false
    # mismatch; it stays covered by the emitting phase's own digest chain and by
    # the fingerprint-pinned ``entity_types`` declaration checked just below.
    accounted_types = set(LegacyImportBatch.objects.filter(run=run).values_list("entity_type", flat=True).distinct())
    declared_types = {entity_type for phase in phases for entity_type in phase.entity_types}
    observed = dict.fromkeys(_STATES, 0)
    for row in (
        run.entity_observations.filter(entity_map__entity_type__in=accounted_types)
        .values("state")
        .annotate(total=Count("id"))
    ):
        if row["state"] not in observed:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_observation_count_mismatch")
        observed[row["state"]] = row["total"]
    # Fail closed: nothing may be written under an entity type the attested
    # registry never declared.
    stray = (
        set(
            run.entity_observations.exclude(entity_map__entity_type__in=accounted_types)
            .values_list("entity_map__entity_type", flat=True)
            .distinct()
        )
        - declared_types
    )
    if stray:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_derived_entity_type_unregistered")
    derived = {
        LegacyEntityMap.State.MIGRATED: counts.migrated,
        LegacyEntityMap.State.SKIPPED: counts.skipped,
        LegacyEntityMap.State.QUARANTINED: counts.quarantined,
    }
    if observed != derived:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_observation_count_mismatch")


def issue_evidence(run: LegacyMigrationRun) -> tuple[dict[tuple[str, str], int], int]:
    """C5: the DB-derived issue histogram plus the blocking-issue count."""

    histogram = {
        (row["rule_code"], row["severity"]): row["total"]
        for row in run.issues.values("rule_code", "severity").annotate(total=Count("id"))
    }
    blocking = (
        run.issues.filter(severity__in=_BLOCKING_SEVERITIES).exclude(review_status__in=_CLOSED_REVIEW_STATUSES).count()
    )
    return histogram, blocking


def chain_digest_tips(run: LegacyMigrationRun) -> list[dict[str, str]]:
    """Last chain digest per source table; run-bound, so provenance only."""

    tips: dict[str, str] = {}
    for batch in LegacyImportBatch.objects.filter(run=run).order_by("source_table", "sequence"):
        tips[batch.source_table] = batch.chain_digest
    return [{"last_chain_digest": digest, "source_table": table} for table, digest in sorted(tips.items())]


def provenance_payload(run: LegacyMigrationRun, *, ordinal: int, status: str) -> dict[str, object]:
    """Run-bound facts; deliberately outside the determinism digest (SPEC 13.2)."""

    return {
        "batch_chain_digests": chain_digest_tips(run),
        "failure_code": run.failure_code,
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "organization_id": str(run.organization_id),
        "rehearsal_ordinal": ordinal,
        "run_id": str(run.pk),
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "status": status,
    }


__all__ = [
    "chain_digest_tips",
    "normalized_phase_report",
    "issue_evidence",
    "phase_report_from_ledger",
    "provenance_payload",
    "reconcile_run",
]
