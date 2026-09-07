"""J4-J8-in paylaşdığı mənbə qatı: ``journals_dates_points`` (+ arxiv) oxunuşu.

Yalnız oxumaq, parse etmək və indeks qurmaq burada yaşayır — heç bir hədəf
yazısı yoxdur.  Üç faza (J4 marks, J5 components, J6 finals) EYNİ cədvəli eyni
audited kontraktla READ-ONLY axıdır; J8 isə eyni klassifikatorlarla yalnız
sayır.  ``month_id`` dəyəri sətri hədəfə bölür:

* ``01``-``12`` təqvim ayı  → ``registrar.LessonMark``      (J4)
* ``k1``/``k2``/``k3``/``si`` → ``AssessmentComponent``      (J5)
* ``im`` / ``im2``           → ``FinalGrade`` / ``ResitRecord`` (J6)
* qalan hər şey (pa/wr/ss/ww/ll/rr/ga)  → karantin (J-V13)

J-V7 arxivi: ``journals_dates_points_archive`` YALNIZ ``added_date`` 2022-03-30-dan
ƏVVƏL olan sətirlər üçün mənbədir.  Canlı mənbə faktı: əsas cədvəlin ən köhnə
``added_date``-i 2022-03-30 05:54:57-dir, yəni kəsim məhz iki cədvəlin sərhədidir.
Kəsimdən sonrakı arxiv sətirləri (overlap) İNFO ilə hesabata düşür və İDXAL
EDİLMİR — "əsas cədvəl udur" qaydası.  Kəsimdən əvvəlki sətir isə hədəf xanası
ARTIQ mövcuddursa yenə əsas cədvələ güzəşt edir (yazı heç vaxt üstündən yazmır).

Arxiv cədvəli plan-da ``archive_gated``-dir: ona görə HEÇ BİR faza onu batch
zəncirinə İDDİA ETMİR (``source_tables = ()``).  Gated olmaq iddiaya, oxumağa
yox, qadağa qoyur (bax ``rehearsal_contracts`` seam qeydi).
"""

from __future__ import annotations

import datetime

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation

from .cell_election import CellElection, elect_winners  # noqa: F401 - public compatibility re-export
from .field_contracts import (
    ALLOWED_QB_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    YEKUN_FIELDS,
)
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import LegacyRehearsalEvidenceError, RehearsalContext
from .source_extraction import open_audited_source_stream

POINT_SOURCE_TABLE = JOURNAL_POINT_FIELDS.source_table
POINT_ARCHIVE_TABLE = JOURNAL_POINT_ARCHIVE_FIELDS.source_table
ALLOWED_QB_TABLE = ALLOWED_QB_FIELDS.source_table
YEKUN_TABLE = YEKUN_FIELDS.source_table

# J-V7 kəsimi — arxiv yalnız BU tarixdən ƏVVƏLKİ sətirlər üçün mənbədir.
ARCHIVE_CUTOFF = datetime.date(2022, 3, 30)

PRESENT_TOKEN = "ie"  # J-V1(F): "İŞTİRAK EDİR"
ABSENT_TOKEN = "qb"
CALENDAR_MONTHS = frozenset(f"{month:02d}" for month in range(1, 13))
KOLLOKVIUM_MONTHS = ("k1", "k2", "k3")
SELF_WORK_MONTH = "si"
EXAM_MONTH = "im"
RESIT_MONTH = "im2"
COMPONENT_MONTHS = frozenset((*KOLLOKVIUM_MONTHS, SELF_WORK_MONTH))
FINAL_MONTHS = frozenset((EXAM_MONTH, RESIT_MONTH))

# J-V2: şkala çevirməsi YOXDUR — bunlar yalnız "bu dəyər ümumiyyətlə bu sahəyə
# sığırmı" qapılarıdır.  Sığmayan dəyər karantinə düşür, TƏHRİF EDİLMİR.
MARK_SCORE_MAX = 10  # gündəlik seminar/lab balı (LessonMark.score)
COMPONENT_SCORE_MAX = 10  # kollokvium/sərbəst iş komponenti (journal_extras.KOLLOKVIUM_MAX)
FINAL_SCORE_MAX = 100  # FinalGrade.exam_score / ResitRecord.resit_score sahə tavanı
EXAM_SCHEME_SCORE_MAX = 50  # AssessmentScheme defoltu (100 - entry_score_max)

# Ledger indeksləri jurnal klasterində on minlərlə sətirdir (J3 tək başına
# 379,215 dərs yazır), ona görə identity kohortunun 20k qapağı burada keçmir.
JOURNAL_INDEX_MAX_ROWS = 2_000_000
# Dublikat namizəd buferi: prefiltr yalnız SÜPERÇOXLUQ verir, qapaq isə
# yaddaşı bağlayır (aşarsa fazanın özü fail-closed olur).
MAX_DUPLICATE_CANDIDATES = 500_000

