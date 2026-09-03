"""J3-ün dərs NÖVÜ indeksi: ``journals_dates_points`` xanaları → ``Lesson.kind``.

J3 əvvəllər HƏR dərsi ``lecture`` yazırdı, çünki dərs cədvəlinin
(``journals_dates_added_by_teacher``) öz ``sem_muh`` sütunu növü ETİBARLI
şəkildə daşımır.  Hədəfdə ``kind`` isə davranış qapısıdır: ``LessonKind``
sənədinə görə LECTURE → yalnız iə/qb, SEMINAR/LAB → iə/qb **+ bal**.  Nəticədə
mənbədə mövcud seminar balları jurnal UI-ında görünmürdü.

Canlı mənbə ölçüləri (rehearsal DB, 2026-08-27) — semantika BUNLARLA təyin edildi:

* ``journals.sem_muh`` jurnalın İŞLƏTDİYİ növlərin JSON siyahısıdır; ən çox
  rast gələn ``["0","1"]`` (10,660 jurnal) — yəni 0 və 1 legacy UI-da AYRICA
  seçilən iki dəyərdir, "təyin olunmayıb" deyil.
* Slot səviyyəsində ballanma nisbəti (bir slot = jurnal+ay+gün+saat):

  ===================  =======  ===============  ==========
  (lab, sem_muh)       slotlar  ballı slot       faiz
  ===================  =======  ===============  ==========
  (0, 1)                89,584              102       0.1 %
  (0, 0)                92,331           38,038      41.2 %
  (0, 3)                35,265            9,397      26.6 %
  (0, 2)                 2,299            1,625      70.7 %
  (1, 0)                24,192            6,146      25.4 %
  (1, 3)                 4,695              588      12.5 %
  (1, 2)                   924              300      32.5 %
  (1, 1)                   550               13       2.4 %
  ===================  =======  ===============  ==========

  ``sem_muh=1`` praktik olaraq HEÇ vaxt ballanmır (0.1 %) → **mühazirə**;
  sütun adının sırası da bunu deyir (``sem``=0, ``muh``=1).  Qalan dəyərlər
  müntəzəm ballanır → hədəfdə bal xanası AÇIQ olmalıdır.
* ``sem_muh=3`` bütöv jurnalı əhatə edir (``["3"]`` = 1,506 jurnal) və bu
  jurnalların adları praktiki fənlərdir (Portfolio, Fotodizayn, "Yazılı
  tərcümə", "Şifahi tərcümə") — yəni mühazirə/seminar bölgüsü olmayan
  **məşğələ** formatı.  Hədəf enumunda məşğələnin qarşılığı SEMINAR-dır
  (``SlotKind.kind`` help_text: "mühazirə/məşğələ/laboratoriya").
* ``sem_muh=2`` ən yüksək ballanma nisbətinə malikdir (70.7 %) → praktiki,
  yenə SEMINAR.
* ``lab`` MÜSTƏQİL bayraqdır (0/1) və laboratoriyanı işarələyir.

Niyə dərs cədvəlinin öz ``sem_muh``-u yox, XANALAR mənbədir: slot səviyyəsində
ölçüldü ki, dərs sətrinin ``sem_muh=0`` dəyəri həm xana-0 (156,983 slot), həm
xana-1 (120,974 slot) slotlarını əhatə edir — yəni sütun sətirlərin 79 %-ində
heç vaxt yenilənməyən DEFOLT-dur və mühazirə ilə seminarı ayıra bilmir.
Xanalar isə slot daxilində praktik olaraq HOMOGENDİR: 355k slotdan yalnız
**313**-ü (0.09 %) qarışıq ``sem_muh`` daşıyır.  Üstəlik ``lab`` sütunu YALNIZ
xanalarda var.
"""

from __future__ import annotations

from .rehearsal_journal_points_source import (
    ARCHIVE_CUTOFF,
    added_on,
    archive_rows,
    calendar_slot,
    legacy_flag,
    legacy_text,
    normalized_time,
    point_rows,
)
from .rehearsal_structure_phase import probe_cancellation

# Hədəf enumunun dəyərləri (``registrar.models.grading.LessonKind``); modul
# sərhədini açmamaq üçün mətn kimi güzgülənir — J1-in ``ensure_assessment_scheme``
# və J3-ün ``create_lesson`` güzgüləri ilə eyni səbəb.
LECTURE = "lecture"
SEMINAR = "seminar"
LAB = "lab"

# Xana ``sem_muh`` kodları (yuxarıdakı ölçülərə əsasən).
_MUHAZIRE_CODE = 1
_SEMINAR_CODES = frozenset({0, 2, 3})

# Bərabər səs halında sabit üstünlük: bal xanasını BAĞLAYAN növ (lecture) ən
# sonda gəlir — mənbədə yazılmış bal heç vaxt görünməz qalmasın.
_KINDS = (LAB, SEMINAR, LECTURE)
_KIND_SLOT = {kind: index for index, kind in enumerate(_KINDS)}

