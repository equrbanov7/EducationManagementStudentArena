"""Phase: ``journal_finals`` (J6) — ``im``/``im2`` → FinalGrade / ResitRecord.

Bu faza HƏM DƏ catch-all-dır: təqvim ayı (J4) və komponent kodu (J5) olmayan
HƏR ``month_id`` buraya düşür, yəni ``pa``/``wr``/``ss``/``ww``/``ll``/``rr``/
``ga`` kimi az işlənən kodlar (J-V13) məhz burada
``legacy_journal_mark_code_unknown`` ilə KARANTİNƏ alınır — heç biri map
edilmir, hamısı tam sayla hesabata düşür.

``finals.set_exam_score`` / ``finals.set_resit_score`` semantikası güzgülənir,
İMPORT EDİLMİR.  Modul-sərhəd səbəbi J1/J3/J4-dəki ilə eynidir; üstəlik iki
davranış fərqi qəsdəndir və J-V2 ilə tələb olunur:

* ``set_exam_score`` balı ``exam_score_max(scheme)``-ə (defolt 50) CLAMP edir —
  canlı mənbədəki 376 ədəd 50-dən böyük ``im`` balı təhrif olunardı.  Burada
  dəyər OLDUĞU KİMİ yazılır və ``legacy_journal_exam_score_above_scheme``
  İNFO-su ilə hesabata düşür (J-V2);
* ``set_resit_score`` mövcud ``ResitRecord`` olmadan heç nə yazmır və
  ``evaluate_resit`` sinxronizasiyası ``compute_final_result``-a bağlıdır —
  import isə tarixi faktı (təkrar imtahan balı) köçürür, cari qiymətləndirmə
  qərarını yenidən vermir.  Ona görə qeyd birbaşa yaradılır: ``status`` bal
  varsa COMPLETED, ``reason`` isə import defoltu ``total`` (mənbədə səbəb
  sütunu yoxdur — ``Enrollment.kind='mandatory'`` defoltu ilə eyni sinif qərar).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_FIELDS
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_cells import JournalCellLedger, drive_cells
from .rehearsal_journal_components_phase import JOURNAL_COMPONENTS_PHASE_KEY
from .rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE
from .rehearsal_journal_marks_phase import JOURNAL_MARKS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index, validated_uniqid
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import (
    CALENDAR_MONTHS,
    COMPONENT_MONTHS,
    EXAM_MONTH,
    EXAM_SCHEME_SCORE_MAX,
    FINAL_MONTHS,
    FINAL_SCORE_MAX,
    RESIT_MONTH,
    legacy_text,
    migrated_index,
    parse_cell_score,
)
from .rehearsal_journal_seal import JournalSealEntry, JournalSealer, state_for, tally_parts
from .rehearsal_journal_slices import build_offering_slices
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_FINALS_PHASE_KEY = "journal_finals"
JOURNAL_FINALS_PHASE_ORDER = 44  # journal_components-dən (42) sonra
FINALS_ENTITY_TYPE = "journal_finals"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-finals-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_MARKS_PHASE_KEY, JOURNAL_COMPONENTS_PHASE_KEY})

# Mənbədə səbəb sütunu yoxdur; import ən neytral səbəbi seçir (J-V-qərarsız).
RESIT_IMPORT_REASON = "total"
RESIT_COMPLETED_STATUS = "completed"

_STATE = LegacyEntityMap.State
_SEVERITY = LegacyMigrationIssue.Severity

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_finals_materialised",
        _STATE.SKIPPED: "journal_finals_skipped",
        _STATE.QUARANTINED: "journal_finals_unresolved",
    }
)

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                # J-V13 catch-all: naməlum ``month_id`` kodu VƏ ``im``/``im2``
                # xanasında oxunmayan dəyər (``l`` kimi).
                "legacy_journal_mark_code_unknown",
                "legacy_journal_final_score_out_of_range",
                "legacy_journal_final_enrollment_unresolved",
                "legacy_journal_final_target_conflict",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                "legacy_journal_final_orphan",
                "legacy_journal_final_duplicate",
                "legacy_journal_final_empty",
                "legacy_journal_final_archive_overlap",
                # J-V2: bal sxem tavanından (50) böyükdür — DƏYƏR SAXLANILIR.
                "legacy_journal_exam_score_above_scheme",
            ),
            _SEVERITY.INFO,
        ),
    }
)

OUTCOME_RULES = MappingProxyType(
    {
        "orphan": ("legacy_journal_final_orphan", False),
        "duplicate": ("legacy_journal_final_duplicate", False),
        "empty": ("legacy_journal_final_empty", False),
        "unknown": ("legacy_journal_mark_code_unknown", True),
        "range": ("legacy_journal_final_score_out_of_range", True),
        "enrollment": ("legacy_journal_final_enrollment_unresolved", False),
        "conflict": ("legacy_journal_final_target_conflict", False),
        "above_scheme": ("legacy_journal_exam_score_above_scheme", False),
        "archive_overlap": ("legacy_journal_final_archive_overlap", False),
    }
)
QUARANTINE_KEYS = tuple(key for key, (_code, fatal) in OUTCOME_RULES.items() if fatal)
WRITTEN_KEYS = ("written", "archive_written")

FINALS_SEALER = JournalSealer(
    entity_type=FINALS_ENTITY_TYPE,
    source_table=JOURNAL_POINT_FIELDS.source_table,
    derivation_prefix=b"legacy-rehearsal-journal-finals-derivation-v1\x00",
    contract_fingerprint=JOURNAL_POINT_FIELDS.fingerprint,
    issue_severity=ISSUE_SEVERITY,
)


@dataclass(frozen=True)
class FinalCell:
    """Bir ``im``/``im2``/naməlum-kod xanasının distillə olunmuş forması."""

    legacy_pk: int
    uniqid: str
    student_id: int
    month_id: str
    point: str
    from_archive: bool


def classify_final_cell(month_id: str, point_text: str):
    """``(nəticə, bal)`` — J-V2/J-V13.

    ``nəticə`` ∈ {unknown, empty, scored, range}.  ``month_id`` ``im``/``im2``
    deyilsə dəyər ümumiyyətlə oxunmur: kod naməlumdur (J-V13 karantini).
    """

    if month_id not in FINAL_MONTHS:
        return "unknown", None
    if point_text == "":
        return "empty", None
    score = parse_cell_score(point_text)
    if score is None:
        return "unknown", None
    if score > FINAL_SCORE_MAX:
        return "range", None
    return "scored", Decimal(score)


def is_final_month(month_id: str) -> bool:
    """J6 catch-all domeni: J4 və J5 götürməyən HƏR kod."""

    return month_id not in CALENDAR_MONTHS and month_id not in COMPONENT_MONTHS


def distill_final_cell(legacy_pk: int, row, from_archive: bool) -> FinalCell:
    student_id = row["student_id"]
    if type(student_id) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return FinalCell(
        legacy_pk=legacy_pk,
        uniqid=validated_uniqid(row["journal_uniqid"]),
        student_id=student_id,
        month_id=legacy_text(row["month_id"]),
        point=legacy_text(row["point"]),
        from_archive=from_archive,
    )


def write_exam_score(context, *, enrollment_pk: str, score, allow_existing: bool) -> str:
    """``FinalGrade.exam_score`` — ``finals.set_exam_score`` güzgüsü (clamp-siz)."""

    model = django_apps.get_model("registrar", "FinalGrade")
    with transaction.atomic():
        grade, _created = model.objects.get_or_create(organization=context.organization, enrollment_id=enrollment_pk)
        if grade.exam_score is None:
            grade.exam_score = score
            grade.entered_by = None
            grade.save(update_fields=["exam_score", "entered_by", "updated_at"])
            return "written"
        if not allow_existing:
            return "superseded"
        return "written" if Decimal(grade.exam_score) == Decimal(score) else "conflict"


def write_resit_score(context, *, enrollment_pk: str, score, allow_existing: bool) -> str:
    """``ResitRecord.resit_score`` — qeyd yoxdursa yaradılır (modul qeydi)."""

    model = django_apps.get_model("registrar", "ResitRecord")
    with transaction.atomic():
        record, created = model.objects.get_or_create(
            organization=context.organization,
            enrollment_id=enrollment_pk,
            defaults={
                "reason": RESIT_IMPORT_REASON,
                "status": RESIT_COMPLETED_STATUS,
                "resit_score": score,
                "decided_by": None,
            },
        )
        if created:
            return "written"
        if record.resit_score is None:
            record.resit_score = score
            record.status = RESIT_COMPLETED_STATUS
            record.save(update_fields=["resit_score", "status", "updated_at"])
            return "written"
        if not allow_existing:
            return "superseded"
        return "written" if Decimal(record.resit_score) == Decimal(score) else "conflict"


class JournalFinalsPhase:
    """J6: yekun/təkrar imtahan balları + naməlum kodların karantini."""

    phase_key = JOURNAL_FINALS_PHASE_KEY
    order = JOURNAL_FINALS_PHASE_ORDER
    source_tables = ()
    entity_types = (FINALS_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        slices = build_offering_slices(context, migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE))
        enrollments = migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE)
        ledger = JournalCellLedger(recorded=FINALS_SEALER.recorded_decisions(context))
        drive_cells(
            context,
            ledger=ledger,
            domain=is_final_month,
            distill=distill_final_cell,
            decide=lambda cell: self._decide(context, cell=cell, slices=slices, enrollments=enrollments, ledger=ledger),
            overlap_key="archive_overlap",
        )

        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(ledger.recorded.items())
        entries = []
        for uniqid, tally in sorted(ledger.tallies.items()):
            state = state_for(
                written=sum(tally[key] for key in WRITTEN_KEYS),
                quarantined=sum(tally[key] for key in QUARANTINE_KEYS),
            )
            digest = FINALS_SEALER.derivation_hash(seal_key=uniqid, outcome_token=str(state), parts=tally_parts(tally))
            label = COURSE_OFFERING_MODEL_LABEL if state == _STATE.MIGRATED else ""
            entries.append(
                JournalSealEntry(
                    seal_key=uniqid,
                    digest=digest,
                    state=state,
                    label=label,
                    target_pk=slices.primary_offering(uniqid) if label else "",
                    rule_codes=tuple(OUTCOME_RULES[key][0] for key in sorted(OUTCOME_RULES) if tally[key]),
                )
            )
            decisions.append((uniqid, (state, digest, label)))
        FINALS_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for uniqid, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(uniqid, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_FINALS_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    def _decide(self, context, *, cell: FinalCell, slices, enrollments, ledger) -> None:
        """orphan → kod/dəyər → qeydiyyat → yazı nərdivanı.

        Yekun bal ``Enrollment``-ə yazılır (açılışa yox), ona görə burada dilim
        həlli lazım deyil: yazılış onsuz da tələbənin öz dilimini göstərir.
        """

        if not slices.has_offering(cell.uniqid):
            ledger.count(cell.uniqid, "orphan")
            return
        outcome, score = classify_final_cell(cell.month_id, cell.point)
        if outcome != "scored":
            ledger.count(cell.uniqid, outcome)
            return
        enrollment_pk = enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
        if not enrollment_pk:
            ledger.count(cell.uniqid, "enrollment")
            return
        if score > EXAM_SCHEME_SCORE_MAX:
            # J-V2: dəyər saxlanılır, yalnız qeyd olunur.
            ledger.count(cell.uniqid, "above_scheme")
        writer = write_exam_score if cell.month_id == EXAM_MONTH else write_resit_score
        result = writer(
            context,
            enrollment_pk=enrollment_pk,
            score=score,
            allow_existing=not cell.from_archive,
        )
        if result == "written":
            ledger.count(cell.uniqid, "archive_written" if cell.from_archive else "written")
        elif result == "superseded":
            ledger.count(cell.uniqid, "archive_overlap")
        else:
            ledger.count(cell.uniqid, "conflict")


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "FINALS_ENTITY_TYPE",
    "FINALS_SEALER",
    "ISSUE_SEVERITY",
    "JOURNAL_FINALS_PHASE_KEY",
    "JOURNAL_FINALS_PHASE_ORDER",
    "RESIT_MONTH",
    "JournalFinalsPhase",
    "classify_final_cell",
    "is_final_month",
]
