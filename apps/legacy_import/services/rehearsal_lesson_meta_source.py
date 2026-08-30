"""J10/J11-in mənbə oxu qatı: otaq reyestri, dərs metadatası, mövzu indeksi.

Bu modul HEÇ NƏ yazmır — yalnız attested axınlar və saf çevirmə funksiyaları.
Üç axının hamısı ``open_audited_source_stream`` ilə, ciddi artan primary-key
sırasında gedir və plan-dakı sətir sayı ilə tutuşdurulur (J0-J3 ilə eyni
fail-closed forma).

Tip qeydi (canlı ``DESCRIBE`` ilə təsdiqli)
------------------------------------------
``journals_dates_rooms.month``/``day``/``saatliq_ders`` sütunları ``float``-dur,
``journals_dates_added_by_teacher``-dəki qarşılıqları isə ``int``.  Ona görə
``rehearsal_journal_offerings_source.legacy_int`` (sərt ``type() is int``)
BURADA İŞLƏMİR və ``legacy_calendar_int`` ayrıca yazılıb: o, tam qiymətli
``float``-u qəbul edir, kəsrli olanı isə fail-closed rədd edir.
"""

from __future__ import annotations

from .legacy_text import clean_text
from .lesson_meta_field_contracts import (
    LESSON_ROOM_FIELDS,
    ROOM_REGISTRY_FIELDS,
    SYLLABUS_TOPIC_FIELDS,
)
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import LegacyRehearsalEvidenceError, RehearsalContext
from .source_extraction import open_audited_source_stream

#: Hədəf ``Lesson.topic`` sütununun eni; mənbə ``movzu`` 500 simvoldur.
TOPIC_MAX_LENGTH = 255
#: Hədəf ``exams.ExamRoom.name`` sütununun eni (canlı ``rooms.name`` ≤ 14).
ROOM_NAME_MAX_LENGTH = 120
#: Bir dərsin ağlabatan akademik saat tavanı — mənbədə ən böyük dəyər 3-dür.
MAX_LESSON_HOURS = 12

#: ``saatliq_ders`` tam ədəd deyil (canlı: 3,926 sətir 0.5).  Hədəf sahəsi
#: ``PositiveSmallIntegerField``-dir, yuvarlaqlaşdırma isə QADAĞANDIR — sətir
#: saatsız keçir və bu kodla işarələnir.
HOURS_FRACTIONAL = "legacy_lesson_meta_hours_fractional"
#: ``saatliq_ders`` diapazondan kənardır (0, mənfi, > 12) — saat yazılmır.
HOURS_INVALID = "legacy_lesson_meta_hours_invalid"


def legacy_calendar_int(value: object) -> int:
    """``float`` sütununu tam ədədə çevir; kəsr fail-closed olur.

    ``None`` MySQL-in yazdığı eyni sıfır sentinelidir (``legacy_int`` ilə eyni
    qayda).  ``bool`` qəsdən rədd olunur: ``type() is int`` yoxlaması bayraqları
    ayırır.
    """

    if value is None:
        return 0
    kind = type(value)
    if kind is int:
        return value
    if kind is float and value.is_integer():
        return int(value)
    raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")


def legacy_lesson_hours(value: object) -> tuple[int, str]:
    """``saatliq_ders`` → ``(saat, issue kodu)``; kəsr YUVARLAQLAŞDIRILMIR.

    Qaytarılan saat ``0`` olduqda çağıran hədəfə HEÇ NƏ yazmır — J3-ün qoyduğu
    dəyər olduğu kimi qalır və sətir issue kodu ilə ledger-də sayılır.
    """

    if value is None:
        return 0, HOURS_INVALID
    kind = type(value)
    if kind is bool or kind not in (int, float):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    if kind is float and not value.is_integer():
        return 0, HOURS_FRACTIONAL
    hours = int(value)
    if not 1 <= hours <= MAX_LESSON_HOURS:
        return 0, HOURS_INVALID
    return hours, ""


def slot_text(*, journal_ref: int, month: int, day: int, time_value: str) -> str:
    """``journals_dates_rooms`` sətrinin slot açarı — mətn, geri parçalanmır."""

    return f"{journal_ref}|{month}|{day}|{time_value}"


def _audited_rows(context: RehearsalContext, contract):
    """Bir audited cədvəli ciddi artan pk sırasında, plan sayğacı ilə axıt."""

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


def room_registry_rows(context: RehearsalContext):
    """``rooms`` cədvəli (158 sətir) — J10-un yeganə mənbəsi."""

    return _audited_rows(context, ROOM_REGISTRY_FIELDS)


def lesson_meta_rows(context: RehearsalContext):
    """``journals_dates_rooms`` cədvəli (291,509 sətir) — J11-in mənbəsi."""

    return _audited_rows(context, LESSON_ROOM_FIELDS)


def syllabus_topic_index(context: RehearsalContext) -> dict[int, tuple[str, bool]]:
    """``sillabus_sem_muh.id`` → ``(təmizlənmiş mövzu, kəsilibmi)``.

    Boş mövzu indeksə DÜŞMÜR: onu yazmaq hədəfdə boş sətirdən fərqlənməzdi,
    çağıran isə "mövzu yoxdur" halını ayrıca issue ilə sayır.
    """

    index: dict[int, tuple[str, bool]] = {}
    for legacy_pk, row in _audited_rows(context, SYLLABUS_TOPIC_FIELDS):
        topic, truncated = clean_text(row["movzu"], max_length=TOPIC_MAX_LENGTH)
        if topic:
            index[legacy_pk] = (topic, truncated)
    return index


__all__ = [
    "HOURS_FRACTIONAL",
    "HOURS_INVALID",
    "MAX_LESSON_HOURS",
    "ROOM_NAME_MAX_LENGTH",
    "TOPIC_MAX_LENGTH",
    "legacy_calendar_int",
    "legacy_lesson_hours",
    "lesson_meta_rows",
    "room_registry_rows",
    "slot_text",
    "syllabus_topic_index",
]
