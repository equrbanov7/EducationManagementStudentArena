"""Sillabus KÖÇÜRMƏSİNİN audited mənbə kontraktları (12 cədvəl).

Niyə ``field_contracts`` DEYİL və niyə ``syllabus_field_contracts`` DEYİL
======================================================================
``field_contracts`` modul-ölçü qapısının (``scripts/check_module_size.py``,
SOFT_CAP=600) TAM tavanındadır — bir sətir də əlavə edilə bilməz.

``syllabus_field_contracts`` (J9) isə **genişlədilməməlidir**: onun
``SILLABUS_FIELDS`` və ``SILLABUS_SELF_WORK_FIELDS`` barmaq izləri J9-un
(``journal_selfwork``) möhür reseptinə qatılıb və oradan hər yazılmış
``source_row_hash``-ə düşüb.  Barmaq izini dəyişmək artıq möhürlənmiş
repetisiyaların ledger-inin yeni kodla TƏKRAR TÖRƏDİLƏ BİLMƏMƏSİ deməkdir
(2026-08-30-da ``YEKUN_FIELDS`` ilə məhz bu baş verdi).  Presedent:
``STUDENT_STATUS_FIELDS`` (``students``-in ikinci, dar kontraktı) və
``YEKUN_EVIDENCE_FIELDS`` (``yekun``-un ikinci, geniş kontraktı).

Ona görə burada ``sillabus`` və ``sillabus_sem_muh`` üçün AYRI, GENİŞ
``syllabus-migration-v1`` kontraktları var; J9-un dar kontraktları toxunulmaz
qalır və hər ikisi eyni cədvəldən paralel oxuya bilir.

⚠️ Fixture invariantı
---------------------
``compile_safe_projection`` kontraktın sxemin ALT-ÇOXLUĞU olmasını tələb edir.
Bir cədvəli İKİ kontrakt oxuyanda sintetik fixture onu GENİŞ proyeksiya ilə
qurmalıdır, əks halda dəst ``legacy_source_schema_contract_mismatch`` ilə çökür
(bax ``test_rehearsal_source_integration._FULL_TABLES``-dakı ``yekun`` qeydi).
Bu modul buna görə ``SUPERSET_INVARIANTS`` cütlərini elan edir və test onları
yükləmə anında yoxlayır.

Gate qeydi
----------
12 cədvəlin HAMISI plan-da ``design_gated``-dir, yəni heç bir faza onları batch
zəncirinə İDDİA ETMİR.  Gated olmaq İDDİAya qadağa qoyur, OXUMAĞA yox — bax
``rehearsal_contracts`` seam qeydi və J9/J11 presedenti.  Bu kontraktları oxuyan
faza ``source_tables = ()`` elan edir və sübutlarını öz müşahidələrində saxlayır.

⚠️ Canlı ölçmə (2026-08-30, ``emsarena-legacy-source-rehearsal``)
=================================================================
``docs/migration/SILLABUS_KOCURME_SPEC.md`` §1-dəki "Sətir" sütunu
``information_schema.tables.table_rows``-dan götürülüb — bu, InnoDB üçün
TƏXMİNDİR, sayğac deyil.  12 cədvəldən 11-i orada YANLIŞ yazılıb.  Həqiqi
``COUNT(*)`` dəyərləri ``table_plan``-dakı ``expected_rows`` ilə TAM üst-üstə
düşür (aşağıda), yəni plan doğrudur, sənəd yanlışdır::

    cədvəl                              COUNT(*)   DISTINCT uniqid   spec §1
    sillabus                               8,248             8,247     8,248 ✔
    sillabus_sem_muh                     131,056             8,220   132,905 ✘
    sillabus_serbest_is                   60,878             8,258    58,966 ✘
    sillabus_imtahan_suallari             20,835             1,553    19,750 ✘
    sillabus_derslikler                   16,476             8,258    16,238 ✘
    sillabus_elmi_maraq                   10,739             8,219    10,435 ✘
    sillabus_certificates                  9,846             8,176     9,672 ✘
    sillabus_eldeolunacaq_tecrubeler       8,261             8,260     8,091 ✘
    sillabus_dersin_islenme_formasi        8,261             8,260     8,021 ✘
    sillabus_yoxlama_formasi               8,261             8,260     7,714 ✘
    sillabus_tesviri_ve_meqsedi            6,491             6,491     5,217 ✘
    sillabus_qarsilama_mesaji              4,676             4,676     4,422 ✘

Peyk sətirlərinin HƏQİQİ cəmi **285,780**-dir (spec §6.4-dəki 279,431 deyil).
Uzlaşdırma balansı bu rəqəmin üzərində qurulmalıdır, yoxsa fail-closed olur.

⚠️ ``sillabus.uniqid`` UNİKAL DEYİL
-----------------------------------
8,248 sətir → 8,247 fərqli ``uniqid``.  ``htcVEP3we58POdhcgo0q`` HƏM
``sillabus.id=601`` (active=1), HƏM ``id=2386`` (active=0) tərəfindən daşınır;
hər ikisi eyni ``lesson_id=552``/``teacher_id=459`` cütüdür.  Peyklər yalnız
``uniqid`` ilə bağlandığına görə həmin uniqid-in bölmə sətirləri İKİ başlıq
arasında AMBİQÜDÜR — oxucu onları fail-closed olaraq işarələyir və heç bir
başlığa yazmır (``rehearsal_syllabus_source.AMBIGUOUS_UNIQID``).
"""

