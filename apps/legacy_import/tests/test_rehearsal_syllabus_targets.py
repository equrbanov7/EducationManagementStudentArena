"""J12-nin HƏDƏF xəritəsi: bölmə açarları, saat növləri və issue taksonomiyası.

Bu dəst MƏNBƏSİZ və DB-SİZdir — yalnız saf çevirmə.  Ən vacib assert budur:
``rehearsal_syllabus_targets``-dakı sətir sabitləri (``info``/``desc``/… və
``approved``/``archived``) ``apps.syllabus.constants``-dakı kataloqla HƏRFƏN
eynidir.  Faza modul-səviyyədə sillabus modulunu idxal etmir (sərhəd qrafında
yeni tıl yaranmasın deyə), ona görə bərabərliyi məhz bu test kilidləyir.
"""

import pytest

from apps.legacy_import.models import LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_syllabus_documents import (
    INSTRUCTOR_UNRESOLVED,
    NO_ACTIVE_VERSION,
    VERSION_FOLDED,
    SyllabusDocument,
)
from apps.legacy_import.services.rehearsal_syllabus_source import (
    AMBIGUOUS_UNIQID,
    HOUR_CELL_FRACTIONAL,
    HOUR_CELL_INVALID,
    HOUR_CELL_OUT_OF_RANGE,
    LANGUAGE_UNKNOWN,
    ORPHAN_UNIQID,
    SyllabusHeaderRow,
    SyllabusSectionRow,
    SyllabusWeekRow,
)
from apps.legacy_import.services.rehearsal_syllabus_targets import (
    ASSESSMENT_NOTE_UNSURFACED,
    ASSESSMENT_TABLE,
    BLANK_ROW_DROPPED,
    CERTIFICATE_TABLE,
    DESCRIPTION_TABLE,
    DOSSIER_MERGED,
    EXAM_QUESTION_TABLE,
    EXAM_QUESTIONS_UNSURFACED,
    ISSUE_SEVERITY,
    LITERATURE_TABLE,
    METHOD_TABLE,
    OUTCOME_TABLE,
    PRACTICAL_UNSURFACED,
    RESEARCH_TABLE,
    SECTION_IDS,
    SECTIONS_EMPTY,
    SELF_WORK_TABLE,
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    SUBJECT_UNRESOLVED,
    SYLLABUS_VERSION_MODEL_LABEL,
    TARGET_HOUR_KINDS,
    TARGET_WEEK_ROWS,
    TEACHER_PROFILE_UNSURFACED,
    TEXT_TRUNCATED,
    WEEK_ROWS_EXCEED_PLAN,
    WELCOME_TABLE,
    WELCOME_UNSURFACED,
    build_section_data,
)
from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _header(**overrides):
    values = {
        "legacy_pk": 1,
        "uniqid": "syl-1",
        "lesson_id": 64,
        "teacher_id": 17,
        "lesson_hours": 45,
        "language": "az",
        "active": True,
        "issues": (),
    }
    values.update(overrides)
    return SyllabusHeaderRow(**values)


def _week(legacy_pk, *, topic="Mövzu", note="", hours=(("lecture", 2),), issues=(), truncated=False):
    return SyllabusWeekRow(
        legacy_pk=legacy_pk, topic=topic, note=note, hours=tuple(hours), issues=tuple(issues), truncated=truncated
    )


def _section(legacy_pk, text, *, truncated=False):
    return SyllabusSectionRow(legacy_pk=legacy_pk, text=text, truncated=truncated)


def _document(*, week=(), sections=None, header=None):
    rows = dict(sections or {})
    return SyllabusDocument(
        header=header or _header(),
        week=tuple(week),
        sections=tuple((table, tuple(rows.get(table, ()))) for table in SYLLABUS_SECTION_CONTRACTS),
    )


# ── hədəf kataloqu ilə bərabərlik ────────────────────────────────────────────


def test_section_ids_are_literally_the_shipped_section_catalogue():
    from apps.syllabus.constants import LESSON_HOUR_KINDS, WEEK_ROWS, SectionKey, SyllabusStatus

    assert SECTION_IDS == tuple(choice.value for choice in SectionKey)
    assert TARGET_HOUR_KINDS == LESSON_HOUR_KINDS
    assert TARGET_WEEK_ROWS == WEEK_ROWS
    assert (STATUS_APPROVED, STATUS_ARCHIVED) == (SyllabusStatus.APPROVED.value, SyllabusStatus.ARCHIVED.value)


def test_the_ledger_target_label_names_the_shipped_version_model():
    from apps.syllabus.models import SyllabusVersion

    assert SYLLABUS_VERSION_MODEL_LABEL == SyllabusVersion._meta.label_lower


