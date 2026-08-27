"""J9-un mənbə qatı: ``sillabus`` körpüsü + ``sillabus_serbest_is`` mövzuları.

Yalnız oxumaq, təmizləmək və indeks qurmaq burada yaşayır — heç bir hədəf
yazısı yoxdur (``rehearsal_journal_points_source`` ilə eyni bölgü).

Zəncir (⚠️ ``sillabus_serbest_is.uniqid`` JURNAL uniqid-i DEYİL)::

    journals.sillabus_id → sillabus.id → sillabus.uniqid → sillabus_serbest_is.uniqid

Mövzu sırası mənbənin ``id`` sırasıdır — MariaDB PK sırasında axıdılır, yəni
eyni dump iki dəfə oxunanda eyni sıra çıxır (determinizm).  Mövzu mətnində
onsuz da "1. ", "3. " kimi nömrə prefiksləri var; onlar OLDUĞU KİMİ saxlanılır,
çünki mənbənin öz nömrələməsi bəzən boşluqlu (1,3,4,6,10…) olur və onu
"düzəltmək" tarixi faktı dəyişmək olardı.

Tavan (``SELF_WORK_MAX_TOPICS`` = 10) hədəfin müqaviləsidir, seçim deyil:
``journal_extras.get_selfwork_board`` cədvəli HƏMİŞƏ 10 sabit slotla qurur və
``AssessmentComponent(self_work).max_score`` da 10-dur.  Mənbədə isə bir
sillabusa 337 mövzuya qədər sətir var (orta 7.37) — 10-dan sonrakılar hədəfdə
onsuz da görünməzdi, ona görə kəsilir və kəsim İNFO ilə hesabata düşür.
"""

from __future__ import annotations

from dataclasses import dataclass

from .legacy_text import clean_text
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import LegacyRehearsalEvidenceError, RehearsalContext
from .rehearsal_journal_offerings_source import legacy_int, validated_uniqid
from .source_extraction import open_audited_source_stream
from .syllabus_field_contracts import (
    JOURNAL_SYLLABUS_FIELDS,
    SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS,
)

SYLLABUS_SOURCE_TABLE = SILLABUS_FIELDS.source_table
SELF_WORK_SOURCE_TABLE = SILLABUS_SELF_WORK_FIELDS.source_table
JOURNAL_SOURCE_TABLE = JOURNAL_SYLLABUS_FIELDS.source_table

# ``journal_extras`` sabitlərinin güzgüsü — ad, tavan və sütun sayı EYNİ olmalıdır.
SELF_WORK_MAX_TOPICS = 10
#: ``registrar.SelfWorkTopic.title`` sütununun eni.
MAX_TITLE_LENGTH = 255


@dataclass(frozen=True)
class SelfWorkTopicRow:
    """Bir sərbəst iş mövzusunun distillə olunmuş, hədəfə hazır forması."""

    legacy_pk: int
    title: str
    placeholder: bool
    truncated: bool


@dataclass(frozen=True)
class SyllabusTopicIndex:
    """Sillabus uniqid → (kəsilmiş mövzu siyahısı, mənbədəki tam say)."""

    topics: dict[str, tuple[SelfWorkTopicRow, ...]]
    source_counts: dict[str, int]

    def for_syllabus(self, syllabus_uniqid: str) -> tuple[SelfWorkTopicRow, ...]:
        return self.topics.get(syllabus_uniqid, ())

    def overflow_for(self, syllabus_uniqid: str) -> int:
        """Tavandan artıq qalan (yəni köçürülməyən) mövzu sayı."""

        return max(0, self.source_counts.get(syllabus_uniqid, 0) - SELF_WORK_MAX_TOPICS)


def _validated_pk(value: object) -> int:
    """``pk_inventory._row_pk`` ilə eyni: heç bir coercion, fail closed."""

    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
    if not 1 <= value <= MAX_LEDGER_PRIMARY_KEY:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
    return value


def _attested_rows(context: RehearsalContext, contract):
    """Bir audited kontraktı ciddi artan PK sırasında axıt + sayı planla tut."""

    entry = context.plan.entry_for(contract.source_table)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=contract,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = _validated_pk(projected_row["id"])
            if legacy_pk <= previous_pk:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
            previous_pk = legacy_pk
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
            yield legacy_pk, projected_row
    if observed != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")


