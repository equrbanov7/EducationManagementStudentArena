"""J12-nin mənbə qatı: BƏRPA olunası dərs slotunun törədilməsi.

Niyə var (ölçülmüş fakt, 2026-08-30/31)
---------------------------------------
J4 (``journal_marks``) bir bal xanasını yalnız MÖVCUD ``Lesson`` sətrinə bağlaya
bilir; dərs indeksi isə ``journals_dates_added_by_teacher``-dən qurulur.  Canlı
mənbədə 570 jurnalın həmin cədvəli boşdur və ya demək olar boşdur (183-ündə
SIFIR sətir), halbuki bal cədvəli doludur.  Nəticə: **164,747 xana** (11,057
fərqli slot) hədəfə heç cür düşə bilmir — onların 12,424-ü REAL rəqəmli
qiymətdir, 19,108-i qayıbdır.

Bağlanma artefaktı deyil: ``journals_dates_added_by_teacher``-də cəmi 28 orphan
sətir var, ``journals``-də təkrar ``uniqid`` yoxdur — yəni itən dərs cədvəli
mənbənin özündə yoxdur, başqa açar altında gizlənmir.

Bərpanın açarı
--------------
İtən dərsin ``(ay, gün, saat)`` üçlüyü BAL XANASININ ÖZÜNDƏDİR
(``journals_dates_points.month_id`` / ``day_number`` / ``time``).  Yəni dərs
sətri uydurulmur — mövcud xananın daşıdığı slotdan BƏRPA olunur.  Hədəfdəki
sətir ``Lesson.is_legacy_synthesised=True`` ilə açıq işarələnir və ledger-də
``legacy_lesson_synthesised`` kodu ilə görünür.

Saat semantikasının 2024 dəyişikliyi (ölçülüb)
----------------------------------------------
``journals_dates_rooms.saatliq_ders`` sütununun VAHİDİ 2024-cü ilin yaz
semestrində dəyişib.  Canlı ölçü (``fake=0``, dərsin öz ``date`` sütunu üzrə):

===========  ==========  ==========  ===========================
dövr         jurnal      orta slot   ``saatliq_ders`` cəmi/jurnal
===========  ==========  ==========  ===========================
< 2024-02      4,471        19.7            38.8   (≈ 2 / slot)
>= 2024-02     7,157        24.8            24.5   (≈ 1 / slot)
===========  ==========  ==========  ===========================

Slot sayı AZALMAYIB (əksinə artıb), yəni akademik saat cəmi yarıya düşə bilməz:
dəyişən vahiddir — köhnə dövrdə sütun AKADEMİK SAAT, yeni dövrdə isə CÜT (bir
cüt = 2 akademik saat) sayır.  Slot şəbəkəsi hər iki dövrdə eynidir (08:30,
10:00, 11:30, 13:30, 15:00, 16:30 — 90 dəqiqəlik addım), yəni bir slot həmişə
bir cütdür.  Ona görə bərpa olunan dərsin saatı belə hesablanır::

    saat = saatliq_ders * 2   (tarix >= 2024-02-01)
    saat = saatliq_ders       (tarix <  2024-02-01)

Yeni dövrdə ``0.5`` (yarım cüt) artıq TAM ƏDƏDƏ düşür (1 akademik saat), yəni
J11-in ``legacy_lesson_meta_hours_fractional`` yolu bu dövrdə yox olur.

⚠️ Bu qayda YALNIZ bərpa olunan dərslərə tətbiq edilir.  J11-in mövcud
sətirlərinə TOXUNULMUR (mövcud dəyər dəyişmir) — J11-in öz saat qərarı sahibin
ayrıca baxışını gözləyir, bax ``docs/migration/BERPA_SINTETIK_DERSLER.md``.

Metadata praktikada demək olar YOXDUR: 11,057 bərpa slotundan yalnız **13**-ü
``journals_dates_rooms``-da qarşılıq tapır (193 xana).  Qalanı J3-ün spec
defoltu ilə (``hours=2``) qalır — bu, yeni dövrün bir cütü ilə eynidir.
"""

from __future__ import annotations

import datetime

from .lesson_meta_field_contracts import LESSON_ROOM_FIELDS
from .rehearsal_lesson_meta_source import (
    MAX_LESSON_HOURS,
    legacy_calendar_int,
    lesson_meta_rows,
)

#: Vahid dəyişikliyinin kəsimi — 2023/2024 tədris ilinin YAZ semestri.
#: Ölçü: 2023-12-də 756/9,932 sətir ``1``, 2024-02-də 6,297/6,363 sətir ``1``.
HOURS_PAIR_SEMANTICS_FROM = datetime.date(2024, 2, 1)

#: Bir cütün akademik saatı (90 dəqiqə = 2 × 45 dəqiqə).
HOURS_PER_PAIR = 2

#: J3-ün spec defoltu; metadata tapılmayanda bərpa olunan dərs bunu saxlayır.
DEFAULT_LESSON_HOURS = 2

#: ``saatliq_ders`` yoxdur / diapazondan kənardır → defolt saat qalır.
HOURS_UNRESOLVED_RULE_CODE = "legacy_lesson_synth_hours_unresolved"
#: Vahid çevrilməsindən sonra da tam ədəd alınmır (köhnə dövrün 0.5-i) → defolt.
HOURS_FRACTIONAL_RULE_CODE = "legacy_lesson_synth_hours_fractional"