_STATE = LegacyEntityMap.State
_ELECTION_PREFIX = b"legacy-rehearsal-journal-cell-v1\x00"


def legacy_text(value: object) -> str:
    """Legacy mətn sütunu; ``NULL`` MySQL-in yazdığı eyni boş sentinelidir."""

    if value is None:
        return ""
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def legacy_flag(value: object) -> int:
    """``int(1)`` bayrağı; bool/mətn fail-closed qalır (A-2 qaydası)."""

    if value is None:
        return 0
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def normalized_time(value: object) -> str:
    """``TIME`` sütununu "HH:MM"-ə çevir; qurula bilməsə boş mətn.

    MariaDB ``TIME``-ı ``timedelta`` kimi qaytarır (24 saatı aşan dəyər legaldır
    və o zaman heç bir dərs slotuna uyğun gəlmir → boş mətn = həll olunmadı).
    """

    if type(value) is datetime.timedelta:
        seconds = int(value.total_seconds())
        if seconds < 0 or seconds >= 24 * 3600:
            return ""
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"
    if type(value) is datetime.time:
        return value.isoformat(timespec="minutes")
    if type(value) is str and len(value) >= 5 and value[2] == ":":
        head = value[:5]
        try:
            datetime.time.fromisoformat(head)
        except ValueError:
            return ""
        return head
    return ""


def parse_cell_score(text: str):
    """``point`` sütunundan tam bal; rəqəm deyilsə ``None``.

    Legacy sütun ``varchar(3)``-dür və yalnız işarəsiz onluq rəqəmlər daşıyır;
    hər hansı başqa forma (``ie``/``qb``/``l``/boşluq) burada ``None``-dur və
    çağıran onu öz nərdivanında ayırır.
    """

    return int(text) if text.isdigit() else None


def calendar_slot(month_id: str, day_number: str):
    """``('04','17')`` → ``(4, 17)``; təqvim forması pozulubsa ``None``."""

    if month_id not in CALENDAR_MONTHS or not day_number.isdigit():
        return None
    day = int(day_number)
    return (int(month_id), day) if 1 <= day <= 31 else None


def cell_key(row) -> tuple[str, str, str, int, str]:
    """J-V4 dedup açarı: jurnal + ay + gün + tələbə + saat."""

    return (
        legacy_text(row["journal_uniqid"]),
        legacy_text(row["month_id"]),
        legacy_text(row["day_number"]),
        _legacy_pk_value(row["student_id"]),
        normalized_time(row["time"]),
    )


def cell_rank(row, legacy_pk: int) -> tuple[int, str, int]:
    """J-V4 qalib sıralaması: ən böyük ``update_counter`` → ən son
    ``updated_at`` → ən böyük ``id``."""

    updated_at = row["updated_at"]
    if updated_at is None:
        updated_text = ""
    elif type(updated_at) is datetime.datetime:
        updated_text = updated_at.isoformat()
    else:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return (legacy_flag(row["update_counter"]), updated_text, legacy_pk)


def added_on(row) -> datetime.date | None:
    """``added_date`` sütununun tarix hissəsi (J-V7 kəsimi üçün)."""

    value = row["added_date"]
    if type(value) is datetime.datetime:
        return value.date()
    if type(value) is datetime.date:
        return value
    return None


def _legacy_pk_value(value: object) -> int:
    if value is None:
        return 0
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def attested_rows(context: RehearsalContext, *, contract, source_table: str):
    """Bir jurnal cədvəlini attested, ciddi artan primary-key sırasında axıt."""

    entry = context.plan.entry_for(source_table)
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


def point_rows(context: RehearsalContext):
    return attested_rows(context, contract=JOURNAL_POINT_FIELDS, source_table=POINT_SOURCE_TABLE)


def archive_rows(context: RehearsalContext):
    return attested_rows(context, contract=JOURNAL_POINT_ARCHIVE_FIELDS, source_table=POINT_ARCHIVE_TABLE)


def yekun_rows(context: RehearsalContext):
    return attested_rows(context, contract=YEKUN_FIELDS, source_table=YEKUN_TABLE)


def migrated_index(context: RehearsalContext, entity_type: str) -> dict[str, str]:
    """BU run-un MIGRATED hədəfləri: ``legacy_pk`` → ``target_pk`` (§3.9).

    ``rehearsal_journal_offerings_source.migrated_target_index`` ilə eyni
    invariant, amma jurnal klasterinin ölçüsünə uyğun qapaqla: dərs və qeydiyyat
    indeksləri identity kohortundan (20k) iki tərtib böyükdür.
    """

    index: dict[str, str] = {}
    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id,
        state=_STATE.MIGRATED,
        entity_map__entity_type=entity_type,
    ).values_list("entity_map__legacy_pk", "target_pk")
    for legacy_pk, target_pk in rows.iterator(chunk_size=10_000):
        index[legacy_pk] = target_pk
        if len(index) > JOURNAL_INDEX_MAX_ROWS:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_cohort_too_large")
    return index