def syllabus_uniqid_index(context: RehearsalContext) -> dict[int, str]:
    """``sillabus.id`` → ``sillabus.uniqid`` körpüsü (8,248 sətir).

    Canlı mənbədə uniqid TAM UNİKAL deyil (8,248 sətir, 8,247 fərqli uniqid) —
    ona görə körpü ``id``-dən uniqid-ə tək istiqamətdə qurulur; əks istiqamət
    heç vaxt lazım olmur.
    """

    index: dict[int, str] = {}
    for legacy_pk, row in _attested_rows(context, SILLABUS_FIELDS):
        index[legacy_pk] = validated_uniqid(row["uniqid"])
    return index


def journal_syllabus_index(context: RehearsalContext, *, syllabus_of: dict[int, str]) -> dict[str, str]:
    """Jurnal uniqid → sillabus uniqid.  Bağlanmayan jurnal indeksə DÜŞMÜR.

    ``sillabus_id`` boşdur (0) və ya heç bir ``sillabus`` sətrinə düşmürsə
    jurnal sadəcə yoxdur — qərarı (İNFO issue) faza verir, mənbə qatı deyil.
    """

    index: dict[str, str] = {}
    for _legacy_pk, row in _attested_rows(context, JOURNAL_SYLLABUS_FIELDS):
        syllabus_uniqid = syllabus_of.get(legacy_int(row["sillabus_id"]))
        if syllabus_uniqid is not None:
            index[validated_uniqid(row["uniqid"])] = syllabus_uniqid
    return index


def _distilled_topic(legacy_pk: int, row, *, ordinal: int) -> SelfWorkTopicRow:
    """Mətni təmizlə; boş addan nömrələnmiş yer tutucu düzəlt."""

    title, truncated = clean_text(row["name"], max_length=MAX_TITLE_LENGTH)
    if title:
        return SelfWorkTopicRow(legacy_pk=legacy_pk, title=title, placeholder=False, truncated=truncated)
    # Mənbədəki 60,878 sətrin 2,572-sinin adı boşdur.  Sətri atmaq sıranı
    # sürüşdürərdi (mövzu 3 birdən mövzu 2 olardı), ona görə yer tutucu qalır.
    return SelfWorkTopicRow(
        legacy_pk=legacy_pk,
        title=f"Sərbəst iş {ordinal}",
        placeholder=True,
        truncated=False,
    )


def self_work_topic_index(context: RehearsalContext, *, wanted: frozenset[str]) -> SyllabusTopicIndex:
    """Yalnız İSTƏNİLƏN sillabus uniqid-ləri üçün ≤10 mövzuluq indeks.

    ``wanted`` bir jurnala bağlı sillabus uniqid-lərinin dəstidir; qalan
    sətirlər oxunur, sayılır və dərhal atılır — yaddaşda ən çoxu
    ``len(wanted) × 10`` mövzu qalır.
    """

    topics: dict[str, list[SelfWorkTopicRow]] = {}
    source_counts: dict[str, int] = {}
    for legacy_pk, row in _attested_rows(context, SILLABUS_SELF_WORK_FIELDS):
        syllabus_uniqid = validated_uniqid(row["uniqid"])
        if syllabus_uniqid not in wanted:
            continue
        seen = source_counts.get(syllabus_uniqid, 0) + 1
        source_counts[syllabus_uniqid] = seen
        if seen > SELF_WORK_MAX_TOPICS:
            continue  # tavandan artığı yaddaşda saxlamırıq, yalnız sayırıq
        topics.setdefault(syllabus_uniqid, []).append(_distilled_topic(legacy_pk, row, ordinal=seen))
    return SyllabusTopicIndex(
        topics={key: tuple(value) for key, value in topics.items()},
        source_counts=source_counts,
    )


__all__ = [
    "JOURNAL_SOURCE_TABLE",
    "MAX_TITLE_LENGTH",
    "SELF_WORK_MAX_TOPICS",
    "SELF_WORK_SOURCE_TABLE",
    "SYLLABUS_SOURCE_TABLE",
    "SelfWorkTopicRow",
    "SyllabusTopicIndex",
    "journal_syllabus_index",
    "self_work_topic_index",
    "syllabus_uniqid_index",
]
