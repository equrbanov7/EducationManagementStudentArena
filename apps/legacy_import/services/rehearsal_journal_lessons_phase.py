"""Phase: ``journal_lessons`` (J3) — ``journals_dates_added_by_teacher`` → registrar.Lesson.

Derived faza (``source_tables = ()``): üç audited kontrakt READ-ONLY axıdılır —
əvvəl ``semestr_jurnal`` (il xəritəsi) və ``journals`` (rəqəm ``journal_id`` →
uniqid indeksi), sonra dərs sətirlərinin özü.  Mənbə sxemi FAKTLA təsdiqlənib:
dərs sətri jurnala ``journal_id`` (int FK → journals.id) ilə bağlanır və İL
SÜTUNU YOXDUR — il jurnalın semestrindən törədilir (akademik il Y/Y+1: ay 9-12
→ Y, ay 1-8 → Y+1; bölgü canlı mənbədə semestr-ay histoqramı ilə yoxlanılıb).

Qərar nərdivanı (yuxarıdan aşağı, hər pillə öz sətrini möhürləyir):

* ``journal_id`` heç bir jurnala bağlanmır VƏ YA jurnal J1-də MIGRATED deyil
  (V6 süzgəci / karantin) → SKIPPED ``legacy_journal_lesson_orphan`` (spec J3).
* Tarix (törədilmiş illə) və ya saat ("HH:MM") qurula bilmir → QUARANTINED
  ``legacy_journal_lesson_invalid`` (data-qoruma: heç nə təxminlə düzəldilmir).
* Eyni jurnalda eyni (tarix, saat) slotu təkrarlanır → ilk sətir (ən kiçik id)
  udur, qalanları SKIPPED ``legacy_journal_lesson_duplicate`` (mənbədə 69,650
  belə artıq sətir var — V4 dedup qaydasının dərs analoqу).
* Qalanı: ``lesson_decision`` + dəstə yazıcısı — kind=lecture, hours=2, instructor açılışın
  müəllimi, allow_past semantikası (bax targets modulunun güzgü qeydi).

Ledger kimlik açarı dates sətrinin rəqəm id-sidir → zəncir J0 kimi artan id
sırasında yeriyir, rebuild-in defolt ``int`` sıralaması ilə üst-üstə düşür.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter
from types import MappingProxyType

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap

from .field_contracts import JOURNAL_DATES_FIELDS
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    source_row_hash,
)
from .rehearsal_journal_batch import Decision, JournalBatchWriter
from .rehearsal_journal_lessons_targets import (
    LESSON_ENTITY_TYPE,
    LESSON_SOURCE_TABLE,
    LessonRequest,
    invalid_decision,
    lesson_decision,
    lesson_materialiser,
    recorded_decisions,
    severity_for,
    skipped_decision,
)
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import journal_rows, legacy_int, migrated_target_index, validated_uniqid
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_periods_phase import JOURNAL_PERIODS_PHASE_KEY, parse_period, period_rows
from .rehearsal_journal_slices import build_offering_slices
from .rehearsal_structure_phase import probe_cancellation
from .source_extraction import open_audited_source_stream

JOURNAL_LESSONS_PHASE_KEY = "journal_lessons"
JOURNAL_LESSONS_PHASE_ORDER = 38  # journal_enrollments-dən (36) sonra
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-lessons-v1"
REQUIRED_PHASE_KEYS = frozenset({JOURNAL_PERIODS_PHASE_KEY, JOURNAL_OFFERINGS_PHASE_KEY})

_STATE = LegacyEntityMap.State
_TIME_PATTERN = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])\Z")
_AUTUMN_FIRST_MONTH = 9  # ay 9-12 akademik ilin birinci ilində keçirilir

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "lesson_materialised",
        _STATE.SKIPPED: "lesson_skipped",
        _STATE.QUARANTINED: "lesson_unresolved",
    }
)


def parse_lesson_schedule(*, first_year: int, month: object, day: object, time_value: object):
    """(tarix, saat) cütünü törədilmiş illə ciddi qur; alınmasa ``None`` (karantin)."""

    month_number = legacy_int(month)
    day_number = legacy_int(day)
    if type(time_value) is not str:
        return None
    match = _TIME_PATTERN.fullmatch(time_value)
    if match is None:
        return None
    year = first_year if month_number >= _AUTUMN_FIRST_MONTH else first_year + 1
    try:
        lesson_date = datetime.date(year, month_number, day_number)
    except ValueError:
        return None
    return lesson_date, datetime.time(int(match.group(1)), int(match.group(2)))


def lesson_rows(context: RehearsalContext):
    """Dərs cədvəlini attested, ciddi artan primary-key sırasında axıt."""

    entry = context.plan.entry_for(LESSON_SOURCE_TABLE)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=JOURNAL_DATES_FIELDS,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            # pk_inventory._row_pk ilə eyni: heç bir coercion, fail closed.
            if type(legacy_pk) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
            if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
            if legacy_pk <= previous_pk:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
            previous_pk = legacy_pk
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
            yield legacy_pk, projected_row
    if observed != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")


def semester_year_index(context: RehearsalContext) -> dict[int, int]:
    """Semestr id → akademik ilin BİRİNCİ ili (J0-ın öz parse-ı ilə, DB-siz).

    Parse alınmayan semestr xəritəyə düşmür: onun jurnalları J0/J1 zəncirində
    onsuz da karantindədir, dərs sətirləri isə orphan yoluna düşəcək.
    """

    years: dict[int, int] = {}
    for legacy_pk, row in period_rows(context):
        plan = parse_period(row)
        if plan is not None:
            years[legacy_pk] = int(plan.academic_year.split("/", 1)[0])
    return years


def journal_index(context: RehearsalContext) -> dict[int, tuple[str, int]]:
    """Rəqəm ``journals.id`` → (uniqid, semestr id) indeksi (dərs FK-nın həlli)."""

    index: dict[int, tuple[str, int]] = {}
    for legacy_pk, row in journal_rows(context):
        index[legacy_pk] = (validated_uniqid(row["uniqid"]), legacy_int(row["semestr"]))
    return index


def offering_instructor_index(context: RehearsalContext, offerings: dict[str, str]) -> dict[str, str]:
    """Offering pk → instructor pk ("" = NULL); dərs açılış müəllimini güzgülər."""

    offering_model = django_apps.get_model("registrar", "CourseOffering")
    rows = offering_model.objects.filter(organization=context.organization, pk__in=set(offerings.values())).values_list(
        "pk", "instructor_id"
    )
    return {str(pk): "" if instructor_id is None else str(instructor_id) for pk, instructor_id in rows}


class JournalLessonsPhase:
    """J3: dərs tarixlərinin jurnal sütunlarına çevrilməsi, sətir başına bir qərar."""

    phase_key = JOURNAL_LESSONS_PHASE_KEY
    order = JOURNAL_LESSONS_PHASE_ORDER
    source_tables = ()
    entity_types = (LESSON_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # 2026-08-28: açar artıq ``<legacy_pk>:<qrup>`` mətnidir (dilim başına bir
    # dərs), ona görə rebuild ``int`` deyil, LEKSİKOQRAFİK sıralayır.
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

        years = semester_year_index(context)
        journals = journal_index(context)
        offerings = migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE)
        slices = build_offering_slices(context, offerings)
        instructors = offering_instructor_index(context, offerings)

        recorded = recorded_decisions(context)
        writer = JournalBatchWriter(
            context,
            entity_type=LESSON_ENTITY_TYPE,
            source_table=LESSON_SOURCE_TABLE,
            severity_for=severity_for,
            materialiser=lesson_materialiser(instructors),
        )

        decisions: list[tuple[str, str, str, str]] = []
        state_counts: Counter[str] = Counter()
        claimed_slots: set[tuple[str, str, str]] = set()
        for legacy_pk, row in lesson_rows(context):
            probe_cancellation(context)
            for seal_key, outcome in self._lesson_entries(
                legacy_pk=legacy_pk,
                row=row,
                journals=journals,
                years=years,
                slices=slices,
                claimed_slots=claimed_slots,
                recorded=recorded,
            ):
                if isinstance(outcome, Decision):
                    writer.add(outcome)
                    entry = (seal_key, str(outcome.state), outcome.digest, outcome.label)
                else:
                    entry = (seal_key, *outcome)  # resume: möhür artıq bu run-dadır
                decisions.append(entry)
                state_counts[self.derived_state_key(entry[1])] += 1
        writer.flush()

        # SA-2: zəncir möhür açarının LEKSİKOQRAFİK sırasında — rebuild ilə eyni.
        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        for seal_key, state, digest, label in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, state, digest, label)

        context.stdout_note(f"{JOURNAL_LESSONS_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    def _resolved_slot(self, row, *, journals, years):
        """Bir sətrin slot həlli: (uniqid, tarix, saat) və ya natamam hissələr."""

        journal = journals.get(legacy_int(row["journal_id"]))
        if journal is None:
            return None, None
        uniqid, semester_ref = journal
        first_year = years.get(semester_ref)
        if first_year is None:
            return uniqid, None
        schedule = parse_lesson_schedule(
            first_year=first_year, month=row["month"], day=row["day"], time_value=row["time"]
        )
        return uniqid, schedule

    def _lesson_entries(self, *, legacy_pk, row, journals, years, slices, claimed_slots, recorded):
        """Bir legacy dərs sətri → jurnalın HƏR dilimə bir möhür (2026-08-28).

        Orphan/invalid hallar jurnal-səviyyədir (möhür açarı ``<legacy_pk>``),
        materiallaşan dərs isə dilim başına ayrıca möhür alır
        (``<legacy_pk>:<qrup>``).  Dublikat slotu artıq AÇILIŞ üzrə tutulur:
        C6 birləşməsində iki jurnal eyni açılışı bölüşürsə ikincinin eyni
        gün/saatı ``legacy_journal_lesson_duplicate`` olur — hədəfdə tək dərs.
        """

        row_hash = source_row_hash(contract=JOURNAL_DATES_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        journal_ref = str(legacy_int(row["journal_id"]))
        journal = journals.get(legacy_int(row["journal_id"]))
        pairs = slices.slice_pairs(journal[0]) if journal is not None else ()
        journal_key = str(legacy_pk)
        if not pairs:
            # Spec J3: jurnal tapılmır VƏ YA V6/karantinlə süzülüb — orphan.
            previous = recorded.get(journal_key)
            yield journal_key, (
                previous
                if previous is not None
                else skipped_decision(
                    legacy_pk=legacy_pk,
                    row_hash=row_hash,
                    rule_code="legacy_journal_lesson_orphan",
                    outcome_token="orphan",
                    journal_ref=journal_ref,
                )
            )
            return

        _uniqid, schedule = self._resolved_slot(row, journals=journals, years=years)
        if schedule is None:
            previous = recorded.get(journal_key)
            yield journal_key, (
                previous
                if previous is not None
                else invalid_decision(legacy_pk=legacy_pk, row_hash=row_hash, journal_ref=journal_ref)
            )
            return

        lesson_date, lesson_time = schedule
        date_text = lesson_date.isoformat()
        time_text = lesson_time.isoformat(timespec="minutes")
        for group_ref, offering_pk in pairs:
            seal_key = f"{legacy_pk}:{group_ref}"
            slot = (offering_pk, date_text, time_text)
            previous = recorded.get(seal_key)
            if previous is not None:
                if previous[0] == _STATE.MIGRATED:
                    # Resume olunan MIGRATED sətir də slot açarını tutur ki,
                    # yarımçıq keçiddən sonrakı davam eyni dublikatı tanısın.
                    claimed_slots.add(slot)
                yield seal_key, previous
                continue
            if slot in claimed_slots:
                yield seal_key, skipped_decision(
                    legacy_pk=legacy_pk,
                    row_hash=row_hash,
                    rule_code="legacy_journal_lesson_duplicate",
                    outcome_token="duplicate",
                    journal_ref=journal_ref,
                    date_text=date_text,
                    time_text=time_text,
                    seal_key=seal_key,
                    slice_ref=group_ref,
                )
                continue
            claimed_slots.add(slot)
            yield seal_key, lesson_decision(
                request=LessonRequest(
                    legacy_pk=legacy_pk,
                    seal_key=seal_key,
                    slice_ref=group_ref,
                    row_hash=row_hash,
                    offering_pk=offering_pk,
                    journal_ref=journal_ref,
                    date=lesson_date,
                    start_time=lesson_time,
                )
            )