from __future__ import annotations

from .field_contracts import LegacySourceFieldContract
from .lesson_meta_field_contracts import SYLLABUS_TOPIC_FIELDS
from .syllabus_field_contracts import SILLABUS_FIELDS, SILLABUS_SELF_WORK_FIELDS

#: Bütün köçürmə kontraktlarının versiya damğası.  Barmaq izi
#: (cədvəl, versiya, sahələr) üçlüyündən çıxır, ona görə eyni sahə dəsti başqa
#: versiya altında BAŞQA barmaq izi verir — J9-un möhürü toxunulmur.
CONTRACT_VERSION = "syllabus-migration-v1"

# ── Başlıq ────────────────────────────────────────────────────────────────────
# QƏSDƏN kənarda qalan sütunlar — hamısı canlı mənbədə SABİTDİR, yəni onları
# oxumaq heç bir məlumat vermir, amma boru xəttinə "fakültə/qrup var" illüziyası
# gətirərdi (8,248 sətrin hamısında ölçülüb):
#   dekan_id=0, kafedra_id=0, ixtisas_id=0, qrup_id=0, birlesen_qruplar='',
#   status=0.
# Proyeksiya default-deny-dir: köçməyən sahə mənbədən heç vaxt çıxmır.
#
# DAXİL olanlar və səbəbi:
#   lesson_id  — 8,248/8,248 ``lessons``-a həll olunur (1,822 fərqli fənn);
#                sillabusun yeganə etibarlı əhatə açarı.
#   teacher_id — 7,292/8,248 ``workers``-ə həll olunur (669 fərqli müəllim);
#                956 sətir qırıqdır (işçi silinib) və ATILMIR — «müəllimi həll
#                olunmayıb» qeydi ilə köçürülür.
#   ders_saati — 8,246/8,248 sətirdə qeyri-sıfır; həftəlik saat cədvəlinin
#                yeganə mənbə-tərəf yekunu (J9-da qəsdən kənarda idi).
#   language   — canlı dəyərlər: az 5,766 · en 2,002 · ru 440 · '-' 40.
#                Sillabusun dili köçürülməsə çoxdilli fənn ayırd edilə bilmir.
#   active     — 7,534 aktiv / 714 qeyri-aktiv; qeyri-aktivlər ``ARCHIVED``.
SYLLABUS_HEADER_FIELDS = LegacySourceFieldContract(
    source_table="sillabus",
    version=CONTRACT_VERSION,
    allowed_fields=(
        "id",
        "uniqid",
        "lesson_id",
        "teacher_id",
        "ders_saati",
        "language",
        "active",
    ),
)