# Say sahələri BİR tam ədədə yığılır (3 növ × 21 bit): slot başına bir dict
# girişi + bir int, ~355k slot üçün yaddaş sabit qalır.  Sayğac daşması
# mümkün deyil — 21 bit ≈ 2M, ən böyük jurnal isə min sıradadır.
_FIELD_BITS = 21
_FIELD_MASK = (1 << _FIELD_BITS) - 1

ABSENT_RULE_CODE = "legacy_journal_lesson_kind_absent"
CONFLICT_RULE_CODE = "legacy_journal_lesson_kind_conflict"


def cell_kind(*, lab: int, sem_muh: int) -> str:
    """Bir xananın işarələdiyi dərs növü; naməlum kodda boş mətn.

    ``lab`` üstünlük təşkil edir: o, ``sem_muh``-dan MÜSTƏQİL, açıq-aşkar
    laboratoriya bayrağıdır (``sem_muh`` isə mühazirə/seminar oxunu daşıyır).
    """

    if lab == 1:
        return LAB
    if lab != 0:
        return ""
    if sem_muh == _MUHAZIRE_CODE:
        return LECTURE
    if sem_muh in _SEMINAR_CODES:
        return SEMINAR
    return ""


def slot_key(*, uniqid: str, month: int, day: int, time_text: str) -> tuple[str, int, int, str]:
    """Dərs slotunun açarı — J3-ün öz (jurnal, ay, gün, saat) həlli ilə eyni.

    Gün/ay TAM ƏDƏD kimi saxlanılır: mənbədə ``day_number`` sıfır-doldurulmuş
    mətndir (``'03'``), dərs cədvəlində isə ``int``-dir.
    """

    return (uniqid, month, day, time_text)


class LessonKindIndex:
    """Slot → dərs növü; sayları yığılmış tam ədədlərdə saxlayır."""

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int, int, str], int] = {}

    def __len__(self) -> int:
        return len(self._counts)

    def observe(self, key: tuple[str, int, int, str], kind: str) -> None:
        slot = _KIND_SLOT.get(kind)
        if slot is None:
            return
        self._counts[key] = self._counts.get(key, 0) + (1 << (_FIELD_BITS * slot))

    def keys(self) -> frozenset[tuple[str, int, int, str]]:
        return frozenset(self._counts)

    def resolve(self, key: tuple[str, int, int, str]) -> tuple[str, str]:
        """``(kind, rule_code)``; xana yoxdursa defolt ``lecture`` + INFO kodu.

        Qalib ƏKSƏRİYYƏTdir; bərabərlikdə ``_KINDS`` sırası həll edir (LAB →
        SEMINAR → LECTURE), yəni qərar mənbə sırasından ASILI DEYİL.
        """

        packed = self._counts.get(key)
        if packed is None:
            return LECTURE, ABSENT_RULE_CODE
        best_kind = ""
        best_count = 0
        total = 0
        for index, kind in enumerate(_KINDS):
            count = (packed >> (_FIELD_BITS * index)) & _FIELD_MASK
            total += count
            if count > best_count:
                best_kind, best_count = kind, count
        if not best_kind:
            return LECTURE, ABSENT_RULE_CODE
        # Qarışıq slot: qərar əksəriyyətlədir, amma sətir INFO ilə işarələnir.
        return best_kind, "" if best_count == total else CONFLICT_RULE_CODE


def _observe_table(context, index: LessonKindIndex, rows, *, from_archive: bool, claimed=frozenset()) -> None:
    """Bir cədvəlin təqvim xanalarını indeksə yığ (J-V7: əsas cədvəl udur).

    ``claimed`` — əsas cədvəlin artıq doldurduğu slotlar; arxiv YALNIZ boş
    qalan slotu doldurur, yəni bir slot heç vaxt iki mənbədən qarışıq saymır.
    """

    for _legacy_pk, row in rows:
        probe_cancellation(context)
        if from_archive:
            stamped = added_on(row)
            if stamped is None or stamped >= ARCHIVE_CUTOFF:
                continue
        calendar = calendar_slot(legacy_text(row["month_id"]), legacy_text(row["day_number"]))
        if calendar is None:
            continue
        time_text = normalized_time(row["time"])
        if not time_text:
            continue
        month, day = calendar
        key = slot_key(
            uniqid=legacy_text(row["journal_uniqid"]),
            month=month,
            day=day,
            time_text=time_text,
        )
        if key in claimed:
            continue
        kind = cell_kind(lab=legacy_flag(row["lab"]), sem_muh=legacy_flag(row["sem_muh"]))
        if kind:
            index.observe(key, kind)


def build_lesson_kind_index(context) -> LessonKindIndex:
    """Əsas cədvəl, sonra arxiv — J3-ün dərs növü indeksi."""

    index = LessonKindIndex()
    _observe_table(context, index, point_rows(context), from_archive=False)
    _observe_table(context, index, archive_rows(context), from_archive=True, claimed=index.keys())
    return index
