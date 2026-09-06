"""Append-only J12 evidence for losing journal target-key values.

This is the conflict-evidence half of ``rehearsal_lesson_recovery_targets``.
It is separate so the public target facade stays below the module-size cap.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_FIELDS
from .rehearsal_contracts import SOURCE_SYSTEM, LegacyRehearsalEvidenceError
from .rehearsal_journal_points_source import POINT_ARCHIVE_TABLE, POINT_SOURCE_TABLE
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer
from .rehearsal_legacy_grade_facts_target import (
    LEGACY_GRADE_FACT_MODEL_LABEL,
    fact_materialization_digest,
)

MARK_CONFLICT_ENTITY_TYPE = "legacy_mark_conflict"
CONFLICT_EVIDENCE_RULE_CODE = "legacy_mark_conflict_evidence"
FACT_CONFLICT_ISSUE_CODE = "legacy_grade_fact_conflict"
CONFLICT_ALREADY_EVIDENCED_RULE_CODE = "legacy_mark_conflict_already_evidenced"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity
_FACT_BATCH = 500

CONFLICT_ISSUE_SEVERITY = MappingProxyType(
    {
        CONFLICT_EVIDENCE_RULE_CODE: _SEVERITY.WARNING,
        CONFLICT_ALREADY_EVIDENCED_RULE_CODE: _SEVERITY.INFO,
        "legacy_journal_mark_recovered_target_conflict": _SEVERITY.WARNING,
        "legacy_journal_component_target_conflict": _SEVERITY.WARNING,
    }
)

MARK_CONFLICT_SEALER = JournalSealer(
    entity_type=MARK_CONFLICT_ENTITY_TYPE,
    source_table=POINT_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-mark-conflict-derivation-v2\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=CONFLICT_ISSUE_SEVERITY,
)


def conflict_seal_key(*, from_archive: bool, legacy_pk: int) -> str:
    """Uduzan xananın möhürü — mənbə sətrinin özü (cədvəl + pk)."""

    return f"cf:{'a' if from_archive else 'p'}:{legacy_pk}"


@dataclass(frozen=True)
class _PendingSeal:
    seal_key: str
    digest: str
    state: str
    label: str
    rule_codes: tuple[str, ...]
    natural_key: tuple | None = None


@dataclass(frozen=True)
class ConflictFact:
    """Hədəf açarı toqquşmasında UDUZAN xananın dəyişməz sübutu."""

    seal_key: str
    source_table: str
    legacy_pk: int
    source_row_hash: str
    uniqid: str
    student_ref: str
    enrollment_pk: str
    month_id: str
    source_lesson_ref: str
    losing_text: str
    winning_text: str
    issue_code: str

    def digest_parts(self) -> tuple[str, ...]:
        return (
            f"journal={self.uniqid}",
            f"student={self.student_ref}",
            f"month={self.month_id}",
            f"lost={self.losing_text}",
            f"kept={self.winning_text}",
            f"issue={self.issue_code}",
        )


class ConflictFactWriter:
    """Insert losing values as immutable grade facts and seal their targets."""

    __slots__ = (
        "_batch_rows",
        "_context",
        "_pending",
        "_run",
        "already",
        "issue_counts",
        "recorded",
        "sealed",
        "written",
    )

    def __init__(self, context, *, run, recorded=None, batch_rows: int = _FACT_BATCH) -> None:
        self._context = context
        self._run = run
        self.recorded = dict(recorded or {})
        self._batch_rows = max(1, int(batch_rows))
        self._pending: list[ConflictFact] = []
        self.issue_counts: Counter = Counter()
        self.sealed: list = []
        self.written = 0
        self.already = 0

    def add(self, fact: ConflictFact) -> None:
        previous = self.recorded.get(fact.seal_key)
        if previous is not None:
            self.sealed.append((fact.seal_key, previous))
            return
        self._pending.append(fact)
        if len(self._pending) >= self._batch_rows:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._deduplicated(self._pending), []
        model = django_apps.get_model("registrar", "LegacyGradeFact")
        created: dict[tuple[str, int], object] = {}
        already = 0
        batch_issue_counts: Counter = Counter()
        try:
            with transaction.atomic():
                existing = self._existing(model, batch)
                target_pks: dict[tuple[str, int], str] = {}
                entries: list[_PendingSeal] = []
                for fact in batch:
                    key = (fact.source_table, fact.legacy_pk)
                    payload = self._payload(fact)
                    digest = fact_materialization_digest(
                        natural_key=(SOURCE_SYSTEM, fact.source_table, fact.legacy_pk),
                        source_row_hash=fact.source_row_hash,
                        payload=payload,
                    )
                    row = existing.get(key)
                    if row is not None:
                        self._assert_same_evidence(row, fact, expected_digest=digest)
                        already += 1
                        target_pks[key] = str(row.pk)
                    else:
                        created[key] = model(
                            organization=self._context.organization,
                            source_system=SOURCE_SYSTEM,
                            source_table=fact.source_table,
                            source_pk=fact.legacy_pk,
                            materialization_digest=digest,
                            **payload,
                        )
                    entries.append(self._entry(fact, digest=digest, natural_key=key))
                if created:
                    model.objects.bulk_create(list(created.values()))
                    target_pks.update({key: str(row.pk) for key, row in created.items()})
                resolved = self._seal(entries, target_pks, issue_counts=batch_issue_counts)
        except Exception:
            self._pending = batch + self._pending
            raise
        self.written += len(created)
        self.already += already
        self.issue_counts.update(batch_issue_counts)
        self.sealed.extend(resolved)

    @staticmethod
    def _deduplicated(batch) -> list[ConflictFact]:
        unique: dict[tuple[str, int], ConflictFact] = {}
        for fact in batch:
            key = (fact.source_table, fact.legacy_pk)
            previous = unique.get(key)
            if previous is not None and previous != fact:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_conflict_fact_conflict")
            unique[key] = fact
        return list(unique.values())

    def _existing(self, model, batch) -> dict[tuple[str, int], object]:
        wanted = {(fact.source_table, fact.legacy_pk) for fact in batch}
        rows = model.objects.filter(
            organization=self._context.organization,
            source_system=SOURCE_SYSTEM,
            source_table__in={key[0] for key in wanted},
            source_pk__in={key[1] for key in wanted},
        )
        return {(row.source_table, row.source_pk): row for row in rows if (row.source_table, row.source_pk) in wanted}

    @staticmethod
    def _assert_same_evidence(row, fact: ConflictFact, *, expected_digest: str) -> None:
        if (
            row.source_row_hash != fact.source_row_hash
            or row.raw_score_text != fact.losing_text
            or row.materialization_digest != expected_digest
            or str(row.enrollment_id or "") != str(fact.enrollment_pk)
        ):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_conflict_fact_conflict")

    def _payload(self, fact: ConflictFact) -> dict:
        """``LegacyGradeFact`` fields; the value is not clamped or quantized."""

        return {
            "enrollment_id": fact.enrollment_pk,
            "source_snapshot_sha256": self._run.snapshot_sha256,
            "source_row_hash": fact.source_row_hash,
            "transform_version": self._run.transform_version,
            "evidence_kind": "other",
            "score_code": fact.month_id,
            "is_archive": fact.source_table == POINT_ARCHIVE_TABLE,
            "mapping_status": "conflict",
            "mapping_issue_code": FACT_CONFLICT_ISSUE_CODE,
            "source_student_ref": fact.student_ref,
            "source_journal_ref": fact.uniqid,
            # Mənbə xanasının stabil təqvim locator-u saxlanır. Disposable
            # target Lesson UUID-si source provenansına və digest-ə düşmür.
            "source_lesson_ref": fact.source_lesson_ref,
            "source_enrollment_ref": f"{fact.uniqid}:{fact.student_ref}",
            "raw_score_text": fact.losing_text,
            "requires_exam_center_review": True,
        }

    @staticmethod
    def _entry(fact: ConflictFact, *, digest: str, natural_key) -> _PendingSeal:
        return _PendingSeal(
            seal_key=fact.seal_key,
            digest=digest,
            state=_STATE.MIGRATED,
            label=LEGACY_GRADE_FACT_MODEL_LABEL,
            rule_codes=(CONFLICT_EVIDENCE_RULE_CODE, fact.issue_code),
            natural_key=natural_key,
        )

    def _seal(self, entries, target_pks, *, issue_counts) -> list:
        resolved = [
            JournalSealEntry(
                seal_key=entry.seal_key,
                digest=entry.digest,
                state=entry.state,
                label=entry.label,
                target_pk=target_pks.get(entry.natural_key, "") if entry.label else "",
                rule_codes=entry.rule_codes,
            )
            for entry in entries
        ]
        MARK_CONFLICT_SEALER.seal_many(self._context, resolved, issue_counts=issue_counts)
        return [(entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in resolved]


__all__ = [
    "CONFLICT_ALREADY_EVIDENCED_RULE_CODE",
    "CONFLICT_EVIDENCE_RULE_CODE",
    "CONFLICT_ISSUE_SEVERITY",
    "MARK_CONFLICT_ENTITY_TYPE",
    "MARK_CONFLICT_SEALER",
    "ConflictFact",
    "ConflictFactWriter",
    "conflict_seal_key",
]
