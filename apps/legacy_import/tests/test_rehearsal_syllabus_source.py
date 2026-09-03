"""Sillabus köçürmə oxucusunun saf funksiyaları və versiya nərdivanı.

Bu dəst MƏNBƏSİZDİR: axın qatı ``test_rehearsal_source_integration``-da real
MariaDB ilə sınanır, burada isə çevirmə qaydaları — saat xanası, dil, məzmun
digest-i və APPROVED seçkisi — sürətli, deterministik və izolyasiya olunmuş
şəkildə kilidlənir.

Bütün gözlənilən dəyərlər CANLI mənbə üzərində ölçülüb (2026-08-30,
``emsarena-legacy-source-rehearsal``); rəqəmlər docstring-lərdə yazılıb ki,
sonra kimsə "bu niyə belədir?" deyəndə cavab kodun içində olsun.
"""

import pytest

from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalEvidenceError
from apps.legacy_import.services.rehearsal_syllabus_documents import (
    NO_ACTIVE_VERSION,
    VERSION_FOLDED,
    SyllabusDocument,
    _elect_versions,
    content_digest,
)
from apps.legacy_import.services.rehearsal_syllabus_source import (
    HOUR_CELL_FRACTIONAL,
    HOUR_CELL_INVALID,
    HOUR_CELL_OUT_OF_RANGE,
    LANGUAGE_UNKNOWN,
    SyllabusHeaderRow,
    SyllabusSectionRow,
    SyllabusWeekRow,
    legacy_hour_cell,
    legacy_language,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Boş və '-' eyni mənadadır: saat yoxdur, anomaliya da yoxdur.
        ("", (0, "")),
        ("-", (0, "")),
        ("   ", (0, "")),
        # Açıq sıfır — canlı: lab_saat sütununda 22,638 sətir.
        ("0", (0, "")),
        # Adi dəyərlər; '01'/'02' sıfır prefiksli yazılışlardır (canlı: 98 sətir).
        ("2", (2, "")),
        ("02", (2, "")),
        ("01", (1, "")),
        ("12", (12, "")),
        # Tam qiymətli onluq qəbul olunur (J11 ``legacy_calendar_int`` semantikası).
        ("2.", (2, "")),
        ("3.0", (3, "")),
        # Kəsr YUVARLAQLAŞDIRILMIR (canlı: '0.5', 40 xana).
        ("0.5", (0, HOUR_CELL_FRACTIONAL)),
        # Bir həftə üçün ağlabatan tavandan böyük — semestr yekunu səhv xanada.
        ("15", (0, HOUR_CELL_OUT_OF_RANGE)),
        ("30", (0, HOUR_CELL_OUT_OF_RANGE)),
        ("120", (0, HOUR_CELL_OUT_OF_RANGE)),
        # Rəqəm olmayan zibil UYDURULMUR (canlı: 'ş', '2K', '`1', '1`', '-+').
        ("ş", (0, HOUR_CELL_INVALID)),
        ("2K", (0, HOUR_CELL_INVALID)),
        ("`1", (0, HOUR_CELL_INVALID)),
        ("1`", (0, HOUR_CELL_INVALID)),
        ("-+", (0, HOUR_CELL_INVALID)),
    ],
)
def test_legacy_hour_cell_covers_the_live_value_space(raw, expected):
    assert legacy_hour_cell(raw) == expected


def test_legacy_hour_cell_rejects_a_numeric_column():
    """Sütun ``char(5)``-dir.  Rəqəm gəlirsə bu sxem sürüşməsidir, konversiya yox."""

    with pytest.raises(LegacyRehearsalEvidenceError):
        legacy_hour_cell(2)
    with pytest.raises(LegacyRehearsalEvidenceError):
        legacy_hour_cell(2.0)


def test_legacy_language_keeps_only_the_known_catalogue():
    """Canlı dəyərlər: az 5,766 · en 2,002 · ru 440 · '-' 40."""

    assert legacy_language("az") == ("az", "")
    assert legacy_language("EN") == ("en", "")
    assert legacy_language("ru") == ("ru", "")
    # '-' dil deyil — BOŞ qalır, təxmin edilmir.
    assert legacy_language("-") == ("", LANGUAGE_UNKNOWN)
    assert legacy_language("") == ("", LANGUAGE_UNKNOWN)


def _header(legacy_pk, *, active=True, language="az", hours=45):
    return SyllabusHeaderRow(
        legacy_pk=legacy_pk,
        uniqid=f"syl-{legacy_pk}",
        lesson_id=4,
        teacher_id=282,
        lesson_hours=hours,
        language=language,
        active=active,
        issues=(),
    )


