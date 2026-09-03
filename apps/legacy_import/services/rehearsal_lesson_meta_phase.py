"""Phase: ``journal_lesson_meta`` (J11) — dərsin MÖVZUSU, OTAĞI və SAATI.

Niyə var (sahib şikayəti, 2026-08-30): köhnə sistemdə hər gün dərs əlavə
olunanda mövzu, otaq və korpus da yazılırdı; hədəfə köçən 293,070 dərsin isə
``topic``-i və ``room_id``-si TAM BOŞ, ``hours``-u isə hamısında sabit 2 idi.

Niyə J3-ün ÖZÜ genişləndirilmir
-------------------------------
J3-ün möhür resepti ``JOURNAL_DATES_FIELDS.fingerprint``-i daşıyır; həmin
kontrakta bir sütun əlavə etmək artıq möhürlənmiş repetisiyaların ledger-ini
yenidən törədilməz edərdi (2026-08-30-da ``YEKUN_FIELDS`` ilə məhz bu baş
verdi).  Metadata başqa CƏDVƏLdən (``journals_dates_rooms``) gəlir, yəni onu
J3-ə qatmaq üçün heç bir texniki səbəb də yoxdur.  Ona görə J9 presedenti
təkrarlanır: YENİ dar kontraktlar (``lesson_meta_field_contracts``) + AYRICA
faza + öz möhür nəsli.  J3-ün heç bir sətri dəyişmir.

Niyə sıra 39
------------
J3-dən (38) SONRA — dərs sətri artıq hədəfdə olmalıdır; J4-dən
(``journal_marks``, 40) ƏVVƏL — J4 sonunda ``recompute_absence_hours``
işləyir və qayıb saatını ``Lesson.hours`` cəmi kimi hesablayır.  Saat düzəlişi
o hesablamadan qabaq oturmasa, saxta qayıb blokları qalardı.

Birləşdirmə açarı (ölçülmüş)
----------------------------
``journals_dates_rooms`` ilə dərs sətri EYNİ slot açarını daşıyır:
``(journal_id, month, day, times)``.  Bu faza dərs cədvəlini YENİDƏN OXUMUR —
slotu birbaşa metadata sətrindən qurub J3-ün öz tarix törəməsi ilə
(``parse_lesson_schedule``: akademik il semestrdən) hədəf dərsini tapır, yəni
iki faza eyni açardan çıxır və bir-birindən sürüşə bilmir.

Canlı ölçü (rehearsal dump, 2026-08-30), ``fake=0`` sətirlər üzrə:

* 265,206 metadata sətri → 265,176 fərqli slot açarı;
* yalnız **28** açarda 2+ sətir var → hamısı ``legacy_lesson_meta_ambiguous``
  ilə fail-closed atlanır (mənbədə seçim üçün heç bir siqnal yoxdur);
* dərs cədvəli tərəfindən baxanda: 325,531 sətir birmənalı uyğunlaşır, 55-i
  ambiqü, 53,629-u uyğunsuz qalır (``fake`` süzgəci olmadan uyğunsuzluq
  23,928-ə düşür — yəni 29,701 dərs YALNIZ ``fake=1`` metadata sətrinə düşür və
  mövcud ``fake`` süzgəci qaydasına uyğun olaraq metadata almır).

Bir metadata sətri jurnalın HƏR dilimə (J-V7 qrup-başına jurnal) təkrarlanır,
ona görə möhür açarı J3-dəki kimi ``<legacy_pk>:<qrup>``dur; sətir-səviyyə
qərarlar (fake / orphan / ambiqü / invalid) isə ``<legacy_pk>`` açarındadır.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType

from apps.legacy_import.models import LegacyEntityMap

from .lesson_meta_field_contracts import LESSON_ROOM_FIELDS
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    source_row_hash,
)
from .rehearsal_journal_lessons_phase import (
    JOURNAL_LESSONS_PHASE_KEY,
    journal_index,
    parse_lesson_schedule,
    semester_year_index,
)
from .rehearsal_journal_offerings_phase import JOURNAL_OFFERINGS_PHASE_KEY
from .rehearsal_journal_offerings_source import migrated_target_index
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_periods_phase import JOURNAL_PERIODS_PHASE_KEY
from .rehearsal_journal_slices import build_offering_slices
from .rehearsal_lesson_meta_source import (
    legacy_calendar_int,
    legacy_lesson_hours,
    lesson_meta_rows,
    slot_text,
    syllabus_topic_index,
)
from .rehearsal_lesson_meta_targets import (
    AMBIGUOUS_RULE_CODE,
    FAKE_RULE_CODE,
    INVALID_RULE_CODE,
    LESSON_META_ENTITY_TYPE,
    LESSON_META_SEALER,
    ORPHAN_RULE_CODE,
    ROOM_MISSING_RULE_CODE,
    TOPIC_MISSING_RULE_CODE,
    TOPIC_TRUNCATED_RULE_CODE,
    LessonMetaRequest,
    LessonMetaWriter,
    resolved_entry,
)
from .rehearsal_lesson_rooms_phase import LEGACY_ROOM_ENTITY_TYPE, LEGACY_ROOMS_PHASE_KEY
from .rehearsal_structure_phase import probe_cancellation

JOURNAL_LESSON_META_PHASE_KEY = "journal_lesson_meta"
JOURNAL_LESSON_META_PHASE_ORDER = 39  # journal_lessons (38) ilə journal_marks (40) arasında
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-lesson-meta-v1"
REQUIRED_PHASE_KEYS = frozenset(
    {
        JOURNAL_PERIODS_PHASE_KEY,
        JOURNAL_OFFERINGS_PHASE_KEY,
        JOURNAL_LESSONS_PHASE_KEY,
        LEGACY_ROOMS_PHASE_KEY,
    }
)

_STATE = LegacyEntityMap.State

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "lesson_meta_written",
        _STATE.SKIPPED: "lesson_meta_skipped",
        _STATE.QUARANTINED: "lesson_meta_unresolved",
    }
)


def source_slot(row) -> str:
    """Metadata sətrinin slot açarı; ``times`` mətn deyilsə boş hissə qalır."""

    time_value = row["times"]
    return slot_text(
        journal_ref=legacy_calendar_int(row["journal_id"]),
        month=legacy_calendar_int(row["month"]),
        day=legacy_calendar_int(row["day"]),
        time_value=time_value if type(time_value) is str else "",
    )


def ambiguous_slots(context: RehearsalContext) -> frozenset[str]:
    """Birinci keçid: 2+ ``fake=0`` sətrin iddia etdiyi slot açarları.

    Ambiqüllük ancaq BÜTÜN cədvəl görüldükdən sonra bilinir, ona görə mənbə iki
    dəfə oxunur (J9 da üç keçid edir).  «Birinci sətir udur» qaydası burada
    QƏSDƏN tətbiq olunmur: dərs cədvəlində dublikat sətirlər eyni dərsi
    təkrarlayır, metadata sətirləri isə FƏRQLİ otaq/mövzu/saat daşıya bilər —
    birini seçmək üçün mənbədə əsas yoxdur, ona görə fail-closed atlanır.
    """

    seen: set[str] = set()
    repeated: set[str] = set()
    for _legacy_pk, row in lesson_meta_rows(context):
        if legacy_calendar_int(row["fake"]):
            continue
        key = source_slot(row)
        if key in seen:
            repeated.add(key)
        else:
            seen.add(key)
    return frozenset(repeated)


class JournalLessonMetaPhase:
    """J11: mövzu/otaq/saat metadatasının mövcud dərs sətirlərinə yazılması."""

    phase_key = JOURNAL_LESSON_META_PHASE_KEY
    order = JOURNAL_LESSON_META_PHASE_ORDER
    source_tables = ()
    entity_types = (LESSON_META_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook
    # Möhür açarı həm ``<pk>``, həm ``<pk>:<qrup>`` ola bilir → LEKSİKOQRAFİK.
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

        index = _MetaIndex(context)
        writer = LessonMetaWriter(context)
        claimed: set[str] = set()
        for legacy_pk, row in lesson_meta_rows(context):
            probe_cancellation(context)
            self._consume(writer, legacy_pk=legacy_pk, row=row, index=index, claimed=claimed)
        writer.flush()

        decisions = list(index.recorded.items())
        decisions.extend(writer.sealed)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        for seal_key, (state, digest, label) in sorted(decisions, key=lambda item: item[0]):
            chain.advance(seal_key, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_LESSON_META_PHASE_KEY}.records.{sum(state_counts.values())}")
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

    # ── Qərar qatı ──────────────────────────────────────────────────────────

    def _consume(self, writer, *, legacy_pk, row, index, claimed) -> None:
        """Bir metadata sətri → sətir-səviyyə qərar VƏ YA dilim-başına yazı."""

        row_key = str(legacy_pk)
        row_hash = source_row_hash(contract=LESSON_ROOM_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        journal_ref = legacy_calendar_int(row["journal_id"])
        parts = (f"row={row_hash}", f"journal={journal_ref}")

        rejection = index.row_rejection(row, journal_ref=journal_ref)
        if rejection is not None:
            outcome, code, quarantined = rejection
            if row_key not in index.recorded:
                writer.add_resolved(
                    resolved_entry(
                        seal_key=row_key,
                        outcome=outcome,
                        parts=parts,
                        rule_codes=(code,),
                        quarantined=quarantined,
                    )
                )
            return

        journal = index.journals[journal_ref]
        schedule = index.schedule_for(row, journal=journal)
        if schedule is None:
            if row_key not in index.recorded:
                # J3-ün ``invalid_decision``-ı ilə eyni ruh: anlaşılmayan tarix/saat
                # KARANTİN-dir, "yazılası bir şey yox idi" (skip) deyil.
                writer.add_resolved(
                    resolved_entry(
                        seal_key=row_key,
                        outcome="invalid",
                        parts=parts,
                        rule_codes=(INVALID_RULE_CODE,),
                        quarantined=True,
                    )
                )
            return

        lesson_date, lesson_time = schedule
        date_text = lesson_date.isoformat()
        time_text = lesson_time.isoformat(timespec="minutes")
        payload = index.payload_for(row)
        for group_ref, offering_pk in index.slices.slice_pairs(journal[0]):
            seal_key = f"{legacy_pk}:{group_ref}"
            slot_claim = f"{offering_pk}|{date_text}|{time_text}"
            previous = index.recorded.get(seal_key)
            if previous is not None:
                if previous[0] == _STATE.MIGRATED:
                    # Resume: möhürlənmiş sətir slotu TUTUR ki, davam eyni
                    # hədəfə ikinci dəfə yazmasın (J3-ün eyni qaydası).
                    claimed.add(slot_claim)
                continue
            request = LessonMetaRequest(
                seal_key=seal_key,
                slice_ref=group_ref,
                row_hash=row_hash,
                journal_ref=str(journal_ref),
                offering_pk=offering_pk,
                date=lesson_date,
                start_time=lesson_time,
                date_text=date_text,
                time_text=time_text,
                **payload,
            )
            if slot_claim in claimed:
                # C6 birləşməsində iki jurnal eyni açılışı bölüşür və hədəfdə
                # TƏK dərs var: ikinci metadata sətrinin dəyərləri fərqli ola
                # bilər, ona görə seçim edilmir.
                writer.add_resolved(
                    resolved_entry(
                        seal_key=seal_key,
                        outcome="target_claimed",
                        parts=request.digest_parts(),
                        rule_codes=(AMBIGUOUS_RULE_CODE,),
                    )
                )
                continue
            claimed.add(slot_claim)
            writer.add(request)


class _MetaIndex:
    """Fazanın bütün oxu indeksləri — bir yerdə qurulur, sonra saf sorğu olur."""

    __slots__ = ("years", "journals", "slices", "rooms", "topics", "ambiguous", "recorded")

    def __init__(self, context: RehearsalContext) -> None:
        self.years = semester_year_index(context)
        self.journals = journal_index(context)
        self.slices = build_offering_slices(context, migrated_target_index(context, COURSE_OFFERING_ENTITY_TYPE))
        self.rooms = migrated_target_index(context, LEGACY_ROOM_ENTITY_TYPE)
        self.topics = syllabus_topic_index(context)
        probe_cancellation(context)
        self.ambiguous = ambiguous_slots(context)
        self.recorded = LESSON_META_SEALER.recorded_decisions(context)

    def row_rejection(self, row, *, journal_ref: int):
        """Sətir-səviyyə rədd: ``(outcome, kod, karantin?)`` və ya ``None``."""

        if legacy_calendar_int(row["fake"]):
            return "fake", FAKE_RULE_CODE, False
        journal = self.journals.get(journal_ref)
        if journal is None or not self.slices.slice_pairs(journal[0]):
            return "orphan", ORPHAN_RULE_CODE, False
        if source_slot(row) in self.ambiguous:
            return "ambiguous", AMBIGUOUS_RULE_CODE, False
        return None

    def schedule_for(self, row, *, journal):
        """J3-ün öz tarix törəməsi — hədəf dərsi məhz bu cütlə açarlanır."""

        first_year = self.years.get(journal[1])
        if first_year is None:
            return None
        return parse_lesson_schedule(
            first_year=first_year,
            month=legacy_calendar_int(row["month"]),
            day=legacy_calendar_int(row["day"]),
            time_value=row["times"],
        )

    def payload_for(self, row) -> dict:
        """Mövzu/otaq/saat + onları müşayiət edən İNFO taksonomiyası."""

        codes: list[str] = []
        topic_entry = self.topics.get(legacy_calendar_int(row["sillabus"]))
        if topic_entry is None:
            topic = ""
            codes.append(TOPIC_MISSING_RULE_CODE)
        else:
            topic, truncated = topic_entry
            if truncated:
                codes.append(TOPIC_TRUNCATED_RULE_CODE)
        room_ref = legacy_calendar_int(row["room"])
        room_pk = self.rooms.get(str(room_ref), "")
        if not room_pk:
            codes.append(ROOM_MISSING_RULE_CODE)
        hours, hours_code = legacy_lesson_hours(row["saatliq_ders"])
        if hours_code:
            codes.append(hours_code)
        return {
            "topic": topic,
            "room_pk": room_pk,
            "room_ref": str(room_ref),
            "hours": hours,
            "rule_codes": tuple(codes),
        }


__all__ = [
    "DERIVED_DIGEST_NAMESPACE",
    "JOURNAL_LESSON_META_PHASE_KEY",
    "JOURNAL_LESSON_META_PHASE_ORDER",
    "JournalLessonMetaPhase",
    "ambiguous_slots",
    "source_slot",
]
