"""J4/J5/J6 yazı qərarının OFLAYN təkrar icrası — nərdivanın SƏBƏB pillələri.

Niyə bu modul var
-----------------
2026-08-30-a qədər nərdivan ``orphan jurnal`` və ``həll olunmayan yazılış``
pillələrindən sonra dayanırdı və 193,516 xana **izahsız** qalırdı.  Səbəb
struktur idi: nərdivan xananın açılışa və yazılışa bağlanıb-bağlanmadığını
yoxlayırdı, amma import-un NÖVBƏTİ iki qapısını heç kim yenidən hesablamırdı:

1. **Dərs slotu** — ``LessonMark`` yalnız MÖVCUD ``Lesson``-a bağlana bilər.
   Xananın ``(açılış, ay, gün, "SS:DD")`` slotu materiallaşmayıbsa xana yazılmır
   (``rehearsal_journal_marks_phase._decide``, ``lesson`` qapısı).
2. **Hədəf açarı toqquşması** — hədəf açarı ``(dərs, yazılış)`` /
   ``(komponent, yazılış)`` / ``(yazılış, im|im2)`` unikaldır, mənbənin J-V4
   dedup açarı isə ``journal_uniqid``-i də ehtiva edir.  Bir neçə legacy jurnal
   BİR açılışa birləşdiyi üçün (``legacy_journal_offering_merged``) iki ayrı
   mənbə xanası eyni hədəf açarına düşür — ikincisi sətir YARATMIR.

Toqquşmanın yarısı ledger üçün tam səssizdir: ``classify_mark_write()`` mövcud
xanaya EYNİ dəyər gələndə ``"written"`` qaytarır, yəni ledger «yazıldı» sayır,
hədəfdə isə yeni sətir yaranmır.  Ona görə bu pillə ledger sayğacından DEYİL,
mənbə xanalarının öz axınından hesablanmalıdır — bu modul məhz onu edir.

Pillələr (2026-08-31 ölçüsündən sonra)
--------------------------------------
Yuxarıdakı iki qapının HƏR BİRİ ölçüldükdən sonra ikiyə bölündü, çünki içindəki
hallar məzmunca fərqlidir:

1. ``lesson_missing_source_absent`` — dərs MƏNBƏDƏ də yoxdur (J12 bərpasının
   hədəfi; bərpa tətbiq olunmuş nüsxədə **0** olur — ölçülüb);
2. ``lesson_missing_source_present`` — dərs sətri mənbədə VAR.  Ölçüldü: bu
   xanaların hamısı mənbənin öz təqvim/saat səhvidir (31 aprel · 30 fevral ·
   ``80:30``), yəni J3 onlardan həqiqi tarix qura bilmir — ``source_slot_reason``
   hər birini adlandırır, adlandırıla bilməyəni AÇIQ saxlayır;
3. ``collision_same_value`` — eyni fakt iki dəfə, itki YOXDUR;
4. ``collision_other_value`` — uduzan dəyər sətir yaratmır (sübut qatında qalır).

Ayrıca ``written``-in alt sayğacı var: ``written_via_synth_null_time`` —
oxunmayan saatlı xana J12-nin ``start_time = NULL`` dərsinə bağlanır.

Müqavilə
--------
Modul **saf**dır: bazaya toxunmur, yalnız iterasiya olunan sətir axını və
hazır xəritələr qəbul edir.  Beləliklə bütün nərdivan riyaziyyatı canlı baza
olmadan test oluna bilir (``apps/legacy_import/tests``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analysis import ABSENT_TOKEN, DOMAIN_COMPONENTS, DOMAIN_MARKS, DOMAINS, PRESENT_TOKEN
from .write_replay_calendar import (
    SUBSTEP_DAY_ABSENT,
    SUBSTEP_DAY_PRESENT_TIME_DIFFERS,
    SUBSTEP_IMPOSSIBLE_DATE,
    SUBSTEP_LEAP_DEPENDENT_DATE,
    SUBSTEP_SLOT_NOT_MATERIALISED,
    SUBSTEP_UNREADABLE_TIME,
    is_readable_time,
    source_slot_reason,
)

# ``replay_writes`` sətir axınının sütun sırası.  İlk yeddi sütun köhnə saf-test
# müqaviləsidir; son dörd sütunu ``source_sql.deduped_cell_keys_sql`` verir.
ROW_UNIQID, ROW_STUDENT, ROW_DOMAIN = 0, 1, 2
ROW_MONTH, ROW_DAY, ROW_TIME, ROW_POINT = 3, 4, 5, 6
ROW_SOURCE_TABLE, ROW_SOURCE_PK, ROW_IS_ARCHIVE, ROW_LOCAL_REPEAT = 7, 8, 9, 10

POINT_SOURCE_TABLE = "journals_dates_points"
POINT_ARCHIVE_TABLE = "journals_dates_points_archive"

# Sayğac açarları — nərdivan pillələri ilə birbaşa uyğun gəlir.
STEP_DEDUPED = "deduped"
STEP_ORPHAN = "orphan"
STEP_UNRESOLVED = "unresolved"
STEP_LESSON_MISSING = "lesson_missing"
STEP_LESSON_SOURCE_ABSENT = "lesson_missing_source_absent"
STEP_LESSON_SOURCE_PRESENT = "lesson_missing_source_present"
STEP_COLLISION = "collision"
STEP_COLLISION_SAME = "collision_same_value"
STEP_COLLISION_OTHER = "collision_other_value"
#: Eyni hədəf açarını 3+ mənbə xanası iddia edir — «eyni/fərqli» bölgüsünün
#: SIRA-dan asılı ola biləcəyi YEGANƏ hal (bax ``replay_writes`` qeydi).
STEP_COLLISION_REPEAT = "collision_third_or_later"
STEP_ARCHIVE_SUPERSEDED = "archive_target_superseded"
STEP_WRITTEN = "written"
#: Saatı oxunmayan xana J12-nin ``start_time = NULL`` dərsinə bağlanır — bu,
#: ``written``-in ALT sayğacıdır (ayrıca pillə DEYİL, ona görə ``IDENTITIES``-ə
#: girmir); bax ``UNREADABLE_TIME_NOTE``.
STEP_SYNTH_TIME_UNKNOWN = "written_via_synth_null_time"

LABEL_LESSON_MISSING = "dərs slotu tapılmadı (mənbədə həmin (ay, gün, saat) dərsi yoxdur)"
LABEL_LESSON_SOURCE_ABSENT = "dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi)"
LABEL_LESSON_SOURCE_PRESENT = "dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb"
LABEL_COLLISION = "hədəf açarı toqquşması (birləşən jurnallar bir xanaya düşür)"
LABEL_COLLISION_SAME = "hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL)"
LABEL_COLLISION_OTHER = "hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır)"
LABEL_ARCHIVE_SUPERSEDED = "arxiv xanası canlı hədəf tərəfindən əvəzlənib (J-V7)"

# Kəsişmə ölçüsünün baxdığı pillələr (cədvəl sırası da budur).
OVERLAP_RUNGS = (
    STEP_LESSON_SOURCE_ABSENT,
    STEP_LESSON_SOURCE_PRESENT,
    STEP_COLLISION_SAME,
    STEP_COLLISION_OTHER,
)

RUNG_LABELS = {
    STEP_LESSON_SOURCE_ABSENT: LABEL_LESSON_SOURCE_ABSENT,
    STEP_LESSON_SOURCE_PRESENT: LABEL_LESSON_SOURCE_PRESENT,
    STEP_COLLISION_SAME: LABEL_COLLISION_SAME,
    STEP_COLLISION_OTHER: LABEL_COLLISION_OTHER,
}

# İtən xananın NƏ DAŞIDIĞI — «bal itdi» ilə «davamiyyət itdi» eyni şey deyil.
SHAPE_PRESENT = "iştirak (`ie`)"
SHAPE_ABSENT = "qayıb (`qb`)"
SHAPE_SCORE = "rəqəmli bal"


def value_shape(point: str) -> str:
    """Xana dəyərinin növü — itkinin AĞIRLIĞINI ayırd etmək üçün."""

    if point == PRESENT_TOKEN:
        return SHAPE_PRESENT
    return SHAPE_ABSENT if point == ABSENT_TOKEN else SHAPE_SCORE


def multi_key_enrollment_targets(enrollments) -> set[str]:
    """Bir neçə legacy açarın göstərdiyi hədəf yazılışları (birləşmə izi).

    Bu, yaddaş qapağının BİR hissəsidir.  Eyni legacy açarın fərqli J-V4
    açarları da normallaşmadan sonra bir hədəfə düşə bilər (məs. ``9``/``09``;
    komponentdə fərqli gün/saat).  SQL həmin halın hər sətrini ayrıca
    ``ROW_LOCAL_REPEAT`` ilə nişanlayır.  Replay yalnız bu iki namizəd sinfinin
    hədəf açarlarını saxlayır — bütün 5M xana yaddaşa yığılmır.
    """

    seen_once: set[str] = set()
    repeated: set[str] = set()
    for target_pk in enrollments.values():
        if target_pk in seen_once:
            repeated.add(target_pk)
        else:
            seen_once.add(target_pk)
    return repeated


def normalized_target_value(domain: str, point: str) -> str:
    """Importer-in hədəfdə müqayisə etdiyi kanonik dəyər.

    J4 status+balı, J5/J6 isə ``Decimal`` balı müqayisə edir.  Mətn forması
    müqayisə edilmir: məsələn ``"07"`` və ``"7"`` eyni baldır.
    """

    if domain == DOMAIN_MARKS:
        if point == PRESENT_TOKEN:
            return "status:present"
        if point == ABSENT_TOKEN:
            return "status:absent"
    return f"score:{int(point)}"


@dataclass(frozen=True)
class CollisionEvidence:
    """Fərqli-dəyər toqquşmasının mənbədən deterministik sübut identity-si.

    Siyahı yalnız həqiqi fərqli konfliktlər üçün böyüyür (~1.7k), bütün xana
    axını üçün yox.  ``source_table + source_pk`` J12 faktının təbii mənbə
    identity-sidir; raw və normallaşmış dəyərlər exact gate-ə həm payload-u,
    həm də importer müqayisəsini müstəqil yoxlamağa imkan verir.
    """

    domain: str
    source_table: str
    source_pk: int
    is_archive: bool
    journal_uniqid: str
    student_ref: str
    enrollment_pk: str
    month_id: str
    target_ref: str
    raw_value: str
    normalized_value: str
    winner_source_table: str
    winner_source_pk: int
    winner_is_archive: bool
    winner_raw_value: str
    winner_normalized_value: str

    @property
    def source_row_hash_key(self) -> tuple[str, int]:
        """Tam field-contract sətrini yenidən hash etmək üçün mənbə açarı."""

        return self.source_table, self.source_pk

    @property
    def winner_source_row_hash_key(self) -> tuple[str, int]:
        return self.winner_source_table, self.winner_source_pk


@dataclass(frozen=True)
class UnresolvedCalendarEvidence:
    """Enrollment-dan sonra dərs slotu tapılmayan writable J4 xanası.

    Replay geniş field-contract payload-unu 5M sətir üzrə daşımır.  Buna görə
    hash-in özü yox, onu mənbədən yenidən və byte-dəqiq hesablamaq üçün təbii
    ``(source_table, source_pk)`` açarı expose olunur.
    """

    source_table: str
    source_pk: int
    is_archive: bool
    journal_uniqid: str
    student_ref: str
    month: int
    day: int
    raw_day: str
    time_text: str
    raw_value: str
    normalized_value: str
    issue_reason: str

    @property
    def source_row_hash_key(self) -> tuple[str, int]:
        return self.source_table, self.source_pk


@dataclass(frozen=True)
class _Claim:
    source_table: str
    source_pk: int
    is_archive: bool
    journal_uniqid: str
    student_ref: str
    enrollment_pk: str
    month_id: str
    target_ref: str
    raw_value: str
    normalized_value: str


@dataclass
class ReplayResult:
    """Domen üzrə sayğaclar + itkinin tərkibi (hesabatın izah bölməsi üçün).

    ``rung_journals`` / ``rung_enrollments`` pillələrin KƏSİŞMƏSİNİ ölçmək
    üçündür: xana səviyyəsində pillələr riyazi olaraq ayrıqdır (hər xana bir
    ``continue``-da bitir), amma EYNİ jurnal və ya EYNİ yazılış bir neçə
    pillədə görünə bilər — hesabat bunu gizlətmir, ölçüb göstərir.
    """

    counts: dict[str, Counter] = field(default_factory=dict)
    lesson_missing_shapes: Counter = field(default_factory=Counter)
    lesson_missing_journals: set[str] = field(default_factory=set)
    collision_journals: set[str] = field(default_factory=set)
    rung_shapes: dict[str, Counter] = field(default_factory=dict)
    rung_journals: dict[str, set] = field(default_factory=dict)
    rung_enrollments: dict[str, set] = field(default_factory=dict)
    source_slot_substeps: Counter = field(default_factory=Counter)
    source_present_substeps: Counter = field(default_factory=Counter)
    conflict_evidence: list[CollisionEvidence] = field(default_factory=list)
    unresolved_calendar_evidence: list[UnresolvedCalendarEvidence] = field(default_factory=list)

    def step(self, domain: str, key: str) -> int:
        return int(self.counts.get(domain, Counter())[key])

    def total(self, key: str) -> int:
        return sum(self.step(domain, key) for domain in DOMAINS)

    def note_rung(self, rung: str, *, journal: str, enrollment: str, point: str = "") -> None:
        """Bir xananı pilləyə yaz — kəsişmə ölçüsünün xam materialı."""

        self.rung_journals.setdefault(rung, set()).add(journal)
        if enrollment:
            self.rung_enrollments.setdefault(rung, set()).add(enrollment)
        if point:
            self.rung_shapes.setdefault(rung, Counter())[value_shape(point)] += 1


# ── Pillələrin ayrıqlığı: ÖLÇÜLÜR, iddia edilmir ────────────────────────────

#: ``(yoxlanılan bütöv, onu tam örtməli olan hissələr)`` — qalıq SIFIR olmalıdır.
IDENTITIES = (
    (
        STEP_DEDUPED,
        (STEP_ORPHAN, STEP_UNRESOLVED, STEP_LESSON_MISSING, STEP_COLLISION, STEP_ARCHIVE_SUPERSEDED, STEP_WRITTEN),
    ),
    (STEP_LESSON_MISSING, (STEP_LESSON_SOURCE_ABSENT, STEP_LESSON_SOURCE_PRESENT)),
    (STEP_COLLISION, (STEP_COLLISION_SAME, STEP_COLLISION_OTHER)),
)


def identity_residuals(result: "ReplayResult") -> list[tuple[str, str, int, int, int]]:
    """``(domen, bütöv, bütövün sayı, hissələrin cəmi, qalıq)`` sətirləri.

    Qalıq sıfırdan fərqlidirsə pillələr YA üst-üstə düşür, YA da bir xana heç
    bir pilləyə düşməyib — hər iki hal nərdivanı etibarsız edir.
    """

    rows: list[tuple[str, str, int, int, int]] = []
    for domain in DOMAINS:
        for whole, parts in IDENTITIES:
            whole_count = result.step(domain, whole)
            part_sum = sum(result.step(domain, part) for part in parts)
            rows.append((domain, whole, whole_count, part_sum, whole_count - part_sum))
    return rows


def rung_overlaps(result: "ReplayResult", rungs=OVERLAP_RUNGS) -> list[tuple[str, str, int, int]]:
    """Pillə cütləri üçün ``(jurnal kəsişməsi, yazılış kəsişməsi)``.

    Xana səviyyəsində kəsişmə sıfırdır (``identity_residuals`` bunu ölçür);
    burada ölçülən — eyni JURNALIN / YAZILIŞIN bir neçə pillədə görünməsidir.
    Bu, ikiqat çıxılma DEYİL, amma «pillələr bir-birindən müstəqil hadisələrdir»
    fərziyyəsini yalanlayır, ona görə hesabatda açıq göstərilir.
    """

    rows: list[tuple[str, str, int, int]] = []
    for index, first in enumerate(rungs):
        for second in rungs[index + 1 :]:
            journals = result.rung_journals.get(first, set()) & result.rung_journals.get(second, set())
            enrollments = result.rung_enrollments.get(first, set()) & result.rung_enrollments.get(second, set())
            rows.append((first, second, len(journals), len(enrollments)))
    return rows


def _calendar_coordinates(row) -> tuple[int, int]:
    """J4 ``calendar_slot(...) or (0, 0)`` normalizasiyasının saf güzgüsü."""

    month_text, day_text = str(row[ROW_MONTH]), str(row[ROW_DAY])
    if month_text in {f"{month:02d}" for month in range(1, 13)} and day_text.isdigit():
        day = int(day_text)
        if 1 <= day <= 31:
            return int(month_text), day
    return 0, 0


def lesson_slot_key(offering_pk: str, row) -> tuple[str, int, int, str]:
    """``(açılış, ay, gün, "SS:DD")`` — ``points_source.lesson_slot_index`` açarı.

    Ay və gün İNT-ə çevrilir, çünki import da ``legacy_int`` ilə belə edir:
    legacy ``day_number`` mətn sütunudur və ``"9"`` ilə ``"09"`` EYNİ dərsdir.
    Bu normalizasiya həm slot axtarışında, həm də hədəf açarında işlədilməlidir —
    əks halda iki mətn variantı süni şəkildə «toqquşmayan» görünür.
    """

    month, day = _calendar_coordinates(row)
    return (offering_pk, month, day, row[ROW_TIME])


def lesson_target(lesson_slots, key):
    """Slot varsa lesson PK-sı; köhnə saf-test set-lərində boş sentinel."""

    if hasattr(lesson_slots, "get"):
        return lesson_slots.get(key)
    return "" if key in lesson_slots else None


def source_slot_key(uniqid: str, row) -> tuple[str, int, int, str]:
    """``(jurnal uniqid, ay, gün, "SS:DD")`` — MƏNBƏ slot indeksinin açarı.

    ``lesson_slot_key``-dən yeganə fərqi: hədəf açılışının pk-sı yerinə legacy
    jurnalın öz ``uniqid``-i durur, çünki mənbə tərəfdə açılış anlayışı yoxdur.
    Ay/gün eyni ``int`` normalizasiyasından keçir (``"9"`` ≡ ``"09"``).
    """

    month, day = _calendar_coordinates(row)
    return (uniqid, month, day, row[ROW_TIME])


def replay_writes(
    rows,
    *,
    offering_journals,
    enrollments,
    enrollment_offerings,
    lesson_slots,
    multi_key_enrollments,
    source_lesson_slots,
) -> ReplayResult:
    """Dedup edilmiş mənbə xanalarını import-un yazı nərdivanından keçir.

    ``rows`` — ``(uniqid, tələbə, domen, ay, gün, "SS:DD", qalib dəyər,
    source_table, source_pk, is_archive, local_target_repeat)`` axını
    (``source_sql.deduped_cell_keys_sql``).  SQL J-V4 seçkisini canlı və arxiv
    üçün AYRI aparıb importer-in faktiki qərar sırasında axıdır: canlı əvvəl,
    arxiv sonra; unikal açarlar PK sırasında, seçki qalibləri onların ardınca.

    ⚠️ «Eyni dəyər / fərqli dəyər» bölgüsü isə YALNIZ bir halda sıradan asılıdır:
    eyni hədəf açarını ÜÇ və daha çox mənbə xanası iddia edəndə 2-ci və 3-cü
    xana 1-ci ilə müqayisə olunur, ona görə hansının «qalib» olduğu bölgünü
    sürüşdürə bilər.  Bu hal ``STEP_COLLISION_REPEAT`` ilə AYRICA sayılır —
    yəni bölgünün qeyri-müəyyənliyinin yuxarı sərhədi hesabatda görünür.

    Qapıların sırası ``rehearsal_journal_marks_phase._decide`` ilə eynidir:
    orphan → yazılış → (təqvimdə) dərs slotu → hədəf açarı.

    ``source_lesson_slots`` — MƏNBƏNİN öz dərs indeksidir
    (``source_sql.lesson_slot_source_sql``): ``(uniqid, ay, gün, "HH:MM")``.
    Dərs qapısında dayanan xana bununla İKİ AYRI pilləyə bölünür — slot
    mənbədə YOXDUR (bərpa hədəfi) vs slot mənbədə VAR, hədəfə düşməyib
    (tamam başqa səbəb).  Bölgü hədəfin sayğacından yox, MƏNBƏDƏN gəlir.
    """

    if not source_lesson_slots:
        # Fail-closed: boş indeks BÜTÜN itkini səhvən «mənbədə yoxdur» sayardı.
        raise ValueError("legacy_reconcile_source_lesson_slots_empty")
    source_lesson_days = {(key[0], key[1], key[2]) for key in source_lesson_slots}

    result = ReplayResult(counts={domain: Counter() for domain in DOMAINS})
    claimed: dict[tuple, _Claim] = {}
    collided: set[tuple] = set()
    archive_started = False
    for sequence, row in enumerate(rows, start=1):
        domain = row[ROW_DOMAIN]
        counter = result.counts.get(domain)
        if counter is None:  # ``unknown_code`` — heç bir domenə düşmür
            continue
        counter[STEP_DEDUPED] += 1
        source_table = str(row[ROW_SOURCE_TABLE]) if len(row) > ROW_SOURCE_TABLE else POINT_SOURCE_TABLE
        source_pk = int(row[ROW_SOURCE_PK]) if len(row) > ROW_SOURCE_PK else sequence
        is_archive = bool(int(row[ROW_IS_ARCHIVE])) if len(row) > ROW_IS_ARCHIVE else False
        local_repeat = bool(int(row[ROW_LOCAL_REPEAT])) if len(row) > ROW_LOCAL_REPEAT else True
        if is_archive:
            archive_started = True
        elif archive_started:
            raise ValueError("legacy_reconcile_source_order_invalid")
        uniqid = row[ROW_UNIQID]
        if uniqid not in offering_journals:
            counter[STEP_ORPHAN] += 1
            continue
        enrollment_pk = enrollments.get(f"{uniqid}:{row[ROW_STUDENT]}", "")
        if not enrollment_pk:
            counter[STEP_UNRESOLVED] += 1
            continue
        offering_pk = enrollment_offerings.get(enrollment_pk, "")
        if domain == DOMAIN_MARKS:
            # J4 açılışsız yazılışı ayrıca saymır — slot axtarışı onsuz da boşa
            # çıxır və xana ``lesson`` qapısında dayanır (fazanın öz sırası).
            slot_key = lesson_slot_key(offering_pk, row) if offering_pk else None
            slot_target = lesson_target(lesson_slots, slot_key) if slot_key is not None else None
            if slot_key is not None and slot_target is None and not is_readable_time(row[ROW_TIME]):
                # J12 güzgüsü: oxunmayan saat → ``start_time = NULL`` dərsi.
                fallback = (slot_key[0], slot_key[1], slot_key[2], "")
                fallback_target = lesson_target(lesson_slots, fallback)
                if fallback != slot_key and fallback_target is not None:
                    counter[STEP_SYNTH_TIME_UNKNOWN] += 1
                    slot_key = fallback
                    slot_target = fallback_target
            if slot_key is None or slot_target is None:
                normalized_month, normalized_day = _calendar_coordinates(row)
                counter[STEP_LESSON_MISSING] += 1
                result.lesson_missing_shapes[value_shape(row[ROW_POINT])] += 1
                result.lesson_missing_journals.add(uniqid)
                source_key = source_slot_key(uniqid, row)
                in_source = source_key in source_lesson_slots
                rung = STEP_LESSON_SOURCE_PRESENT if in_source else STEP_LESSON_SOURCE_ABSENT
                counter[rung] += 1
                result.note_rung(rung, journal=uniqid, enrollment=enrollment_pk, point=row[ROW_POINT])
                if in_source:
                    detail = source_slot_reason(row[ROW_MONTH], row[ROW_DAY], row[ROW_TIME])
                    result.source_present_substeps[detail] += 1
                else:
                    day_seen = source_key[:3] in source_lesson_days
                    detail = SUBSTEP_DAY_PRESENT_TIME_DIFFERS if day_seen else SUBSTEP_DAY_ABSENT
                    result.source_slot_substeps[detail] += 1
                result.unresolved_calendar_evidence.append(
                    UnresolvedCalendarEvidence(
                        source_table=source_table,
                        source_pk=source_pk,
                        is_archive=is_archive,
                        journal_uniqid=uniqid,
                        student_ref=str(row[ROW_STUDENT]),
                        month=normalized_month,
                        day=normalized_day,
                        raw_day=str(row[ROW_DAY]),
                        time_text=str(row[ROW_TIME]),
                        raw_value=row[ROW_POINT],
                        normalized_value=normalized_target_value(domain, row[ROW_POINT]),
                        issue_reason=f"{rung}:{detail}",
                    )
                )
                continue
            target_key = (slot_key, enrollment_pk)
        else:
            # J5 komponenti açılışdan törəyir; açılış yoxdursa faza xananı
            # ``enrollment`` qapısında saxlayır.  J6 açılışa ümumiyyətlə baxmır.
            if domain == DOMAIN_COMPONENTS and not offering_pk:
                counter[STEP_UNRESOLVED] += 1
                continue
            target_key = (row[ROW_MONTH], enrollment_pk)
        if enrollment_pk in multi_key_enrollments or local_repeat:
            previous = claimed.get(target_key)
            if previous is not None:
                if is_archive:
                    # J-V7: uyğun canlı hədəf artıq varsa arxiv heç vaxt konflikt
                    # yaratmır və dəyər müqayisə olunmur — sadəcə superseded-dir.
                    counter[STEP_ARCHIVE_SUPERSEDED] += 1
                    continue
                counter[STEP_COLLISION] += 1
                if target_key in collided:
                    counter[STEP_COLLISION_REPEAT] += 1
                collided.add(target_key)
                normalized = normalized_target_value(domain, row[ROW_POINT])
                same = previous.normalized_value == normalized
                rung = STEP_COLLISION_SAME if same else STEP_COLLISION_OTHER
                counter[rung] += 1
                result.collision_journals.add(uniqid)
                result.note_rung(rung, journal=uniqid, enrollment=enrollment_pk, point=row[ROW_POINT])
                if not same:
                    result.conflict_evidence.append(
                        CollisionEvidence(
                            domain=domain,
                            source_table=source_table,
                            source_pk=source_pk,
                            is_archive=is_archive,
                            journal_uniqid=str(uniqid),
                            student_ref=str(row[ROW_STUDENT]),
                            enrollment_pk=str(enrollment_pk),
                            month_id=str(row[ROW_MONTH]),
                            target_ref=str(slot_target or "") if domain == DOMAIN_MARKS else "",
                            raw_value=row[ROW_POINT],
                            normalized_value=normalized,
                            winner_source_table=previous.source_table,
                            winner_source_pk=previous.source_pk,
                            winner_is_archive=previous.is_archive,
                            winner_raw_value=previous.raw_value,
                            winner_normalized_value=previous.normalized_value,
                        )
                    )
                continue
            claimed[target_key] = _Claim(
                source_table=source_table,
                source_pk=source_pk,
                is_archive=is_archive,
                journal_uniqid=str(uniqid),
                student_ref=str(row[ROW_STUDENT]),
                enrollment_pk=str(enrollment_pk),
                month_id=str(row[ROW_MONTH]),
                target_ref=str(slot_target or "") if domain == DOMAIN_MARKS else "",
                raw_value=row[ROW_POINT],
                normalized_value=normalized_target_value(domain, row[ROW_POINT]),
            )
        counter[STEP_WRITTEN] += 1
    return result


__all__ = [
    "CollisionEvidence",
    "UnresolvedCalendarEvidence",
    "IDENTITIES",
    "LABEL_COLLISION",
    "LABEL_ARCHIVE_SUPERSEDED",
    "LABEL_COLLISION_OTHER",
    "LABEL_COLLISION_SAME",
    "LABEL_LESSON_SOURCE_ABSENT",
    "LABEL_LESSON_SOURCE_PRESENT",
    "OVERLAP_RUNGS",
    "RUNG_LABELS",
    "STEP_COLLISION_REPEAT",
    "STEP_ARCHIVE_SUPERSEDED",
    "STEP_SYNTH_TIME_UNKNOWN",
    "STEP_LESSON_SOURCE_ABSENT",
    "STEP_LESSON_SOURCE_PRESENT",
    "SUBSTEP_DAY_ABSENT",
    "SUBSTEP_IMPOSSIBLE_DATE",
    "SUBSTEP_LEAP_DEPENDENT_DATE",
    "SUBSTEP_SLOT_NOT_MATERIALISED",
    "SUBSTEP_UNREADABLE_TIME",
    "source_slot_reason",
    "SUBSTEP_DAY_PRESENT_TIME_DIFFERS",
    "identity_residuals",
    "rung_overlaps",
    "source_slot_key",
    "SHAPE_ABSENT",
    "SHAPE_PRESENT",
    "SHAPE_SCORE",
    "LABEL_LESSON_MISSING",
    "ReplayResult",
    "STEP_COLLISION",
    "STEP_COLLISION_OTHER",
    "STEP_COLLISION_SAME",
    "STEP_DEDUPED",
    "STEP_LESSON_MISSING",
    "STEP_ORPHAN",
    "STEP_UNRESOLVED",
    "STEP_WRITTEN",
    "is_readable_time",
    "lesson_slot_key",
    "multi_key_enrollment_targets",
    "normalized_target_value",
    "replay_writes",
    "value_shape",
]
