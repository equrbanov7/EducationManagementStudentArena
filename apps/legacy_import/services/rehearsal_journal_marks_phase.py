"""Phase: ``journal_marks`` (J4) — ``journals_dates_points`` təqvim ayları → LessonMark.

Derived faza (``source_tables = ()``): mənbə ``rehearsal_journal_cells``
sürücüsü ilə axıdılır, hədəflər ``rehearsal_journal_marks_targets`` ilə yazılır.

**Ledger qranulyarlığı (spec B.6)**: 5,135,289 sətir üçün sətir-başına
``LegacyEntityMap`` yazılmır — hər JURNAL bir möhür alır və o möhürün
derivation digest-inə jurnalın sətir hesabatı (yazıldı / atlandı / karantin,
səbəb-səbəb) qatlanır.  Resume həmin möhürdə qısa-qapanır; qərar dəyişsə
``upsert_entity_map`` özü ``legacy_entity_identity_conflict`` verir.

Qərar nərdivanı (yuxarıdan aşağı, hər pillə öz sətrini hesaba alır):

* jurnal J1-də MIGRATED deyil → ``legacy_journal_mark_orphan``;
* J-V4 dublikat uduzanı → ``legacy_journal_mark_duplicate`` (sürücüdə);
* ``point=''`` → mark YARADILMIR (J-V1(F)), ``legacy_journal_mark_empty``;
* oxunmayan ``point`` dəyəri → KARANTİN ``legacy_journal_mark_point_unknown``
  (J-V13; naməlum ``month_id`` KODU isə J6-nın catch-all yoludur);
* rəqəm 0-10 xaricində → KARANTİN ``legacy_journal_mark_score_out_of_range``
  (J-V2: şkala çevrilmir, dəyər təhrif olunmur);
* qeydiyyat (J2) və ya dərs slotu (J3) həll olunmur → müvafiq WARNING;
* qalanı yazılır: ``ie`` → PRESENT(score=None), ``qb`` → ABSENT (J-V3
  pəncərəsinə düşürsə EXCUSED), rəqəm → PRESENT + score.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap

from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
)
from .rehearsal_journal_cells import JournalCellLedger, drive_cells
from .rehearsal_journal_enrollments_phase import (
    JOURNAL_ENROLLMENT_ENTITY_TYPE,
    JOURNAL_ENROLLMENTS_PHASE_KEY,
)
from .rehearsal_journal_lessons_phase import JOURNAL_LESSONS_PHASE_KEY
from .rehearsal_journal_marks_targets import (
    ABSENT_STATUS,
    EXCUSED_STATUS,
    MARK_SEALER,
    MARKS_ENTITY_TYPE,
    PRESENT_STATUS,
    LessonMarkWriter,
    MarkWrite,
    journal_seal_entry,
    recompute_absence_hours,
)
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index, validated_uniqid
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import (
    ABSENT_TOKEN,
    CALENDAR_MONTHS,
    MARK_SCORE_MAX,
    PRESENT_TOKEN,
    allowed_absence_windows,
    calendar_slot,
    is_excused,
    legacy_flag,
    legacy_text,
    lesson_slot_index,
    migrated_index,
    normalized_time,
    parse_cell_score,
)
from .rehearsal_journal_seal import state_for
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_MARKS_PHASE_KEY = "journal_marks"
JOURNAL_MARKS_PHASE_ORDER = 40  # journal_lessons-dən (38) sonra
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-marks-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_OFFERINGS_PHASE_KEY, JOURNAL_ENROLLMENTS_PHASE_KEY, JOURNAL_LESSONS_PHASE_KEY})

_STATE = LegacyEntityMap.State

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "journal_marks_materialised",
        _STATE.SKIPPED: "journal_marks_skipped",
        _STATE.QUARANTINED: "journal_marks_unresolved",
    }
)

# Hesabat açarı → (issue kodu, karantin sayılırmı).  Açar adları möhürün
# digest-inə qatlandığı üçün bu cədvəl həm taksonomiya, həm də resepti sayılır.
OUTCOME_RULES = MappingProxyType(
    {
        "orphan": ("legacy_journal_mark_orphan", False),
        "duplicate": ("legacy_journal_mark_duplicate", False),
        "empty": ("legacy_journal_mark_empty", False),
        "unknown": ("legacy_journal_mark_point_unknown", True),
        "range": ("legacy_journal_mark_score_out_of_range", True),
        "enrollment": ("legacy_journal_mark_enrollment_unresolved", False),
        "lesson": ("legacy_journal_mark_lesson_unresolved", False),
        "conflict": ("legacy_journal_mark_target_conflict", False),
        "excused": ("legacy_journal_mark_excused", False),
        "lab": ("legacy_journal_mark_lab_cell", False),
        "archive_overlap": ("legacy_journal_archive_overlap", False),
    }
)
QUARANTINE_KEYS = tuple(key for key, (_code, fatal) in OUTCOME_RULES.items() if fatal)
WRITTEN_KEYS = ("written", "archive_written")


@dataclass(frozen=True)
class MarkCell:
    """Bir təqvim xanasının distillə olunmuş forması (mənbə sətri saxlanmır)."""

    legacy_pk: int
    uniqid: str
    student_id: int
    month: int
    day: int
    time_text: str
    point: str
    excusable: int
    lab: int
    from_archive: bool
    why: str
    description: str


def classify_mark_cell(point_text: str):
    """J-V1/J-V2 saf təsnifatı: ``(nəticə, status, bal)``.

    ``nəticə`` ∈ {empty, present, absent, scored, unknown, range}.  Heç bir
    şkala çevrilməsi yoxdur — bal olduğu kimi qaytarılır.
    """

    if point_text == "":
        return "empty", "", None
    if point_text == PRESENT_TOKEN:
        return "present", PRESENT_STATUS, None
    if point_text == ABSENT_TOKEN:
        return "absent", ABSENT_STATUS, None
    score = parse_cell_score(point_text)
    if score is None:
        return "unknown", "", None
    if score > MARK_SCORE_MAX:
        return "range", "", None
    return "scored", PRESENT_STATUS, Decimal(score)


def is_calendar_month(month_id: str) -> bool:
    return month_id in CALENDAR_MONTHS


def distill_mark_cell(legacy_pk: int, row, from_archive: bool) -> MarkCell:
    """Təqvim sətrini distillə et.

    Gün nömrəsi pozuqdursa sətir ATILMIR — ``(0, 0)`` slotu ilə davam edir və
    heç bir dərsə uyğun gəlmədiyi üçün nərdivanın ``lesson`` pilləsində qeydli
    şəkildə hesaba alınır.  Səssiz düşmə say balansını (J8) pozardı.
    """

    slot = calendar_slot(legacy_text(row["month_id"]), legacy_text(row["day_number"])) or (0, 0)
    student_id = row["student_id"]
    if type(student_id) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return MarkCell(
        legacy_pk=legacy_pk,
        uniqid=validated_uniqid(row["journal_uniqid"]),
        student_id=student_id,
        month=slot[0],
        day=slot[1],
        time_text=normalized_time(row["time"]),
        point=legacy_text(row["point"]),
        excusable=legacy_flag(row["excusable"]),
        lab=legacy_flag(row["lab"]),
        from_archive=from_archive,
        why=legacy_text(row["why"]),
        description=legacy_text(row["description"]),
    )


@dataclass(frozen=True)
class MarkResolution:
    """Faza boyu dəyişməyən lookup keşləri (registrar-a sorğu vermədən)."""

    offerings: dict
    enrollments: dict
    lessons: dict
    windows: dict


def build_resolution(context: RehearsalContext) -> MarkResolution:
    return MarkResolution(
        offerings=migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE),
        enrollments=migrated_index(context, JOURNAL_ENROLLMENT_ENTITY_TYPE),
        lessons=lesson_slot_index(context),
        windows=allowed_absence_windows(context),
    )


class JournalMarksPhase:
    """J4: təqvim xanalarının ``LessonMark``-a çevrilməsi, jurnal başına bir möhür."""

    phase_key = JOURNAL_MARKS_PHASE_KEY
    order = JOURNAL_MARKS_PHASE_ORDER
    source_tables = ()
    entity_types = (MARKS_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Açar ``uniqid``-dir (rəqəm deyil): rebuild leksikoqrafik sıralayır.
    derived_ledger_sort_key = staticmethod(str)

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, Config deyil: orkestrator run-u FAILED bitirir.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        resolution = build_resolution(context)
        ledger = JournalCellLedger(recorded=MARK_SEALER.recorded_decisions(context))
        writer = LessonMarkWriter(context, ledger)
        drive_cells(
            context,
            ledger=ledger,
            domain=is_calendar_month,
            distill=distill_mark_cell,
            decide=lambda cell: self._decide(cell=cell, resolution=resolution, ledger=ledger, writer=writer),
            overlap_key="archive_overlap",
            # J-V7: arxiv keçidi başlamazdan əvvəl əsas cədvəl hədəfə düşməlidir.
            flush=writer.flush,
        )
        recompute_absence_hours(context, ledger.touched_targets)

        issue_counts: Counter[tuple[str, str]] = Counter()
        decisions = list(ledger.recorded.items())
        entries = []
        for uniqid, tally in sorted(ledger.tallies.items()):
            state = state_for(
                written=sum(tally[key] for key in WRITTEN_KEYS),
                quarantined=sum(tally[key] for key in QUARANTINE_KEYS),
            )
            entry, outcome = journal_seal_entry(
                uniqid=uniqid,
                state=state,
                offering_pk=resolution.offerings.get(uniqid, ""),
                tally=tally,
                evidence=ledger.evidence_part(uniqid),
                rule_codes=tuple(OUTCOME_RULES[key][0] for key in sorted(OUTCOME_RULES) if tally[key]),
            )
            entries.append(entry)
            decisions.append((uniqid, outcome))
        MARK_SEALER.seal_many(context, entries, issue_counts=issue_counts)

        # SA-2: zəncir seal açarının LEKSİKOQRAFİK sırasında — rebuild ilə eyni.
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for uniqid, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(uniqid, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_MARKS_PHASE_KEY}.records.{sum(state_counts.values())}")
        context.stdout_note(f"{JOURNAL_MARKS_PHASE_KEY}.cells.{ledger.cell_count}")
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

    def _decide(self, *, cell: MarkCell, resolution: MarkResolution, ledger, writer) -> None:
        """Bir xananın qərarı — nərdivan modul qeydindəki sıradadır."""

        offering_pk = resolution.offerings.get(cell.uniqid, "")
        if not offering_pk:
            ledger.count(cell.uniqid, "orphan")
            return
        outcome, status, score = classify_mark_cell(cell.point)
        if outcome in ("empty", "unknown", "range"):
            ledger.count(cell.uniqid, outcome)
            return
        enrollment_pk = resolution.enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
        if not enrollment_pk:
            ledger.count(cell.uniqid, "enrollment")
            return
        slot = resolution.lessons.get((cell.uniqid, cell.month, cell.day, cell.time_text))
        if slot is None:
            ledger.count(cell.uniqid, "lesson")
            return
        lesson_pk, lesson_date = slot
        if status == ABSENT_STATUS and is_excused(
            excusable=cell.excusable,
            student_id=cell.student_id,
            lesson_date=lesson_date,
            windows=resolution.windows,
        ):
            status = EXCUSED_STATUS
            ledger.count(cell.uniqid, "excused")
            # J-V3: sənəd qeydləri (``why``/``description``) qərara daxil olub —
            # ledger onları oxunaqlı saxlaya bilmir, ona görə möhürə qatlanır.
            ledger.note(cell.uniqid, f"{cell.legacy_pk}|{cell.why}|{cell.description}")
        if cell.lab == 1:
            # J-V5: J3 hər dərsi ``lecture`` yaradır, ona görə bu yalnız
            # qeyddir — davranışa təsiri yoxdur (bax modul qeydi).
            ledger.count(cell.uniqid, "lab")
        writer.enqueue(
            uniqid=cell.uniqid,
            from_archive=cell.from_archive,
            request=MarkWrite(
                lesson_pk=lesson_pk,
                enrollment_pk=enrollment_pk,
                status=status,
                score=score,
                allow_existing=not cell.from_archive,
            ),
        )