def lesson_slot_index(context: RehearsalContext, slices) -> dict[tuple[str, int, int, str], tuple[str, datetime.date]]:
    """``(açılış pk, ay, gün, "HH:MM")`` → ``(lesson_pk, dərs tarixi)``.

    J3-ün öz axını (``journals_dates_added_by_teacher``) və öz ledger xəritəsi
    birləşdirilir: beləliklə J4 registrar cədvəlinə heç bir sorğu vermir və
    dərsin TÖRƏDİLMİŞ ilini (J-V3 üzürlü qaib pəncərəsi üçün lazımdır) J3 ilə
    EYNİ funksiya ilə alır.  J3-də dublikat slot SKIPPED olduğundan xəritədə
    yalnız qalib sətir görünür — açar isə hər iki halda eynidir.

    2026-08-28 (qrup-başına jurnal): açarın birinci hissəsi artıq ``uniqid``
    deyil, AÇILIŞ pk-sıdır — tələbənin xanası öz qrupunun dərsinə bağlanmalıdır,
    qonşu qrupun eyni gün/saatlı dərsinə yox.
    """

    from .rehearsal_journal_lessons_phase import journal_index, parse_lesson_schedule, semester_year_index
    from .rehearsal_journal_lessons_targets import LESSON_ENTITY_TYPE, LESSON_SOURCE_TABLE
    from .rehearsal_journal_offerings_source import legacy_int

    years = semester_year_index(context)
    journals = journal_index(context)
    lessons = migrated_index(context, LESSON_ENTITY_TYPE)
    index: dict[tuple[str, int, int, str], tuple[str, datetime.date]] = {}
    for legacy_pk, row in attested_rows(context, contract=JOURNAL_DATES_FIELDS, source_table=LESSON_SOURCE_TABLE):
        journal = journals.get(legacy_int(row["journal_id"]))
        if journal is None:
            continue
        first_year = years.get(journal[1])
        if first_year is None:
            continue
        schedule = parse_lesson_schedule(
            first_year=first_year, month=row["month"], day=row["day"], time_value=row["time"]
        )
        if schedule is None:
            continue
        lesson_date, lesson_time = schedule
        time_text = lesson_time.isoformat(timespec="minutes")
        for group_ref, offering_pk in slices.slice_pairs(journal[0]):
            lesson_pk = lessons.get(f"{legacy_pk}:{group_ref}", "")
            if not lesson_pk:
                continue  # orphan/invalid/dublikat — J3 onsuz da möhürləyib
            key = (offering_pk, lesson_date.month, lesson_date.day, time_text)
            index.setdefault(key, (lesson_pk, lesson_date))
    return index


def allowed_absence_windows(context: RehearsalContext) -> dict[int, tuple[tuple[datetime.date, datetime.date], ...]]:
    """J-V3: ``allowed_qb`` pəncərələri — tələbə → (başlanğıc, son) aralıqları.

    Sxemdə FK yoxdur (``uniq`` sütunu jurnal uniqid-i DEYİL — canlı mənbədə
    ``journals`` ilə 0 uyğunluq verir, yəni sənəd paketinin öz açarıdır), ona
    görə qayda TARİX-ARALIĞI üzərindən tətbiq olunur.
    """

    windows: dict[int, list[tuple[datetime.date, datetime.date]]] = {}
    for _legacy_pk, row in attested_rows(context, contract=ALLOWED_QB_FIELDS, source_table=ALLOWED_QB_TABLE):
        start = _window_date(row["allowed_date_start"])
        end = _window_date(row["allowed_date_end"])
        if start is None or end is None or end < start:
            continue  # yararsız pəncərə heç kimi üzürlü etmir (data qorunur)
        windows.setdefault(_legacy_pk_value(row["student_id"]), []).append((start, end))
    return {student: tuple(sorted(items)) for student, items in windows.items()}


def _window_date(value: object) -> datetime.date | None:
    if type(value) is datetime.datetime:
        return value.date()
    if type(value) is datetime.date:
        return value
    return None


def is_excused(*, excusable: int, student_id: int, lesson_date, windows) -> bool:
    """J-V3: ``excusable=1`` VƏ YA ``allowed_qb`` pəncərəsinə düşən qayıb."""

    if excusable == 1:
        return True
    if lesson_date is None:
        return False
    return any(start <= lesson_date <= end for start, end in windows.get(student_id, ()))
