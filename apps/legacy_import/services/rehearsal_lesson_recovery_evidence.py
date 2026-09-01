"""J12-də hədəfsiz qalan təqvim xanasının append-only xam sübutu.

Tarixi qurulmayan və ya bərpadan sonra yenə ``Lesson``-a bağlanmayan yazıla
bilən xana kanonik jurnala köçmür.  Buna baxmayaraq onun xam bal mətni, dəqiq
mənbə cədvəli/pk-sı və tam sətir hash-i ``LegacyGradeFact``-da saxlanır.
Fakt ``unresolved`` qalır, heç bir ``Enrollment``-ə bağlanmır və İmtahan
Mərkəzinin baxışı məcburidir.
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

MARK_UNRESOLVED_ENTITY_TYPE = "legacy_mark_unresolved"
UNRESOLVED_EVIDENCE_RULE_CODE = "legacy_mark_unresolved_evidence"
FACT_UNRESOLVED_ISSUE_CODE = "legacy_grade_fact_unresolved"
DATE_INVALID_RULE_CODE = "legacy_lesson_synth_date_invalid"
LESSON_UNRESOLVED_RULE_CODE = "legacy_journal_mark_recovered_lesson_unresolved"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity
_FACT_BATCH = 500

UNRESOLVED_ISSUE_SEVERITY = MappingProxyType(
    {
        UNRESOLVED_EVIDENCE_RULE_CODE: _SEVERITY.WARNING,
        DATE_INVALID_RULE_CODE: _SEVERITY.WARNING,
        LESSON_UNRESOLVED_RULE_CODE: _SEVERITY.WARNING,
    }
)

MARK_UNRESOLVED_SEALER = JournalSealer(
    entity_type=MARK_UNRESOLVED_ENTITY_TYPE,
    source_table=POINT_SOURCE_TABLE,
    derivation_prefix=b"legacy-rehearsal-mark-unresolved-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=UNRESOLVED_ISSUE_SEVERITY,
)


def unresolved_seal_key(*, from_archive: bool, legacy_pk: int) -> str:
    """Mənbə cədvəli + pk: əsas və arxiv pk məkanları toqquşmur."""

    return f"uf:{'a' if from_archive else 'p'}:{legacy_pk}"


@dataclass(frozen=True)
class UnresolvedFact:
    """Kanonik dərsə yazıla bilməyən, amma itirilməməli təqvim xanası."""

    source_table: str
    legacy_pk: int
    source_row_hash: str
    uniqid: str
    student_ref: str
    month_id: str
    day: int
    time_text: str
    raw_score_text: str
    issue_code: str

    @property
    def seal_key(self) -> str:
        return unresolved_seal_key(
            from_archive=self.source_table == POINT_ARCHIVE_TABLE,
            legacy_pk=self.legacy_pk,
        )

    @property
    def natural_key(self) -> tuple[str, int]:
        return self.source_table, self.legacy_pk

    def digest_parts(self) -> tuple[str, ...]:
        return (
            f"table={self.source_table}",
            f"pk={self.legacy_pk}",
            f"row={self.source_row_hash}",
            f"journal={self.uniqid}",
            f"student={self.student_ref}",
            f"month={self.month_id}",
            f"day={self.day}",
            f"time={self.time_text}",
            f"raw={self.raw_score_text}",
            f"issue={self.issue_code}",
        )


def unresolved_fact_for(cell, *, issue_code: str) -> UnresolvedFact:
    """``RecoveryMarkCell``-i heç bir xam bal çevirmədən fakta çevir."""

    return UnresolvedFact(
        source_table=POINT_ARCHIVE_TABLE if cell.from_archive else POINT_SOURCE_TABLE,
        legacy_pk=cell.legacy_pk,
        source_row_hash=cell.row_hash,
        uniqid=cell.uniqid,
        student_ref=str(cell.student_id),
        month_id=f"{cell.month:02d}",
        day=cell.day,
        time_text=cell.time_text,
        raw_score_text=cell.point,
        issue_code=issue_code,
    )


@dataclass(frozen=True)
class _PendingSeal:
    fact: UnresolvedFact
    digest: str
    state: str
    label: str
    rule_codes: tuple[str, ...]


class UnresolvedFactWriter:
    """Xam fakt + onun ledger möhürünü eyni tranzaksiyada yazır."""

    def __init__(self, context, *, run, recorded=None, batch_rows: int = _FACT_BATCH) -> None:
        self._context = context
        self._run = run
        self._batch_rows = max(1, int(batch_rows))
        self._pending: list[UnresolvedFact] = []
        self.recorded = dict(recorded or {})
        self.issue_counts: Counter = Counter()
        self.sealed: list = []
        self.written = 0
        self.already = 0

    def add(self, fact: UnresolvedFact) -> None:
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
        batch_issue_counts: Counter = Counter()
        created: dict[tuple[str, int], object] = {}
        try:
            with transaction.atomic():
                existing = self._existing(model, batch)
                pending_seals: list[_PendingSeal] = []
                target_pks: dict[tuple[str, int], str] = {}
                for fact in batch:
                    payload = self._payload(fact)
                    digest = fact_materialization_digest(
                        natural_key=(SOURCE_SYSTEM, *fact.natural_key),
                        source_row_hash=fact.source_row_hash,
                        payload=payload,
                    )
                    row = existing.get(fact.natural_key)
                    if row is not None:
                        self._assert_same_evidence(row, fact, expected_digest=digest)
                        target_pks[fact.natural_key] = str(row.pk)
                        pending_seals.append(self._pending_seal(fact, digest=digest))
                        continue
                    created[fact.natural_key] = model(
                        organization=self._context.organization,
                        source_system=SOURCE_SYSTEM,
                        source_table=fact.source_table,
                        source_pk=fact.legacy_pk,
                        materialization_digest=digest,
                        **payload,
                    )
                    pending_seals.append(self._pending_seal(fact, digest=digest))
                if created:
                    model.objects.bulk_create(list(created.values()))
                    target_pks.update({key: str(row.pk) for key, row in created.items()})
                resolved = self._seal(
                    pending_seals,
                    target_pks,
                    issue_counts=batch_issue_counts,
                )
        except Exception:
            self._pending = batch + self._pending
            raise
        self.written += len(created)
        self.already += len(batch) - len(created)
        self.issue_counts.update(batch_issue_counts)
        self.sealed.extend(resolved)

    def _deduplicated(self, batch) -> list[UnresolvedFact]:
        unique: dict[tuple[str, int], UnresolvedFact] = {}
        for fact in batch:
            previous = unique.get(fact.natural_key)
            if previous is not None and previous != fact:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_unresolved_fact_conflict")
            unique[fact.natural_key] = fact
        return list(unique.values())

    def _existing(self, model, batch) -> dict[tuple[str, int], object]:
        wanted = {fact.natural_key for fact in batch}
        rows = model.objects.filter(
            organization=self._context.organization,
            source_system=SOURCE_SYSTEM,
            source_table__in={key[0] for key in wanted},
            source_pk__in={key[1] for key in wanted},
        )
        return {(row.source_table, row.source_pk): row for row in rows if (row.source_table, row.source_pk) in wanted}

    def _assert_same_evidence(self, row, fact: UnresolvedFact, *, expected_digest: str) -> None:
        if (
            row.source_row_hash != fact.source_row_hash
            or row.raw_score_text != fact.raw_score_text
            or row.materialization_digest != expected_digest
            or row.enrollment_id is not None
        ):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_unresolved_fact_conflict")

    def _payload(self, fact: UnresolvedFact) -> dict:
        slot_ref = f"calendar:{fact.month_id}:{fact.day}:{fact.time_text}"
        return {
            "enrollment_id": None,
            "source_snapshot_sha256": self._run.snapshot_sha256,
            "source_row_hash": fact.source_row_hash,
            "transform_version": self._run.transform_version,
            "evidence_kind": "other",
            "score_code": fact.month_id,
            "is_archive": fact.source_table == POINT_ARCHIVE_TABLE,
            "mapping_status": "unresolved",
            "mapping_issue_code": FACT_UNRESOLVED_ISSUE_CODE,
            "source_student_ref": fact.student_ref,
            "source_journal_ref": fact.uniqid,
            "source_lesson_ref": slot_ref,
            "source_enrollment_ref": f"{fact.uniqid}:{fact.student_ref}",
            "raw_score_text": fact.raw_score_text,
            "requires_exam_center_review": True,
        }

    def _pending_seal(self, fact, *, digest: str) -> _PendingSeal:
        # Grade-fact ledger müqaviləsi: map/observation hash-i faktın öz
        # materialization digest-i olmalıdır. Mövcud eyni fakt da həmin hədəfə
        # MIGRATED bağlanır; SKIPPED derivation hash exact gate-i və rerun-u pozur.
        return _PendingSeal(
            fact=fact,
            digest=digest,
            state=_STATE.MIGRATED,
            label=LEGACY_GRADE_FACT_MODEL_LABEL,
            rule_codes=(UNRESOLVED_EVIDENCE_RULE_CODE, fact.issue_code),
        )

    def _seal(self, entries, target_pks, *, issue_counts) -> list:
        resolved = [
            JournalSealEntry(
                seal_key=entry.fact.seal_key,
                digest=entry.digest,
                state=entry.state,
                label=entry.label,
                target_pk=target_pks.get(entry.fact.natural_key, "") if entry.label else "",
                rule_codes=entry.rule_codes,
            )
            for entry in entries
        ]
        MARK_UNRESOLVED_SEALER.seal_many(self._context, resolved, issue_counts=issue_counts)
        return [(entry.seal_key, (entry.state, entry.digest, entry.label)) for entry in resolved]


__all__ = [
    "DATE_INVALID_RULE_CODE",
    "FACT_UNRESOLVED_ISSUE_CODE",
    "LESSON_UNRESOLVED_RULE_CODE",
    "MARK_UNRESOLVED_ENTITY_TYPE",
    "MARK_UNRESOLVED_SEALER",
    "UNRESOLVED_EVIDENCE_RULE_CODE",
    "UNRESOLVED_ISSUE_SEVERITY",
    "UnresolvedFact",
    "UnresolvedFactWriter",
    "unresolved_fact_for",
    "unresolved_seal_key",
]