def pair_semantics(lesson_date: datetime.date) -> bool:
    """Bu tarixdə ``saatliq_ders`` CÜT sayırmı (yoxsa akademik saat)?"""

    return lesson_date >= HOURS_PAIR_SEMANTICS_FROM


def recovered_lesson_hours(value: object, lesson_date: datetime.date) -> tuple[int, str]:
    """``saatliq_ders`` → ``(saat, issue kodu)``; dövr-şüurlu, yuvarlaqlaşdırmasız.

    ``0`` qaytarılanda çağıran J3 defoltunu (``DEFAULT_LESSON_HOURS``) saxlayır
    və sətri qaytarılan kodla ledger-də sayır — dəyər heç vaxt təxmin edilmir.
    """

    kind = type(value)
    if value is None or kind is bool or kind not in (int, float):
        return 0, HOURS_UNRESOLVED_RULE_CODE
    raw = float(value)
    hours = raw * HOURS_PER_PAIR if pair_semantics(lesson_date) else raw
    if not float(hours).is_integer():
        return 0, HOURS_FRACTIONAL_RULE_CODE
    hours = int(hours)
    if not 1 <= hours <= MAX_LESSON_HOURS:
        return 0, HOURS_UNRESOLVED_RULE_CODE
    return hours, ""


class RecoveredSlotMetadata:
    """Bərpa slotu → ``journals_dates_rooms`` metadatası (varsa).

    Açar J11-in öz slot açarıdır — ``(journal_id, ay, gün, "HH:MM")`` — amma
    burada ``journal_id`` yerinə jurnalın ``uniqid``-i işlədilir, çünki xana
    cədvəli rəqəm FK daşımır.  ``fake=1`` sətirlər J11-dəki kimi süzülür;
    eyni açarı iki ``fake=0`` sətir iddia edərsə HEÇ BİRİ götürülmür (J11-in
    ``legacy_lesson_meta_ambiguous`` fail-closed qaydası).
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: dict[tuple[str, int, int, str], object]) -> None:
        self._rows = rows

    def __len__(self) -> int:
        return len(self._rows)

    def get(self, key: tuple[str, int, int, str]):
        return self._rows.get(key)


def build_recovered_slot_metadata(context, journals, wanted) -> RecoveredSlotMetadata:
    """Yalnız BƏRPA olunacaq slotlar üçün metadata indeksi (yaddaş dar qalsın).

    ``journals`` — ``journals.id`` → ``(uniqid, semestr)`` indeksi (J3-ün öz
    köməkçisi); ``wanted`` — bərpa slot açarlarının dəsti.  Mənbənin 291,509
    sətri axıdılır, amma indeksdə yalnız istənən açarlar qalır.
    """

    hits: dict[tuple[str, int, int, str], object] = {}
    ambiguous: set[tuple[str, int, int, str]] = set()
    for _legacy_pk, row in lesson_meta_rows(context):
        if legacy_calendar_int(row["fake"]):
            continue
        journal = journals.get(legacy_calendar_int(row["journal_id"]))
        if journal is None:
            continue
        time_value = row["times"]
        key = (
            journal[0],
            legacy_calendar_int(row["month"]),
            legacy_calendar_int(row["day"]),
            time_value if type(time_value) is str else "",
        )
        if key not in wanted or key in ambiguous:
            continue
        if key in hits:
            # J11 ilə eyni ruh: iki metadata sətri arasında seçim üçün mənbədə
            # əsas yoxdur → hər ikisi buraxılır, dərs defoltları ilə qalır.
            del hits[key]
            ambiguous.add(key)
            continue
        hits[key] = row
    return RecoveredSlotMetadata(hits)


def metadata_payload(row, *, lesson_date: datetime.date, topics, rooms) -> tuple[str, str, int, tuple[str, ...]]:
    """Metadata sətri → ``(mövzu, otaq pk, saat, issue kodları)``.

    Mövzu/otaq J11-in indekslərindən oxunur; tapılmasa BOŞ qalır (təxmin yoxdur).
    """

    codes: list[str] = []
    if row is None:
        return "", "", 0, (HOURS_UNRESOLVED_RULE_CODE,)
    topic_entry = topics.get(legacy_calendar_int(row["sillabus"]))
    topic = topic_entry[0] if topic_entry is not None else ""
    room_pk = rooms.get(str(legacy_calendar_int(row["room"])), "")
    hours, hours_code = recovered_lesson_hours(row["saatliq_ders"], lesson_date)
    if hours_code:
        codes.append(hours_code)
    return topic, room_pk, hours, tuple(codes)


#: J12 heç bir YENİ cədvəl iddia etmir; oxuduğu kontraktlar bunlardır (sənəd).
RECOVERY_SOURCE_CONTRACTS = (LESSON_ROOM_FIELDS,)


__all__ = [
    "DEFAULT_LESSON_HOURS",
    "HOURS_FRACTIONAL_RULE_CODE",
    "HOURS_PAIR_SEMANTICS_FROM",
    "HOURS_PER_PAIR",
    "HOURS_UNRESOLVED_RULE_CODE",
    "RECOVERY_SOURCE_CONTRACTS",
    "RecoveredSlotMetadata",
    "build_recovered_slot_metadata",
    "metadata_payload",
    "pair_semantics",
    "recovered_lesson_hours",
]