def test_issue_severity_covers_exactly_the_j12_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        SUBJECT_UNRESOLVED: "warning",
        INSTRUCTOR_UNRESOLVED: "warning",
        AMBIGUOUS_UNIQID: "warning",
        ORPHAN_UNIQID: "warning",
        HOUR_CELL_FRACTIONAL: "warning",
        HOUR_CELL_INVALID: "warning",
        HOUR_CELL_OUT_OF_RANGE: "warning",
        TEXT_TRUNCATED: "warning",
        LANGUAGE_UNKNOWN: "info",
        VERSION_FOLDED: "info",
        NO_ACTIVE_VERSION: "info",
        DOSSIER_MERGED: "info",
        SECTIONS_EMPTY: "info",
        BLANK_ROW_DROPPED: "info",
        WEEK_ROWS_EXCEED_PLAN: "info",
        PRACTICAL_UNSURFACED: "info",
        WELCOME_UNSURFACED: "info",
        EXAM_QUESTIONS_UNSURFACED: "info",
        ASSESSMENT_NOTE_UNSURFACED: "info",
        TEACHER_PROFILE_UNSURFACED: "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


# ── bölmə xəritəsi ───────────────────────────────────────────────────────────


def test_every_satellite_lands_in_its_designed_section():
    data, _codes = build_section_data(
        _document(
            week=[_week(1, topic="Birinci mövzu")],
            sections={
                DESCRIPTION_TABLE: [_section(1, "Fənnin təsviri")],
                OUTCOME_TABLE: [_section(1, "Nəticə A"), _section(2, "Nəticə B")],
                METHOD_TABLE: [_section(1, "Mühazirə")],
                ASSESSMENT_TABLE: [_section(1, "Yoxlama forması")],
                SELF_WORK_TABLE: [_section(1, "Sərbəst iş 1")],
                LITERATURE_TABLE: [_section(1, "Dərslik A")],
            },
        )
    )

    assert tuple(data) == SECTION_IDS
    assert data["desc"] == {"description": "Fənnin təsviri", "goal": ""}
    assert data["out"] == {"outcomes": ["Nəticə A", "Nəticə B"]}
    assert data["method"] == {"methods": ["Mühazirə"], "note": ""}
    assert data["assess"]["note"] == "Yoxlama forması"
    assert data["self"]["topics"] == [{"title": "Sərbəst iş 1"}]
    assert data["lit"] == {"primary": ["Dərslik A"], "additional": []}
    assert data["prev"] == {} and data["send"] == {}


def test_the_three_unsurfaced_families_are_stored_and_counted():
    """Qarşılama, imtahan sualları və müəllim profili — data itmir, sayılır."""

    data, codes = build_section_data(
        _document(
            sections={
                WELCOME_TABLE: [_section(1, "Xoş gəldiniz"), _section(2, "İkinci abzas")],
                EXAM_QUESTION_TABLE: [_section(1, "Sual 1")],
                RESEARCH_TABLE: [_section(1, "Süni intellekt")],
                CERTIFICATE_TABLE: [_section(1, "PMP")],
            }
        )
    )

    assert data["info"]["welcome"] == "Xoş gəldiniz\n\nİkinci abzas"
    assert data["assess"]["exam_questions"] == ["Sual 1"]
    assert data["info"]["research_interests"] == ["Süni intellekt"]
    assert data["info"]["certificates"] == ["PMP"]
    assert set(codes) >= {WELCOME_UNSURFACED, EXAM_QUESTIONS_UNSURFACED, TEACHER_PROFILE_UNSURFACED}


def test_the_header_facts_that_have_no_own_section_ride_along_in_info():
    data, _codes = build_section_data(_document(header=_header(language="en", lesson_hours=60)))

    assert data["info"]["language"] == "en"
    assert data["info"]["lesson_hours"] == 60
    # Müəllim adı və qəbul saatı mənbədə YOXDUR — uydurulmur, boş qalır.
    assert data["info"]["teacher"] == "" and data["info"]["office_hours"] == ""


def test_week_rows_keep_source_order_blank_topics_and_the_note_column():
    data, _codes = build_section_data(
        _document(
            week=[
                _week(3, topic="İkinci həftə", hours=(("lecture", 2), ("seminar", 1))),
                _week(7, topic="", hours=()),
                _week(9, topic="Dördüncü həftə", note="Müəllim qeydi", hours=(("lab", 2),)),
            ]
        )
    )

    rows = data["week"]["rows"]
    # Sıra mənbə PK-sınındır və BOŞ mövzu ATILMIR: atmaq qalan mövzuları bir
    # həftə yuxarı sürüşdürərdi.
    assert [row["topic"] for row in rows] == ["İkinci həftə", "", "Dördüncü həftə"]
    assert rows[0]["lecture"] == 2 and rows[0]["seminar"] == 1 and rows[0]["lab"] == 0
    assert rows[2]["note"] == "Müəllim qeydi"
    # Mövzu ↔ təlim nəticəsi bağı mənbədə yoxdur → uydurulmur.
    assert {row["outcome"] for row in rows} == {""}


