"""Kontrakt barmaq izlərinin PİNLƏNMİŞ regressiya qapısı.

Niyə bu fayl var
----------------
``LegacySourceFieldContract.fingerprint`` sadəcə daxili detal deyil — o,
faza möhürlərinin (``JournalSealer.contract_fingerprint``) tərkibinə girir və
oradan hər ``derivation_hash``-ə düşür.  Yəni bir kontraktın ``version`` və ya
``allowed_fields`` dəyərini YERİNDƏ dəyişmək artıq möhürlənmiş repetisiyaların
ledger-inin yeni kodla TƏKRAR TÖRƏDİLƏ BİLMƏMƏSİ deməkdir.

2026-08-30-da məhz bu baş verdi: ``YEKUN_FIELDS`` ``journal-v1``→``journal-v2``
edilib 7 sahədən 12-yə çıxarıldı.  Registry qapısı (``_AUDITED_CONTRACTS``)
kontrakt barmaq izlərini əhatə etmədiyi üçün dəyişiklik SƏSSİZ keçdi və J5b
(``journal_entry_scores``) ilə J8 (``journal_reconcile``) fazalarının
digest-lərini dəyişdi.

Buna görə aşağıdakı hexlər QƏSDƏN sabit kodlanıb.  Bu testlərdən biri çökürsə,
düzgün cavab dəyəri yeniləmək DEYİL:

* Yeni sütunlar bir fazaya lazımdırsa → AYRICA kontrakt yarat (J9-un
  ``JOURNAL_SYLLABUS_FIELDS``-i və qiymət sübutunun ``YEKUN_EVIDENCE_FIELDS``-i
  bu presedentdir), paylaşılanı genişlətmə.
* Möhür resepti həqiqətən dəyişməlidirsə → bu şüurlu qərardır: köhnə
  repetisiyaların yenidən törədilə bilməyəcəyini qəbul et, hexi yenilə və
  səbəbini commit mesajında yaz.
"""

import hashlib

import pytest

from apps.legacy_import.services.excuse_field_contracts import ALLOWED_QB_DOCUMENT_FIELDS
from apps.legacy_import.services.field_contracts import (
    ALLOWED_QB_FIELDS,
    JOURNAL_DATES_FIELDS,
    JOURNAL_FIELDS,
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    YEKUN_FIELDS,
)
from apps.legacy_import.services.legacy_grade_field_contracts import (
    EXAM_ENTRY_EXIT_FIELDS,
    SCORE_SHEET_EXPORT_FIELDS,
    YEKUN_EVIDENCE_FIELDS,
)
from apps.legacy_import.services.lesson_meta_field_contracts import (
    LESSON_ROOM_FIELDS,
    ROOM_REGISTRY_FIELDS,
    SYLLABUS_TOPIC_FIELDS,
)
from apps.legacy_import.services.rehearsal_contracts import encoded_part
from apps.legacy_import.services.rehearsal_journal_entry_scores_phase import ENTRY_SCORE_SEALER
from apps.legacy_import.services.rehearsal_journal_lessons_targets import lesson_derivation_hash
from apps.legacy_import.services.rehearsal_journal_reconcile_phase import RECONCILE_SEALER
from apps.legacy_import.services.source_extraction import _AUDITED_CONTRACTS
from apps.legacy_import.services.syllabus_field_contracts import (
    SILLABUS_FIELDS,
    SILLABUS_SELF_WORK_FIELDS,
)
from apps.legacy_import.services.syllabus_migration_contracts import (
    SYLLABUS_ASSESSMENT_FIELDS,
    SYLLABUS_CERTIFICATE_FIELDS,
    SYLLABUS_DESCRIPTION_FIELDS,
    SYLLABUS_EXAM_QUESTION_FIELDS,
    SYLLABUS_HEADER_FIELDS,
    SYLLABUS_LITERATURE_FIELDS,
    SYLLABUS_METHOD_FIELDS,
    SYLLABUS_MIGRATION_CONTRACTS,
    SYLLABUS_OUTCOME_FIELDS,
    SYLLABUS_RESEARCH_INTEREST_FIELDS,
    SYLLABUS_SECTION_CONTRACTS,
    SYLLABUS_WEEK_FIELDS,
    SYLLABUS_WELCOME_FIELDS,
)

