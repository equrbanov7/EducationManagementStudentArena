"""Dərs METADATA domeninin audited mənbə kontraktları (J10/J11).

Niyə ``field_contracts`` DEYİL: həmin modul modul-ölçü qapısının sərt 600-sətir
tavanındadır (``scripts/check_module_size.py``), qapının yazdığı yeganə çarə isə
"əvvəlcə onu bölün"-dür.  Presedent: ``syllabus_field_contracts`` (J9) və
``legacy_grade_field_contracts`` (qiymət sübutu).

⚠️ Niyə HEÇ BİR mövcud kontrakt genişləndirilmir
------------------------------------------------
``JOURNAL_DATES_FIELDS.fingerprint`` J3-ün (``journal_lessons``) möhür reseptinə
qatlanır və oradan hər ``lesson_derivation_hash``-ə düşür.  Onu genişlətmək
artıq möhürlənmiş repetisiyaların ledger-inin yeni kodla TƏKRAR TÖRƏDİLƏ
BİLMƏMƏSİ deməkdir (2026-08-30-da ``YEKUN_FIELDS`` ilə məhz bu baş verdi).
Dərs metadatası ona görə BURADA, öz barmaq izi ilə yaşayır: J3 toxunulmamış
qalır, yeni fazalar isə öz möhür nəsillərini alır.

Zəncir
------
``journals_dates_added_by_teacher`` (J3-ün dərs sətri) ilə
``journals_dates_rooms`` EYNİ slot açarını daşıyır::

    (journal_id, month, day, times)   ←→   (journal_id, month, day, time)

Canlı ölçü (rehearsal dump, 2026-08-30):

* ``journals_dates_rooms``: 291,509 sətir, ``fake=0`` olan 265,206;
* həmin ``fake=0`` sətirlər 265,176 fərqli slot açarı verir — yalnız **28**
  açarda 2+ sətir var (0.01 %).  Ambiqü açar fail-closed ATLANIR;
* dərs sətri tərəfindən baxanda: 325,531 birmənalı, 55 ambiqü, 53,629 uyğunsuz.

``journals_dates_rooms.room`` → ``rooms.id`` (264,924 həll olunur, 201 sətirdə
``room=0``, 81 sətirdə silinmiş otağa istinad).  ``rooms.bina`` KORPUS-dur
(1→43, 2→57, 3→44, 5→14 otaq).

``journals_dates_rooms.sillabus`` → ``sillabus_sem_muh.id`` (263,245 həll
olunur).  ⚠️ Bu ``sillabus.id`` DEYİL: eyni sütun ``sillabus`` cədvəlinə cəmi
15,032 sətirdə düşür, ``sillabus_sem_muh``-a isə 99.3 % — yəni doğru hədəf
mövzu cədvəlidir.  ``sillabus_sem_muh.movzu`` = DƏRSİN MÖVZUSU.

Gate qeydi
----------
``sillabus_sem_muh`` plan-da ``design_gated``-dir, yəni HEÇ BİR faza onu batch
zəncirinə İDDİA ETMİR.  Gated olmaq İDDİAya qadağa qoyur, OXUMAĞA yox — bax
``rehearsal_contracts`` seam qeydi və J9 presedenti.  ``journals_dates_rooms``
ilə ``rooms`` ``review_gated``-dir (iddia edilə bilər), amma bu fazalar da
``source_tables = ()`` elan edir: sübutları tamamilə öz müşahidələrində və
digest zəncirlərində yaşayır (J9 ilə eyni forma).
"""

from __future__ import annotations

from .field_contracts import LegacySourceFieldContract

# Dərs-səviyyə metadata sətri.  Proyeksiya default-deny-dir: OXUNMAYAN sütun
# mənbədən heç vaxt çıxmamalıdır, ona görə ``date`` və ``sem_muh`` QƏSDƏN
# kənardadır.  ``date`` cəlbedici görünür, amma dərsin tarixi J3-də semestrin
# ilindən törədilir (``parse_lesson_schedule``) və hədəf sətri MƏHZ o tarixlə
# açarlanır — ikinci, uyğunlaşdırılmamış tarix mənbəyi oxumaq iki fazanı
# səssizcə ayırardı.  ``sem_muh`` isə dərs NÖVÜ üçündür və o qərar artıq
# ``rehearsal_journal_lesson_kinds``-də xanalar üzərində verilib.
LESSON_ROOM_FIELDS = LegacySourceFieldContract(
    source_table="journals_dates_rooms",
    version="lesson-meta-v1",
    allowed_fields=(
        "id",
        "journal_id",
        "month",
        "day",
        "times",
        "room",
        "sillabus",
        "saatliq_ders",
        "fake",
    ),
)

# Otaq reyestri (158 sətir).  ``department_id``/``type``/``kollec_or_uni``
# kənardadır: hədəf ``exams.ExamRoom`` onları daşımır, deməli onları oxumaq
# üçün səbəb yoxdur.  ``who_is_added`` isə aktor izidir — import heç kimin
# adından yazmır.
ROOM_REGISTRY_FIELDS = LegacySourceFieldContract(
    source_table="rooms",
    version="lesson-meta-v1",
    allowed_fields=("id", "name", "bina", "max_student_count"),
)

# Mövzu mətninin özü.  ``movzu`` varchar(500)-dür və HTML entity daşıyır
# (``&uuml;``, ``&#601;``) — ``legacy_text.clean_text`` onları üç keçidlə açır,
# sonra NFC + boşluq normallaşdırması edib hədəfin 255 simvoluna kəsir.
# ``muh_saat``/``sem_saat``/``praktiki_saat``/``lab_saat`` QƏSDƏN kənardadır:
# onları oxuyan faza yoxdur, lazım olanda AYRICA kontraktla açılmalıdır.
SYLLABUS_TOPIC_FIELDS = LegacySourceFieldContract(
    source_table="sillabus_sem_muh",
    version="lesson-meta-v1",
    allowed_fields=("id", "movzu"),
)

__all__ = [
    "LESSON_ROOM_FIELDS",
    "ROOM_REGISTRY_FIELDS",
    "SYLLABUS_TOPIC_FIELDS",
]