def test_practical_hours_survive_in_an_extra_key_and_are_counted():
    """Hədəfin saat növləri üçdür, mənbədə isə ``praktiki_saat`` da doludur."""

    data, codes = build_section_data(_document(week=[_week(1, hours=(("lecture", 1), ("practical", 2)))]))

    assert data["week"]["rows"][0]["practical"] == 2
    assert PRACTICAL_UNSURFACED in codes


def test_a_week_plan_longer_than_the_target_table_is_kept_and_flagged():
    data, codes = build_section_data(_document(week=[_week(index) for index in range(1, TARGET_WEEK_ROWS + 8)]))

    assert len(data["week"]["rows"]) == TARGET_WEEK_ROWS + 7  # KƏSİLMİR
    assert WEEK_ROWS_EXCEED_PLAN in codes


def test_hour_cell_issues_are_carried_up_from_the_source_row():
    _data, codes = build_section_data(_document(week=[_week(1, hours=(), issues=(HOUR_CELL_FRACTIONAL,))]))

    assert HOUR_CELL_FRACTIONAL in codes


def test_blank_and_truncated_satellite_rows_are_counted():
    _data, codes = build_section_data(
        _document(
            sections={
                LITERATURE_TABLE: [_section(1, ""), _section(2, "Dərslik", truncated=True)],
            }
        )
    )

    assert BLANK_ROW_DROPPED in codes and TEXT_TRUNCATED in codes


def test_a_document_without_a_single_section_row_is_flagged():
    _data, codes = build_section_data(_document())

    assert SECTIONS_EMPTY in codes


def test_codes_are_deduplicated_and_order_stable():
    _data, codes = build_section_data(
        _document(
            week=[_week(1, hours=(), issues=(HOUR_CELL_INVALID,)), _week(2, hours=(), issues=(HOUR_CELL_INVALID,))]
        )
    )

    assert codes.count(HOUR_CELL_INVALID) == 1


# ── Sətir sonu MƏZMUNDUR: köhnə siyahı tələbəyə N sətir kimi çıxmalıdır ──────

#: Canlı ``sillabus_derslikler.name`` forması (id=2407 nümunəsi): bütöv
#: nömrələnmiş ədəbiyyat siyahısı BİR sütunda, ``1.`` + TAB, aralarında CRLF.
#: Canlı ölçmə (2026-08-30): 11 peykin 23,574 sətrində sətir sonu var
#: (``_yoxlama_formasi`` 4,842 · ``_eldeolunacaq_tecrubeler`` 4,791 ·
#: ``_tesviri_ve_meqsedi`` 4,652 · ``_dersin_islenme_formasi`` 4,574 ·
#: ``_derslikler`` 2,508 · ``_qarsilama_mesaji`` 1,724 · ``_elmi_maraq`` 483).
_LEGACY_LITERATURE_COLUMN = (
    "1.\tSpeak Out, Pre-Intermediate, Students&rsquo; Book\r\n"
    "2.\tBasic English Grammar, 4th Edition\r\n"
    "3.\tİngilis dili &uuml;zr&#601; praktikum"
)


def test_a_multiline_literature_column_reaches_the_student_as_separate_lines():
    """Uçdan-uca: mənbə xanası → bölmə datası → tələbənin gördüyü sənəd.

    ``apps.syllabus.document._lines`` mətni "\\n" üzrə bölür.  Mənbə sətrini
    yastılamaq ``truncated=False`` və issue-suz, yəni TAM SƏSSİZ struktur
    itkisidir: tələbə üç ədəbiyyat sətri əvəzinə BİR abzas görərdi.  Bu test
    məhz həmin fərqi kilidləyir.
    """
    from apps.legacy_import.services.rehearsal_syllabus_source import distilled_section_row
    from apps.syllabus.constants import SectionKey
    from apps.syllabus.document import build_preview_blocks

    row = distilled_section_row(1, _LEGACY_LITERATURE_COLUMN)
    assert row.truncated is False
    assert len(row.text.split("\n")) == 3

    data, codes = build_section_data(_document(sections={LITERATURE_TABLE: [row]}))
    assert data[SectionKey.LIT.value]["primary"] == [row.text]
    assert TEXT_TRUNCATED not in codes

    literature_block = build_preview_blocks(data)[-1]
    assert literature_block["body"].split("\n") == [
        "1. Speak Out, Pre-Intermediate, Students’ Book",
        "2. Basic English Grammar, 4th Edition",
        "3. İngilis dili üzrə praktikum",
    ]