# (kontrakt, gözlənilən source_table, gözlənilən version, pinlənmiş fingerprint)
PINNED_CONTRACTS = (
    (
        YEKUN_FIELDS,
        "yekun",
        "journal-v1",
        "cf542fc060773d38b016dd950133d0e1fff5822f99511f33af8f9a0790019ddc",
    ),
    (
        JOURNAL_FIELDS,
        "journals",
        "journal-v1",
        "baf023866e12717c7d6c42f20e1ded37e5fbdd36f8d63f0c11989593956dcd5c",
    ),
    (
        JOURNAL_POINT_FIELDS,
        "journals_dates_points",
        "journal-v1",
        "ac72d9df4b386e9be70c846b0581571cb2fd17e8ce5c65cec743343777450802",
    ),
    (
        JOURNAL_POINT_ARCHIVE_FIELDS,
        "journals_dates_points_archive",
        "journal-v1",
        "33ee560b2403b73bb0919fc76ad9b99aa7f721222ad0ad4baf176a9f85ed4f1d",
    ),
    (
        ALLOWED_QB_FIELDS,
        "allowed_qb",
        "journal-v1",
        "d1bcf25ef18b20c9b36de2d9ac1903332d66ee1d7acf3dc13519c7c607c02634",
    ),
    # J13 (journal_excuse_documents): ``allowed_qb``-ın GENİŞ sənəd proyeksiyası.
    # Dar ``journal-v1`` ilə YANAŞI yaşayır; onu genişlətmək J4-ün bütün
    # ``source_row_hash`` dəyərlərini dəyişərdi.
    (
        ALLOWED_QB_DOCUMENT_FIELDS,
        "allowed_qb",
        "excuse-v1",
        "869d464e7fe9969890fc3998ddd2483a94ce94e83adc9bf909797eb56500c02c",
    ),
    (
        YEKUN_EVIDENCE_FIELDS,
        "yekun",
        "grade-evidence-v1",
        "3a8ae4fbdb3deaae4d1cf3c32d2f6373bc025a876337521580c9e71dcdea711b",
    ),
    (
        EXAM_ENTRY_EXIT_FIELDS,
        "imthngrscxsblr",
        "legacy-grade-v1",
        "706d7f799b02d92be6962bc8f2998963fcf0381f187f4e7d6a684ba0bf458e0c",
    ),
    (
        SCORE_SHEET_EXPORT_FIELDS,
        "balvereqi_logs",
        "legacy-grade-v1",
        "fbce55ed5d519ef903e0876bf73a1871a5f07961914e797432a6db93e8c00ca7",
    ),
    # J10/J11 (legacy_rooms + journal_lesson_meta).  ``LESSON_ROOM_FIELDS``
    # J3-ün ``JOURNAL_DATES_FIELDS``-indən AYRIDIR: paylaşılanı genişlətmək
    # J3-ün BÜTÜN ``lesson_derivation_hash``-lərini dəyişərdi.
    (
        LESSON_ROOM_FIELDS,
        "journals_dates_rooms",
        "lesson-meta-v1",
        "969f0fb15c7d533dc0b247bddef294560d766d0be1148346ecbf9e64683c7f8e",
    ),
    (
        ROOM_REGISTRY_FIELDS,
        "rooms",
        "lesson-meta-v1",
        "e2de4897f042768afca0b8ca9fc22ecff27d609235e5618cdd7e8303bc346f41",
    ),
    (
        SYLLABUS_TOPIC_FIELDS,
        "sillabus_sem_muh",
        "lesson-meta-v1",
        "1faf9df56c3a594ce0af00b78fb49b98d880b908602f5c104fa9f531ec5f4485",
    ),
    # Sillabus KÖÇÜRMƏSİ (12 cədvəl).  ``sillabus`` və ``sillabus_sem_muh``
    # üçün AYRI, GENİŞ kontraktlar var: J9-un ``SILLABUS_FIELDS``-ini və
    # J11-in ``SYLLABUS_TOPIC_FIELDS``-ini genişlətmək onların möhürlərini
    # dağıdardı.  ``sillabus_serbest_is`` isə burada YOXDUR — J9-un
    # ``SILLABUS_SELF_WORK_FIELDS``-i olduğu kimi təkrar işlədilir (cədvəldə
    # cəmi üç sütun var, genişlətməyə ehtiyac yoxdur).
    (
        SYLLABUS_HEADER_FIELDS,
        "sillabus",
        "syllabus-migration-v1",
        "32c043585e30155e47ed224965037e062340316327a24f1368a01a6b40953010",
    ),
    (
        SYLLABUS_WEEK_FIELDS,
        "sillabus_sem_muh",
        "syllabus-migration-v1",
        "a25af377bc0db5be5be9b47ab8f74f4d94cead01ebab79c38d097b2bf595c0cb",
    ),
    (
        SYLLABUS_EXAM_QUESTION_FIELDS,
        "sillabus_imtahan_suallari",
        "syllabus-migration-v1",
        "dc7aeef5fe2774d9ffb186a18546f2054cabe5ed0868de652bc92452c5f9cc83",
    ),
    (
        SYLLABUS_LITERATURE_FIELDS,
        "sillabus_derslikler",
        "syllabus-migration-v1",
        "d3bab7b8dc733b8d923692c8485c0921f833cdc88469fc75927dd8be2b1da0fc",
    ),
    (
        SYLLABUS_RESEARCH_INTEREST_FIELDS,
        "sillabus_elmi_maraq",
        "syllabus-migration-v1",
        "293d1e051d1bfe1f8b37fb38398daa7e1ff61c6026851c18e2a181e02bccccd5",
    ),
    (
        SYLLABUS_CERTIFICATE_FIELDS,
        "sillabus_certificates",
        "syllabus-migration-v1",
        "eebebf00c506f87ddd6d45521a7c7a1fcfb71bab5ef0e22163515dc2aef1d150",
    ),
    (
        SYLLABUS_OUTCOME_FIELDS,
        "sillabus_eldeolunacaq_tecrubeler",
        "syllabus-migration-v1",
        "ec87e42f6e4aa1f8d3083aa616b103d4eadfd7b5fbc7b2dbc500146171f25da1",
    ),
    (
        SYLLABUS_METHOD_FIELDS,
        "sillabus_dersin_islenme_formasi",
        "syllabus-migration-v1",
        "e44c643922f025857149d287e998dfb0cbee1d9384405ae8441d330d4a3b2693",
    ),
    (
        SYLLABUS_ASSESSMENT_FIELDS,
        "sillabus_yoxlama_formasi",
        "syllabus-migration-v1",
        "e5cc656a64b3e6f3a39daf4a4c6572eeed5621c5ff49493323a49f1a5e510219",
    ),
    (
        SYLLABUS_DESCRIPTION_FIELDS,
        "sillabus_tesviri_ve_meqsedi",
        "syllabus-migration-v1",
        "3d29553ba544de059219eaf7d8bab16246040f7498d37107cfc7b664cf116ad3",
    ),
    (
        SYLLABUS_WELCOME_FIELDS,
        "sillabus_qarsilama_mesaji",
        "syllabus-migration-v1",
        "f02e5c27b2d32c4e3d01cc73f8c2410abddac9f339d23e23644f60c75b6fda57",
    ),
)