# ── Həftəlik mövzu planı ──────────────────────────────────────────────────────
# ``tarix`` QƏSDƏN kənardadır: 131,056 sətrin 131,056-sı BOŞDUR.  Boş sütunu
# oxumaq boru xəttinə "dərs tarixi var" illüziyası gətirər, halbuki sahibin
# gözlədiyi yaranma tarixi mənbədə ÜMUMİYYƏTLƏ yoxdur (spec §2).
#
# ``qeyd`` DAXİLDİR: 1,697 sətirdə doludur — az, amma real müəllim mətnidir və
# atılsa səssizcə itərdi.
#
# ⚠️ Dörd saat sütunu ``char(5)``-dir, rəqəm deyil.  Canlı dəyər fəzası:
# '' · '0' · '1'…'6' · '8' · '10'…'16' · '21' · '22' · '30' · '45' · '60' ·
# '75' · '120' · '01' · '02' · '0.5' · '2.' · '-' · '-+' · '2K' · 'ş' · '`1' ·
# '1`'.  ``rehearsal_syllabus_source.legacy_hour_cell`` onları fail-closed
# çevirir: kəsr YUVARLAQLAŞDIRILMIR, zibil UYDURULMUR.
SYLLABUS_WEEK_FIELDS = LegacySourceFieldContract(
    source_table="sillabus_sem_muh",
    version=CONTRACT_VERSION,
    allowed_fields=(
        "id",
        "uniqid",
        "movzu",
        "muh_saat",
        "sem_saat",
        "praktiki_saat",
        "lab_saat",
        "qeyd",
    ),
)


def _section_contract(source_table: str) -> LegacySourceFieldContract:
    """``id | uniqid | name`` formalı peyk cədvəli üçün kontrakt.

    On peykin sxemi HƏRFƏN eynidir (canlı ``DESCRIBE`` ilə təsdiqli), ona görə
    kontraktlar bir yerdən törəyir — əl ilə yazılmış on nüsxə arasında bir
    hərflik fərq səssiz sxem sürüşməsi olardı.  Barmaq izi yenə də hər cədvəl
    üçün AYRIDIR, çünki cədvəl adı barmaq izi materialındadır.
    """

    return LegacySourceFieldContract(
        source_table=source_table,
        version=CONTRACT_VERSION,
        allowed_fields=("id", "uniqid", "name"),
    )


SYLLABUS_EXAM_QUESTION_FIELDS = _section_contract("sillabus_imtahan_suallari")
SYLLABUS_LITERATURE_FIELDS = _section_contract("sillabus_derslikler")
SYLLABUS_RESEARCH_INTEREST_FIELDS = _section_contract("sillabus_elmi_maraq")
SYLLABUS_CERTIFICATE_FIELDS = _section_contract("sillabus_certificates")
SYLLABUS_OUTCOME_FIELDS = _section_contract("sillabus_eldeolunacaq_tecrubeler")
SYLLABUS_METHOD_FIELDS = _section_contract("sillabus_dersin_islenme_formasi")
SYLLABUS_ASSESSMENT_FIELDS = _section_contract("sillabus_yoxlama_formasi")
SYLLABUS_DESCRIPTION_FIELDS = _section_contract("sillabus_tesviri_ve_meqsedi")
SYLLABUS_WELCOME_FIELDS = _section_contract("sillabus_qarsilama_mesaji")

# ⚠️ ``sillabus_serbest_is`` üçün YENİ kontrakt YAZILMIR — J9-un
# ``SILLABUS_SELF_WORK_FIELDS``-i TƏKRAR İŞLƏDİLİR.  Səbəb: cədvəlin canlı
# sxemində CƏMİ üç sütun var (``id``, ``uniqid``, ``name``) və J9-un kontraktı
# onların HAMISINI oxuyur.  Yəni genişlətməyə ehtiyac YOXDUR (ona görə J9-un
# möhürü də təhlükədə deyil), eyni sahə dəstinin ikinci nüsxəsi isə yalnız
# heç nə sübut etməyən əlavə barmaq izi yaradardı.  Eyni məntiq ``sillabus``
# və ``sillabus_sem_muh``-a ŞAMİL OLUNMUR: orada J9/J11 kontraktları DARDIR
# (``id|uniqid`` və ``id|movzu``), köçürmə isə daha çox sütun tələb edir.
SYLLABUS_SELF_WORK_FIELDS = SILLABUS_SELF_WORK_FIELDS