def test_a_blank_only_section_row_is_still_dropped_after_the_line_split():
    """Yalnız sətir sonundan ibarət xana BOŞ sayılır — kod dəyişmir."""
    from apps.legacy_import.services.rehearsal_syllabus_source import distilled_section_row

    row = distilled_section_row(1, "\r\n\r\n   \r\n")

    assert row.text == ""
    _data, codes = build_section_data(_document(sections={LITERATURE_TABLE: [row]}))
    assert BLANK_ROW_DROPPED in codes


# ── Qiymətləndirmə: mənbənin QAYDA MƏTNİ tələbəyə çatmalıdır ─────────────────

#: Canlı ``sillabus_yoxlama_formasi`` xanası (``uniqid=xT3TV90663lSdMvRT6LL``,
#: id=26) — entity daşıyır, çoxsətirlidir və NK-nın 348 nömrəli qərarına
#: istinad edir.  Canlı ölçmə (2026-08-30): cədvəldə 8,261 sətir, 4,842-si
#: çoxsətirli, yəni bu forma demək olar HƏR sillabusda var.
_LEGACY_ASSESSMENT_COLUMN = (
    "1.\tİmtahandan əvvəl məsləhət saatları təşkil olunur.\r\n"
    "2.\tİmtahanlar və aralıq yoxlamalar (kollekviumlar) yazılı formada aparılır.\r\n"
    "3.\tTələbələrin imtahana buraxılması fak&uuml;ltə dekanı tərəfindən həll edilir. "
    "İmtahanlar Nazirlər Kabinetinin 348 n&ouml;mrəli qərarı ilə təsdiq edilmiş "
    "&ldquo;kredit sistemi ilə təlimin təşkili Qaydaları&rdquo;na əsasən aparılır."
)


def test_the_assessment_rule_text_reaches_the_student_instead_of_a_default_split():
    """Uçdan-uca: mənbə xanası → ``assess.note`` → tələbənin gördüyü blok.

    Bu, J12-nin ƏN BAHALI səssiz itkisi idi: sənəd qurucusu ``note``-u heç
    oxumur, gövdəni isə tətbiqin DEFOLT rəqəmlərindən qururdu — nəticədə
    köçürülən 8,248 sillabusun hamısında tələbə mənbədə OLMAYAN
    «10 + 10 + 0 + 30 + 50 = 100 bal» sətrini görür, mənbədəki əsl qayda mətni
    isə heç yerdə çıxmırdı.
    """
    from apps.legacy_import.services.rehearsal_syllabus_source import distilled_section_row
    from apps.syllabus.constants import SectionKey
    from apps.syllabus.document import build_preview_blocks

    row = distilled_section_row(26, _LEGACY_ASSESSMENT_COLUMN)
    data, codes = build_section_data(
        _document(
            sections={
                ASSESSMENT_TABLE: [row],
                EXAM_QUESTION_TABLE: [distilled_section_row(1, "İmtahan sualı: alqoritmin m&uuml;rəkkəbliyi")],
            }
        )
    )

    assert data[SectionKey.ASSESS.value]["note"] == row.text
    assert ASSESSMENT_NOTE_UNSURFACED in codes  # redaktorda input yoxdur → sayılır

    body = build_preview_blocks(data)[5]["body"]
    # 1) uydurma bölgü YOXDUR;
    assert "10 + 10 + 0 + 30 + 50" not in body
    # 2) mənbənin ÜÇ sətri olduğu kimi durur (entity açılmış, tərs dırnaq real);
    for fragment in ("348 nömrəli qərarı", "fakültə dekanı", "“kredit sistemi"):
        assert fragment in body
    assert body.count("\n") >= 3
    # 3) imtahan sualı da göstərilir (mənbədə 20,835 sətir).
    assert "İmtahan sualı: alqoritmin mürəkkəbliyi" in body


def test_a_migrated_syllabus_shows_no_score_for_selfwork_topics():
    """Mənbədə sərbəst iş VARİANTI yoxdur → «(0 bal)» yazmaq yanlış məlumatdır."""
    from apps.syllabus.document import build_preview_blocks

    data, _codes = build_section_data(
        _document(sections={SELF_WORK_TABLE: [_section(1, "Birinci mövzu"), _section(2, "İkinci mövzu")]})
    )

    assert data["self"]["option"] == ""
    assert build_preview_blocks(data)[6]["body"].split("\n") == ["1. Birinci mövzu", "2. İkinci mövzu"]


def test_the_assessment_note_counter_stays_silent_without_a_source_row():
    _data, codes = build_section_data(_document(sections={LITERATURE_TABLE: [_section(1, "Dərslik")]}))

    assert ASSESSMENT_NOTE_UNSURFACED not in codes