@pytest.mark.parametrize(
    ("contract", "source_table", "version", "fingerprint"),
    PINNED_CONTRACTS,
    ids=[item[0].source_table + ":" + item[2] for item in PINNED_CONTRACTS],
)
def test_contract_fingerprint_is_pinned(contract, source_table, version, fingerprint):
    """Yuxarıdakı modul docstring-ini oxumadan bu dəyərləri YENİLƏMƏ."""

    assert contract.source_table == source_table
    assert contract.version == version
    assert contract.fingerprint == fingerprint


def test_yekun_projections_stay_separate_contracts():
    """``yekun``-a iki proyeksiya var və onlar bir-birinə qarışmamalıdır.

    Bu qapı 2026-08-30 reqressiyasının birbaşa əksidir: qiymət sübutunun geniş
    sütun dəsti J5b/J8-in dar kontraktına GERİ sızarsa test çökür.
    """

    assert YEKUN_FIELDS.source_table == YEKUN_EVIDENCE_FIELDS.source_table == "yekun"
    assert YEKUN_FIELDS.fingerprint != YEKUN_EVIDENCE_FIELDS.fingerprint

    # Dar kontrakt J5b/J8 üçün: təsdiqlənməmiş semantikalı sütunlar KƏNARDA.
    assert YEKUN_FIELDS.allowed_fields == (
        "id",
        "student_id",
        "lesson_id",
        "journal_id",
        "girish",
        "imtahanda",
        "yekun",
    )
    drifted = {"group_id", "kesr", "guzest_girish", "level", "guzest_artim"}
    assert not drifted & set(YEKUN_FIELDS.allowed_fields)

    # Geniş kontrakt dar olanın üstünə qurulur — sübut fazası itkisiz olmalıdır.
    assert set(YEKUN_FIELDS.allowed_fields) < set(YEKUN_EVIDENCE_FIELDS.allowed_fields)
    assert drifted < set(YEKUN_EVIDENCE_FIELDS.allowed_fields)

    # Versiya nəsilləri ayrıdır: eyni cədvəl, fərqli ailə.
    assert YEKUN_FIELDS.version.startswith("journal-")
    assert not YEKUN_EVIDENCE_FIELDS.version.startswith("journal-")


