"""Sillabus köçürməsinin MƏNBƏ qatı: başlıq indeksi + 11 peyk axını.

Bu modul HEÇ NƏ yazmır — yalnız attested axınlar, saf çevirmə funksiyaları və
yaddaşda qurulan indekslər (``rehearsal_journal_selfwork_source`` ilə eyni
bölgü).  Bütün axınlar ``open_audited_source_stream`` ilə, ciddi artan
primary-key sırasında gedir və plan-dakı ``expected_rows`` ilə TAM bərabərlik
tələb edir.

⚠️ Sıra MƏNALIDIR
-----------------
Peyklərin sətirləri nömrələnmiş siyahıdır (mövzu 1, mövzu 2, …) — mənbədə isə
sıra yalnız ``id``-dədir (nömrə sütunu YOXDUR).  Axın PK sırasında getdiyinə
görə siyahılar burada göründüyü sıra ilə yığılır; heç bir yerdə çeşidlənmir.
Mətnin öz içindəki "1. ", "3. " prefiksləri OLDUĞU KİMİ saxlanılır (J9 qeydi:
mənbənin nömrələməsi boşluqlu ola bilər, onu "düzəltmək" faktı dəyişmək olardı).

⚠️ ``uniqid`` yeganə bağdır və UNİKAL DEYİL
-------------------------------------------
Peyklərin başlığa yeganə bağı ``uniqid``-dir (yad açar yoxdur).  Canlı mənbədə
8,248 başlıq sətri 8,247 fərqli ``uniqid`` daşıyır: ``htcVEP3we58POdhcgo0q``
həm ``sillabus.id=601`` (active=1), həm ``id=2386`` (active=0) tərəfindən
işlədilir.  Həmin uniqid-in bölmə sətirləri iki başlıq arasında AMBİQÜDÜR, ona
görə ``SyllabusHeaderIndex.ambiguous_uniqids``-ə düşür və HEÇ BİR başlığa
bağlanmır — çərçivənin fail-closed qaydası (ambiqü açar → uydurma yox, DAYAN).

⚠️ İKİ mətn təmizləyicisi — sətir sonu MƏZMUNDUR
------------------------------------------------
Peyklərin ``name`` sütunu ``clean_multiline_text`` ilə təmizlənir, ``movzu`` və
``qeyd`` isə ``clean_text`` ilə.  Bu, zövq məsələsi deyil, ölçülmüş fərqdir:
köhnə redaktor bütöv nömrələnmiş siyahını (ədəbiyyat, qiymətləndirmə, təlim
nəticələri) BİR ``text`` sütununa ``\r\n`` ayırıcısı ilə yazıb — canlı mənbədə
**23,574 sətirdə** sətir sonu var (``sillabus_yoxlama_formasi`` 4,842 ·
``_eldeolunacaq_tecrubeler`` 4,791 · ``_tesviri_ve_meqsedi`` 4,652 ·
``_dersin_islenme_formasi`` 4,574 · ``_derslikler`` 2,508 ·
``_qarsilama_mesaji`` 1,724 · ``_elmi_maraq`` 483).  Onları yastılamaq
``truncated=False`` və issue-suz, yəni TAM SƏSSİZ struktur itkisidir: hədəfin
oxucusu (``apps.syllabus.document._lines``) "\n" üzrə böldüyü üçün tələbə N
ədəbiyyat sətri əvəzinə BİR abzas görərdi.

``movzu``/``qeyd`` isə ``clean_text``-də QALIR — 131,056 sətrin heç birində
sətir sonu YOXDUR (canlı ölçmə), yəni J11 ilə davranış eyni qalır və iki
təmizləyici tək sətirli hər dəyərdə onsuz da eyni nəticə verir.

⚠️ Saat sütunları ``char(5)``-dir
---------------------------------
``muh_saat``/``sem_saat``/``praktiki_saat``/``lab_saat`` rəqəm deyil, MƏTNDİR.
``legacy_hour_cell`` onları fail-closed çevirir: kəsr YUVARLAQLAŞDIRILMIR
(J11-in ``legacy_lesson_hours`` presedenti), zibil UYDURULMUR, tavandan böyük
dəyər (bir həftəlik xanaya yazılmış semestr yekunu) qəbul edilmir.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from .legacy_text import clean_multiline_text, clean_text
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import LegacyRehearsalEvidenceError, RehearsalContext
from .rehearsal_journal_offerings_source import legacy_int, validated_uniqid
from .source_extraction import open_audited_source_stream
from .syllabus_migration_contracts import (
    SYLLABUS_HEADER_FIELDS,
    SYLLABUS_SECTION_CONTRACTS,
    SYLLABUS_WEEK_FIELDS,
)

#: Mənbə ``movzu`` sütununun eni (``varchar(500)``; ölçülən maksimum 499).
#: Hədəf ``SyllabusSection.data`` JSON-dur, yəni DB eni yoxdur — bu tavan
#: sürücü anomaliyasına qarşı qoruyucudur, kəsmə siyasəti deyil.
TOPIC_MAX_LENGTH = 500
#: ``qeyd`` da ``varchar(500)``-dür (ölçülən maksimum 432).
NOTE_MAX_LENGTH = 500
#: Peyklərin ``name`` sütunları ``text``-dir (ölçülən maksimum 46,992).
#: MySQL ``TEXT`` onsuz da 65,535 baytdır, yəni bu tavan real mətni KƏSMİR.
SECTION_TEXT_MAX_LENGTH = 65_535

#: Bir həftəlik xananın ağlabatan akademik saat tavanı (J11-in
#: ``MAX_LESSON_HOURS`` dəyəri ilə eyni).  Canlı mənbədə bundan böyük dəyərlər
#: var (15, 30, 45, 60, 75, 120) — onlar bir həftənin deyil, bütün semestrin
#: saatıdır və səhv xanaya yazılıb; yuvarlaqlaşdırmaq kimi, "bölmək" də
#: uydurma olardı, ona görə sətir saatsız keçir və issue ilə sayılır.
MAX_TOPIC_HOURS = 12

#: ``language`` sütununun QƏBUL EDİLƏN dəyərləri (canlı: az 5,766 · en 2,002 ·
#: ru 440 · '-' 40).  '-' dil deyil, "təyin edilməyib" deməkdir.
KNOWN_LANGUAGES = frozenset({"az", "en", "ru"})

# ── Issue kodları ────────────────────────────────────────────────────────────
#: Saat xanası kəsrlidir (canlı: '0.5'); YUVARLAQLAŞDIRMA QADAĞANDIR.
HOUR_CELL_FRACTIONAL = "legacy_syllabus_hour_cell_fractional"
#: Saat xanası rəqəm deyil (canlı: 'ş', '2K', '`1', '1`', '-+').
HOUR_CELL_INVALID = "legacy_syllabus_hour_cell_invalid"
#: Saat xanası bir həftə üçün ağlabatan tavandan böyükdür (15, 30, 45, …).
HOUR_CELL_OUT_OF_RANGE = "legacy_syllabus_hour_cell_out_of_range"
#: ``uniqid`` birdən çox başlıq sətri tərəfindən işlədilir — bölmə sətirləri
#: heç bir başlığa bağlanmır (fail-closed).
AMBIGUOUS_UNIQID = "legacy_syllabus_uniqid_ambiguous"
#: Bölmə sətrinin ``uniqid``-i heç bir başlığa düşmür (canlı: 14 uniqid).
ORPHAN_UNIQID = "legacy_syllabus_uniqid_orphan"
#: ``language`` kataloqda yoxdur — dil BOŞ qalır, təxmin edilmir.
LANGUAGE_UNKNOWN = "legacy_syllabus_language_unknown"

_DIGIT_HOURS = re.compile(r"[0-9]{1,5}\Z")
_DECIMAL_HOURS = re.compile(r"[0-9]{1,4}\.[0-9]{0,4}\Z")
#: Boş xana ilə eyni mənalı yazılışlar.  '-' müəllimin "saat yoxdur" yazmasıdır;
#: onu issue kimi saymaq ledger-i 69 sətirlik səs-küylə doldurardı.
_BLANK_HOUR_TOKENS = frozenset({"", "-"})

#: Həftəlik cədvəlin dörd saat sütunu, hədəf açarı ilə birlikdə.  ``practical``
#: hədəfin ``LESSON_HOUR_KINDS``-ində YOXDUR (orada yalnız lecture/seminar/lab
#: var) — mənbədə isə 50,671 sətirdə doludur.  Oxucu onu OXUYUR və ötürür;
#: hədəfə necə yazılacağı (yoxsa yazılmayacağı) FAZANIN qərarıdır, mənbə qatı
#: heç nəyi səssizcə atmır.
HOUR_COLUMNS = (
    ("lecture", "muh_saat"),
    ("seminar", "sem_saat"),
    ("practical", "praktiki_saat"),
    ("lab", "lab_saat"),
)


def legacy_hour_cell(value: object) -> tuple[int, str]:
    """``char(5)`` saat xanası → ``(saat, issue kodu)``; fail-closed.

    Qaytarılan saat ``0`` və issue kodu boş olanda xana həqiqətən sıfırdır
    (və ya boşdur).  Issue kodu dolu olanda saat YAZILMIR — çağıran sətri
    saatsız köçürür və kodu ledger-də sayır.
    """

    if value is None:
        return 0, ""
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    text = value.strip()
    if text in _BLANK_HOUR_TOKENS:
        return 0, ""
    if _DIGIT_HOURS.fullmatch(text):
        hours = int(text)
    elif _DECIMAL_HOURS.fullmatch(text):
        # J11-in ``legacy_calendar_int`` semantikası: tam qiymətli onluq
        # ('2.') qəbul olunur, kəsrli ('0.5') fail-closed rədd edilir.
        number = float(text)
        if not number.is_integer():
            return 0, HOUR_CELL_FRACTIONAL
        hours = int(number)
    else:
        return 0, HOUR_CELL_INVALID
    if hours > MAX_TOPIC_HOURS:
        return 0, HOUR_CELL_OUT_OF_RANGE
    return hours, ""


def legacy_language(value: object) -> tuple[str, str]:
    """``language`` → ``(dil, issue kodu)``; naməlum dəyər BOŞ qalır."""

    if value is None:
        return "", LANGUAGE_UNKNOWN
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    language = value.strip().casefold()
    if language in KNOWN_LANGUAGES:
        return language, ""
    return "", LANGUAGE_UNKNOWN


@dataclass(frozen=True)
class SyllabusHeaderRow:
    """Bir ``sillabus`` başlığının distillə olunmuş forması."""

    legacy_pk: int
    uniqid: str
    lesson_id: int
    teacher_id: int
    lesson_hours: int
    language: str
    active: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class SyllabusWeekRow:
    """``sillabus_sem_muh``-un bir sətri: mövzu + dörd saat xanası."""

    legacy_pk: int
    topic: str
    note: str
    #: Hədəf açarı → saat (``HOUR_COLUMNS`` sırasında, yalnız qəbul edilənlər).
    hours: tuple[tuple[str, int], ...]
    issues: tuple[str, ...]
    truncated: bool


@dataclass(frozen=True)
class SyllabusSectionRow:
    """``id | uniqid | name`` formalı peykin bir sətri."""

    legacy_pk: int
    text: str
    truncated: bool


@dataclass(frozen=True)
class SyllabusHeaderIndex:
    """Başlıq reyestri + ``uniqid`` körpüsü + ambiqü açar dəsti."""

    #: ``sillabus.id`` → başlıq (mənbənin PK sırasında qurulur).
    headers: dict[int, SyllabusHeaderRow]
    #: ``uniqid`` → ``sillabus.id``.  Ambiqü uniqid-lər BURADA YOXDUR.
    pk_of_uniqid: dict[str, int]
    #: Birdən çox başlıq tərəfindən işlədilən ``uniqid``-lər.
    ambiguous_uniqids: frozenset[str]

    def header_for_uniqid(self, uniqid: str) -> SyllabusHeaderRow | None:
        legacy_pk = self.pk_of_uniqid.get(uniqid)
        return None if legacy_pk is None else self.headers[legacy_pk]


def _validated_pk(value: object) -> int:
    """``pk_inventory._row_pk`` ilə eyni: heç bir coercion, fail closed."""

    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
    if not 1 <= value <= MAX_LEDGER_PRIMARY_KEY:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
    return value


def _attested_rows(context: RehearsalContext, contract) -> Iterator[tuple[int, object]]:
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


def syllabus_header_index(context: RehearsalContext) -> SyllabusHeaderIndex:
    """8,248 başlığı oxu; ``uniqid`` körpüsünü qur, ambiqü olanı ayır.

    Ambiqü uniqid HƏR İKİ istiqamətdə çıxarılır: nə körpüdə qalır, nə də
    başlıqları itir — başlıqlar ``headers``-də olduğu kimi durur, sadəcə
    onlara peyk bağlanmır.  Beləliklə uydurma bağ qurulmur, amma başlığın
    özü də səssizcə itmir.
    """

    headers: dict[int, SyllabusHeaderRow] = {}
    pk_of_uniqid: dict[str, int] = {}
    ambiguous: set[str] = set()
    for legacy_pk, row in _attested_rows(context, SYLLABUS_HEADER_FIELDS):
        uniqid = validated_uniqid(row["uniqid"])
        language, language_issue = legacy_language(row["language"])
        headers[legacy_pk] = SyllabusHeaderRow(
            legacy_pk=legacy_pk,
            uniqid=uniqid,
            lesson_id=legacy_int(row["lesson_id"]),
            teacher_id=legacy_int(row["teacher_id"]),
            lesson_hours=legacy_int(row["ders_saati"]),
            language=language,
            active=legacy_int(row["active"]) == 1,
            issues=(language_issue,) if language_issue else (),
        )
        if uniqid in pk_of_uniqid or uniqid in ambiguous:
            ambiguous.add(uniqid)
            pk_of_uniqid.pop(uniqid, None)
            continue
        pk_of_uniqid[uniqid] = legacy_pk
    return SyllabusHeaderIndex(
        headers=headers,
        pk_of_uniqid=pk_of_uniqid,
        ambiguous_uniqids=frozenset(ambiguous),
    )


def _distilled_week_row(legacy_pk: int, row) -> SyllabusWeekRow:
    """Mövzu mətnini təmizlə, dörd saat xanasını fail-closed çevir."""

    topic, topic_truncated = clean_text(row["movzu"], max_length=TOPIC_MAX_LENGTH)
    note, note_truncated = clean_text(row["qeyd"], max_length=NOTE_MAX_LENGTH)
    hours: list[tuple[str, int]] = []
    issues: list[str] = []
    for target_key, column in HOUR_COLUMNS:
        value, issue = legacy_hour_cell(row[column])
        if issue:
            issues.append(issue)
            continue
        hours.append((target_key, value))
    return SyllabusWeekRow(
        legacy_pk=legacy_pk,
        topic=topic,
        note=note,
        hours=tuple(hours),
        issues=tuple(issues),
        truncated=topic_truncated or note_truncated,
    )


def syllabus_week_rows(context: RehearsalContext) -> dict[str, tuple[SyllabusWeekRow, ...]]:
    """``uniqid`` → həftəlik mövzu sətirləri, mənbənin ``id`` SIRASINDA.

    Boş mövzu sətri ATILMIR: onu atmaq qalan mövzuları bir pillə yuxarı
    sürüşdürərdi (həftə 5 birdən həftə 4 olardı).  Boşluq qərarı fazanındır.
    """

    grouped: dict[str, list[SyllabusWeekRow]] = {}
    for legacy_pk, row in _attested_rows(context, SYLLABUS_WEEK_FIELDS):
        uniqid = validated_uniqid(row["uniqid"])
        grouped.setdefault(uniqid, []).append(_distilled_week_row(legacy_pk, row))
    return {uniqid: tuple(rows) for uniqid, rows in grouped.items()}


def distilled_section_row(legacy_pk: int, value: object) -> SyllabusSectionRow:
    """Bir peyk ``name`` xanası → distillə olunmuş sətir (saf funksiya).

    ``_distilled_week_row``-un peyk qarşılığı: axından AYRI dayanır ki, təmizləmə
    qaydası kontekst/DB olmadan sınana bilsin.
    """

    # ``clean_multiline_text``: sətir sonları MƏZMUNDUR (modul başlığı).
    text, truncated = clean_multiline_text(value, max_length=SECTION_TEXT_MAX_LENGTH)
    return SyllabusSectionRow(legacy_pk=legacy_pk, text=text, truncated=truncated)


def syllabus_section_rows(context: RehearsalContext, source_table: str) -> dict[str, tuple[SyllabusSectionRow, ...]]:
    """Bir ``id | uniqid | name`` peykini ``uniqid`` üzrə, ``id`` sırasında yığ.

    ``source_table`` ``SYLLABUS_SECTION_CONTRACTS``-də OLMALIDIR — naməlum ad
    fail-closed rədd edilir, çünki audited olmayan cədvəldən oxumaq
    proyeksiyanın default-deny zəmanətini pozardı.
    """

    contract = SYLLABUS_SECTION_CONTRACTS.get(source_table)
    if contract is None:
        raise LegacyRehearsalEvidenceError("legacy_syllabus_section_table_unregistered")
    grouped: dict[str, list[SyllabusSectionRow]] = {}
    for legacy_pk, row in _attested_rows(context, contract):
        uniqid = validated_uniqid(row["uniqid"])
        grouped.setdefault(uniqid, []).append(distilled_section_row(legacy_pk, row["name"]))
    return {uniqid: tuple(rows) for uniqid, rows in grouped.items()}


__all__ = [
    "AMBIGUOUS_UNIQID",
    "HOUR_CELL_FRACTIONAL",
    "HOUR_CELL_INVALID",
    "HOUR_CELL_OUT_OF_RANGE",
    "HOUR_COLUMNS",
    "KNOWN_LANGUAGES",
    "LANGUAGE_UNKNOWN",
    "MAX_TOPIC_HOURS",
    "NOTE_MAX_LENGTH",
    "ORPHAN_UNIQID",
    "SECTION_TEXT_MAX_LENGTH",
    "TOPIC_MAX_LENGTH",
    "SyllabusHeaderIndex",
    "SyllabusHeaderRow",
    "SyllabusSectionRow",
    "SyllabusWeekRow",
    "distilled_section_row",
    "legacy_hour_cell",
    "legacy_language",
    "syllabus_header_index",
    "syllabus_section_rows",
    "syllabus_week_rows",
]