#: Köçürmənin oxuduğu 12 kontrakt, mənbə cədvəlinin adına görə sabit sırada.
#: ``source_extraction._AUDITED_CONTRACTS`` bu dəsti bir sətirdə qeydiyyatdan
#: keçirir — allowlist yenə də KOD SAHİBLİYİNDƏDİR (dəst burada, əl ilə
#: yazılıb), sadəcə qeydiyyat 24 sətir yerinə 1 sətir tutur.  Bu vacibdir:
#: ``source_extraction`` 583/600 sətirdədir və modul-ölçü qapısı onu böyütməyə
#: qoymur.
SYLLABUS_MIGRATION_CONTRACTS = (
    SYLLABUS_HEADER_FIELDS,
    SYLLABUS_WEEK_FIELDS,
    SYLLABUS_SELF_WORK_FIELDS,
    SYLLABUS_EXAM_QUESTION_FIELDS,
    SYLLABUS_LITERATURE_FIELDS,
    SYLLABUS_RESEARCH_INTEREST_FIELDS,
    SYLLABUS_CERTIFICATE_FIELDS,
    SYLLABUS_OUTCOME_FIELDS,
    SYLLABUS_METHOD_FIELDS,
    SYLLABUS_ASSESSMENT_FIELDS,
    SYLLABUS_DESCRIPTION_FIELDS,
    SYLLABUS_WELCOME_FIELDS,
)

#: Bölmə cədvəli → kontrakt.  Sıra DİZAYNIN bölmə sırasına (README §3.2) görə
#: sabitdir və oxucunun sənəd qurma sırasını təyin edir; ``dict`` Python 3.7+
#: sırasını qoruyur, ona görə bu həm də deterministik iterasiya mənbəyidir.
SYLLABUS_SECTION_CONTRACTS = {
    "sillabus_qarsilama_mesaji": SYLLABUS_WELCOME_FIELDS,
    "sillabus_tesviri_ve_meqsedi": SYLLABUS_DESCRIPTION_FIELDS,
    "sillabus_eldeolunacaq_tecrubeler": SYLLABUS_OUTCOME_FIELDS,
    "sillabus_dersin_islenme_formasi": SYLLABUS_METHOD_FIELDS,
    "sillabus_yoxlama_formasi": SYLLABUS_ASSESSMENT_FIELDS,
    "sillabus_serbest_is": SYLLABUS_SELF_WORK_FIELDS,
    "sillabus_imtahan_suallari": SYLLABUS_EXAM_QUESTION_FIELDS,
    "sillabus_derslikler": SYLLABUS_LITERATURE_FIELDS,
    "sillabus_elmi_maraq": SYLLABUS_RESEARCH_INTEREST_FIELDS,
    "sillabus_certificates": SYLLABUS_CERTIFICATE_FIELDS,
}

#: (dar kontrakt, geniş kontrakt) — sintetik fixture cədvəli GENİŞ olanla
#: qurmalıdır.  Test modulu yüklənəndə yoxlayır; bax modul başlığındakı
#: «Fixture invariantı» qeydi.
SUPERSET_INVARIANTS = (
    # J9-un dar ``sillabus`` körpüsü (``id|uniqid``) ⊂ köçürmə başlığı.
    (SILLABUS_FIELDS, SYLLABUS_HEADER_FIELDS),
    # J11-in dar mövzu indeksi (``id|movzu``) ⊂ köçürmənin həftəlik planı.
    (SYLLABUS_TOPIC_FIELDS, SYLLABUS_WEEK_FIELDS),
)

__all__ = [
    "CONTRACT_VERSION",
    "SUPERSET_INVARIANTS",
    "SYLLABUS_ASSESSMENT_FIELDS",
    "SYLLABUS_CERTIFICATE_FIELDS",
    "SYLLABUS_DESCRIPTION_FIELDS",
    "SYLLABUS_EXAM_QUESTION_FIELDS",
    "SYLLABUS_HEADER_FIELDS",
    "SYLLABUS_LITERATURE_FIELDS",
    "SYLLABUS_METHOD_FIELDS",
    "SYLLABUS_MIGRATION_CONTRACTS",
    "SYLLABUS_OUTCOME_FIELDS",
    "SYLLABUS_RESEARCH_INTEREST_FIELDS",
    "SYLLABUS_SECTION_CONTRACTS",
    "SYLLABUS_SELF_WORK_FIELDS",
    "SYLLABUS_WEEK_FIELDS",
    "SYLLABUS_WELCOME_FIELDS",
]