def test_journal_seal_recipes_bind_the_narrow_yekun_contract():
    """J5b/J8 möhürləri məhz dar kontraktın barmaq izini daşımalıdır.

    Möhür resepti dəyişsə köhnə repetisiyaların ledger-i yenidən törədilə
    bilməz; ona görə bu bağ testlə kilidlənir.
    """

    for sealer in (ENTRY_SCORE_SEALER, RECONCILE_SEALER):
        assert sealer.source_table == "yekun"
        assert sealer.contract_fingerprint == YEKUN_FIELDS.fingerprint
        assert sealer.contract_fingerprint != YEKUN_EVIDENCE_FIELDS.fingerprint


def test_lesson_metadata_stays_off_the_j3_lesson_contract():
    """Dərs metadatası J3-ün möhür reseptinə SIZMAMALIDIR.

    J3 (``journal_lessons``) hər dərs qərarını ``JOURNAL_DATES_FIELDS``
    barmaq izi ilə möhürləyir.  Mövzu/otaq/saat sütunlarını həmin kontrakta
    qatmaq bütün köhnə repetisiyaların ledger-ini yenidən törədilməz edərdi —
    ona görə metadata AYRICA cədvəldən, AYRICA kontraktla oxunur.
    """

    assert JOURNAL_DATES_FIELDS.source_table == "journals_dates_added_by_teacher"
    assert LESSON_ROOM_FIELDS.source_table == "journals_dates_rooms"
    assert JOURNAL_DATES_FIELDS.fingerprint != LESSON_ROOM_FIELDS.fingerprint
    # J3-ün proyeksiyası dar qalır: metadata sütunları oraya girmir.
    assert JOURNAL_DATES_FIELDS.allowed_fields == ("id", "journal_id", "month", "day", "time")
    assert not {"room", "sillabus", "saatliq_ders"} & set(JOURNAL_DATES_FIELDS.allowed_fields)
    # J3-ün derivation resepti hələ də DAR kontraktın barmaq izini daşıyır.
    assert (
        lesson_derivation_hash(
            legacy_pk=1,
            row_hash="a" * 64,
            outcome_token="materialised",
            journal_ref="2",
            date_text="2021-12-30",
            time_text="14:00",
        )
        == _expected_lesson_hash()
    )


def _expected_lesson_hash() -> str:
    digest = hashlib.sha256(b"legacy-rehearsal-journal-lesson-derivation-v1\x00")
    for part in (JOURNAL_DATES_FIELDS.fingerprint, "1", "a" * 64, "materialised", "2", "2021-12-30", "14:00", "", ""):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def test_every_pinned_contract_is_registered_as_audited():
    """Barmaq izi qapısı registry ilə eyni obyektə baxmalıdır.

    ``_AUDITED_CONTRACTS`` fingerprint ilə açarlanır: kontrakt yerində
    dəyişdirilsə açar da sürüşür, yəni bu bərabərlik həm də registry-nin
    köhnəlmədiyini yoxlayır.
    """

    for contract, _table, _version, fingerprint in PINNED_CONTRACTS:
        assert _AUDITED_CONTRACTS.get(fingerprint) is contract


