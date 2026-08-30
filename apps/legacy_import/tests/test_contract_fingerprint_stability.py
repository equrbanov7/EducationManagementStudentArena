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

import pytest

from apps.legacy_import.services.field_contracts import (
    ALLOWED_QB_FIELDS,
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
from apps.legacy_import.services.rehearsal_journal_entry_scores_phase import ENTRY_SCORE_SEALER
from apps.legacy_import.services.rehearsal_journal_reconcile_phase import RECONCILE_SEALER
from apps.legacy_import.services.source_extraction import _AUDITED_CONTRACTS

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


def test_every_pinned_contract_is_registered_as_audited():
    """Barmaq izi qapısı registry ilə eyni obyektə baxmalıdır.

    ``_AUDITED_CONTRACTS`` fingerprint ilə açarlanır: kontrakt yerində
    dəyişdirilsə açar da sürüşür, yəni bu bərabərlik həm də registry-nin
    köhnəlmədiyini yoxlayır.
    """

    for contract, _table, _version, fingerprint in PINNED_CONTRACTS:
        assert _AUDITED_CONTRACTS.get(fingerprint) is contract