def _document(legacy_pk, *, topics=("A", "B"), active=True, literature=("kitab",)):
    return SyllabusDocument(
        header=_header(legacy_pk, active=active),
        week=tuple(
            SyllabusWeekRow(
                legacy_pk=index,
                topic=topic,
                note="",
                hours=(("lecture", 2), ("seminar", 0), ("practical", 0), ("lab", 0)),
                issues=(),
                truncated=False,
            )
            for index, topic in enumerate(topics, start=1)
        ),
        sections=(
            (
                "sillabus_derslikler",
                tuple(
                    SyllabusSectionRow(legacy_pk=index, text=text, truncated=False)
                    for index, text in enumerate(literature, start=1)
                ),
            ),
        ),
    )


def test_content_digest_ignores_identity_and_placement():
    """Digest MƏZMUNA baxır: ``id``/``uniqid``/``active`` onu dəyişməməlidir."""

    assert content_digest(_document(1)) == content_digest(_document(9, active=False))
    # Məzmun dəyişəndə digest də dəyişir.
    assert content_digest(_document(1)) != content_digest(_document(1, topics=("A", "C")))
    assert content_digest(_document(1)) != content_digest(_document(1, literature=("başqa",)))


def test_identical_documents_fold_into_one_version():
    """Eyni məzmunlu nüsxələr BİR versiyaya yığılır, ``id``-ləri isə itmir."""

    versions = _elect_versions((_document(3), _document(7), _document(11)))

    assert len(versions) == 1
    assert versions[0].version_number == 1
    # Nümayəndə ƏN KİÇİK ``id``-dir (orijinal), qalanları qeyd olunur.
    assert versions[0].document.header.legacy_pk == 3
    assert versions[0].folded_source_pks == (7, 11)
    assert VERSION_FOLDED in versions[0].issues
    assert versions[0].approved is True


def test_distinct_documents_become_a_version_ladder():
    """Fərqli məzmun = fərqli versiya; ƏN SONUNCU aktiv olan APPROVED-dur.

    Canlı mənbədə spec §4-ün nümunəsi (``lesson_id=4, teacher_id=282``) MƏHZ
    belədir: 7 sillabusun hər birində 23 mövzu var, amma MÖVZU MƏTNLƏRİ
    fərqlidir — yəni onlar nüsxə deyil, redaktə tarixçəsidir.
    """

    versions = _elect_versions(
        (
            _document(1, topics=("A",)),
            _document(2, topics=("A", "B")),
            _document(3, topics=("A", "B", "C")),
        )
    )

    assert [version.version_number for version in versions] == [1, 2, 3]
    assert [version.document.header.legacy_pk for version in versions] == [1, 2, 3]
    assert [version.approved for version in versions] == [False, False, True]
    assert all(not version.folded_source_pks for version in versions)


def test_an_inactive_tail_cannot_win_the_approved_slot():
    """714 qeyri-aktiv başlıq mənbədə AÇIQ söndürülüb — APPROVED seçilə bilməz."""

    versions = _elect_versions(
        (
            _document(1, topics=("A",)),
            _document(2, topics=("A", "B")),
            _document(3, topics=("A", "B", "C"), active=False),
        )
    )

    assert [version.approved for version in versions] == [False, True, False]


def test_a_fully_inactive_ladder_elects_nobody():
    """Heç bir aktiv başlıq yoxdursa uydurma APPROVED yaradılmır."""

    versions = _elect_versions(
        (
            _document(1, topics=("A",), active=False),
            _document(2, topics=("A", "B"), active=False),
        )
    )

    assert not any(version.approved for version in versions)
    assert all(NO_ACTIVE_VERSION in version.issues for version in versions)


def test_folding_carries_the_active_flag_of_every_sibling():
    """Qatlanan qardaşlardan biri aktivdirsə versiya APPROVED ola bilər.

    Nümayəndə (ən kiçik ``id``) qeyri-aktiv olsa da, eyni məzmunun sonrakı
    aktiv nüsxəsi versiyanı canlı saxlayır — əks halda tamamilə real bir
    sillabus yalnız nüsxələmə artefaktına görə arxivə düşərdi.
    """

    versions = _elect_versions((_document(1, active=False), _document(2, active=True)))

    assert len(versions) == 1
    assert versions[0].document.header.legacy_pk == 1
    assert versions[0].folded_source_pks == (2,)
    assert versions[0].approved is True