def test_syllabus_migration_contracts_stay_off_the_j9_and_j11_recipes():
    """Köçürmə ``sillabus``/``sillabus_sem_muh``-u GENİŞ oxuyur — ayrı kontraktla.

    J9 (``journal_selfwork``) ``SILLABUS_FIELDS``-i, J11
    (``journal_lesson_meta``) isə ``SYLLABUS_TOPIC_FIELDS``-i möhürləyib.
    Köçürməyə lazım olan əlavə sütunları həmin kontraktlara qatmaq onların
    barmaq izlərini — və oradan hər yazılmış ``source_row_hash``-i — dəyişərdi.
    Bu qapı məhz o sızmanın qarşısını alır.
    """

    assert SILLABUS_FIELDS.source_table == SYLLABUS_HEADER_FIELDS.source_table == "sillabus"
    assert SILLABUS_FIELDS.fingerprint != SYLLABUS_HEADER_FIELDS.fingerprint
    assert SYLLABUS_TOPIC_FIELDS.source_table == SYLLABUS_WEEK_FIELDS.source_table == "sillabus_sem_muh"
    assert SYLLABUS_TOPIC_FIELDS.fingerprint != SYLLABUS_WEEK_FIELDS.fingerprint

    # Dar kontraktlar DAR qalır: köçürmənin sütunları oraya girmir.
    assert SILLABUS_FIELDS.allowed_fields == ("id", "uniqid")
    assert SYLLABUS_TOPIC_FIELDS.allowed_fields == ("id", "movzu")

    # Geniş kontraktlar dar olanların ÜSTÜNƏ qurulur — sintetik fixture
    # cədvəli geniş proyeksiya ilə yaradanda hər iki oxucuya xidmət edir
    # (``compile_safe_projection`` alt-çoxluq tələbi).
    assert set(SILLABUS_FIELDS.allowed_fields) < set(SYLLABUS_HEADER_FIELDS.allowed_fields)
    assert set(SYLLABUS_TOPIC_FIELDS.allowed_fields) < set(SYLLABUS_WEEK_FIELDS.allowed_fields)

    # Sabit olduğu SÜBUT EDİLMİŞ sütunlar proyeksiyaya girmir: onları oxumaq
    # boru xəttinə olmayan fakültə/qrup/təsdiq ölçüsü gətirərdi.
    constant_columns = {"dekan_id", "kafedra_id", "ixtisas_id", "qrup_id", "birlesen_qruplar", "status"}
    assert not constant_columns & set(SYLLABUS_HEADER_FIELDS.allowed_fields)
    # ``tarix`` 131,056/131,056 sətirdə BOŞDUR — oxunmur.
    assert "tarix" not in SYLLABUS_WEEK_FIELDS.allowed_fields


def test_syllabus_migration_contracts_are_registered_and_distinct():
    """12 kontraktın hamısı audited allowlist-dədir və barmaq izləri fərqlidir."""

    assert len(SYLLABUS_MIGRATION_CONTRACTS) == 12
    fingerprints = {contract.fingerprint for contract in SYLLABUS_MIGRATION_CONTRACTS}
    assert len(fingerprints) == 12
    for contract in SYLLABUS_MIGRATION_CONTRACTS:
        assert _AUDITED_CONTRACTS.get(contract.fingerprint) is contract

    # 10 bölmə peyki + başlıq + həftəlik plan = 12; sərbəst iş J9-un
    # kontraktını TƏKRAR İŞLƏDİR, ona görə ayrıca barmaq izi yaranmır.
    assert len(SYLLABUS_SECTION_CONTRACTS) == 10
    assert SYLLABUS_SECTION_CONTRACTS["sillabus_serbest_is"] is SILLABUS_SELF_WORK_FIELDS
    assert set(SYLLABUS_SECTION_CONTRACTS.values()) <= set(SYLLABUS_MIGRATION_CONTRACTS)
