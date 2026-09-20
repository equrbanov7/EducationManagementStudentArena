"""Oxu-rejimli sənədin QURAŞDIRMAMA qaydası (``apps.syllabus.document``).

Sənəd tələbəyə göstərilir, ona görə blok gövdəsindəki hər sətir onun üçün REAL
faktdır.  Bu dəst məhz bunu kilidləyir: tətbiqin defolt dəyərindən qurulmuş
«sanki data» sətri tələbəyə ÇIXMAMALIDIR, müəllimin doldurduğu real dəyər isə
həmişə çıxmalıdır.

Kilidlənən presedent (düşmən baxışı, 2026-08-30): qiymətləndirmə bloku
``note``/``exam_questions`` sahələrini heç oxumur, gövdəni isə
``10 + 10 + {midterm} + {project} + 50 = 100 bal`` kimi QURURDU.  Köçürülmüş
8,248 sillabusda ``midterm`` 0 olduğuna görə tələbə mənbədə OLMAYAN
«10 + 10 + 0 + 30 + 50 = 100 bal» bölgüsünü görürdü.
"""

from __future__ import annotations

import re

from apps.syllabus.assessment_formula import formula_text
from apps.syllabus.constants import SectionKey
from apps.syllabus.document import (
    _EMPTY,
    _POINTS,
    BLOCK_TITLES,
    build_preview_blocks,
)
from apps.syllabus.services.drafts import blank_section_data
from apps.syllabus.tests.factories import complete_section_data

#: Köçürülmüş sillabusun qiymətləndirmə mətni (canlı nümunənin qısaldılmış
#: forması — ``sillabus_yoxlama_formasi`` sətri, NK-nın 348 nömrəli qərarına
#: istinad edir).
LEGACY_RULE_TEXT = (
    "Tələbənin biliyi 100 ballıq sistemlə qiymətləndirilir.\n"
    "Nazirlər Kabinetinin 348 nömrəli qərarına əsasən semestr ərzində "
    "toplanan bal 50-dən az olduqda tələbə imtahana buraxılmır."
)

#: QURULMUŞ bal bölgüsünün NAXIŞI — konkret sətir yox, forma.
#: ⚠️ Mutasiya sınağı (2026-08-31): qurucudan qorumanı çıxaranda blok
#: «10 + 10 + 0 + 0 + 50 = 70 bal» verdi və konkret sətrə baxan köhnə damğa
#: (``"10 + 10 + 0 + 30 + 50"``) bunu BURAXDI.  Naxış beş toplananı və cəmi
#: tanıyır, yəni hər hansı yeni uydurma cütlük də tutulur.
SPLIT_RE = re.compile(r"\d+ \+ \d+ \+ \d+ \+ \d+ \+ \d+ = ")

# ⚠️ Gözlənilən mətnlər modulun ÖZ sabitlərindən qurulur: dəst aktiv dildən
# asılı olmamalıdır (bax 7cdc3376 — «icazə etiketi testi aktiv dildən asılı
# olmasın»).  Yoxlanan şey mətnin tərcüməsi deyil, blokun DAVRANIŞIDIR.
POINTS = str(_POINTS)
EMPTY = str(_EMPTY)
#: Sahib 2026-09-20: bal bölgüsü universitet STANDARTIDIR və HƏMİŞƏ çap olunur
#: (uydurma deyil — siyasətin özü). Defolt fəaliyyət: seminar.
FORMULA = formula_text(("seminar",))


def _blocks(section_map):
    return {str(block["title"]): block["body"] for block in build_preview_blocks(section_map)}


def _assessment(section_map):
    return build_preview_blocks(section_map)[5]["body"]


def _migrated_map(**assess):
    """Köçürmə borusunun yazdığı forma: bölgü 0/0, mətn ``note``-da."""
    data = {key: blank_section_data(key) for key in (choice.value for choice in SectionKey)}
    data[SectionKey.ASSESS.value] = {"midterm": 0, "project": 0, "note": "", "exam_questions": [], **assess}
    return data


# ── 1. Standart düstur HƏMİŞƏ çap olunur, mənbə mətni onun ardınca ────────────


def _lines_after_formula(body):
    lines = body.split("\n")
    assert lines[0] == FORMULA
    # 2-ci sətir fəaliyyət izahıdır (seminar/lab ədədi ortası qaydası).
    return lines[2:]


def test_the_migrated_rule_text_reaches_the_reader_after_the_standard_formula():
    body = _assessment(_migrated_map(note=LEGACY_RULE_TEXT))

    assert "348" in body
    assert _lines_after_formula(body) == LEGACY_RULE_TEXT.split("\n")


def test_the_stored_split_never_changes_the_printed_formula():
    """Köhnə 0/0, 15/15, 20/20 — hamısı eyni STANDART düsturu verir (uydurma cəm yox)."""
    for pair in ({}, {"midterm": 15, "project": 15}, {"midterm": 20, "project": 20}, {"midterm": 0, "project": 30}):
        body = _assessment(_migrated_map(**pair))
        assert body.split("\n")[0] == FORMULA
        assert "= 110" not in body and "= 70" not in body


def test_exam_questions_are_shown_too():
    """Mənbədə 20,835 sual sətri var; əvvəllər heç biri oxunmurdu."""
    body = _assessment(_migrated_map(note=LEGACY_RULE_TEXT, exam_questions=["1. Alqoritm nədir?", "2. Yığın və növbə"]))

    assert "1. Alqoritm nədir?" in body
    assert "2. Yığın və növbə" in body


def test_an_empty_assessment_section_still_prints_the_standard_formula():
    section_map = _migrated_map()

    assert _assessment(section_map).split("\n")[0] == FORMULA
    assert _blocks(section_map)[str(BLOCK_TITLES["description"])] == EMPTY


def test_the_formula_names_every_component_and_the_hundred():
    assert "10" in FORMULA and "20" in FORMULA and "50" in FORMULA
    assert f"= 100 {POINTS}" in FORMULA


# ── 2b. Abzas boşluğu OXUCUYA ÇATIR ──────────────────────────────────────────


def test_a_paragraph_break_inside_the_rule_text_survives_the_reader():
    """``legacy_text.clean_multiline_text`` abzas boşluğunu QƏSDƏN saxlayır
    (canlı: 588 sətir); oxucu əvvəl onların 588-ni də atırdı."""
    note = "Birinci abzas.\n\nİkinci abzas."

    body = _assessment(_migrated_map(note=note))

    assert _lines_after_formula(body) == ["Birinci abzas.", "", "İkinci abzas."]


def test_the_numbered_outcome_list_still_drops_blank_lines():
    """⚠️ ``outcomes`` NÖMRƏLƏNİR — orada boş sətir «TN2. » yaradardı."""
    data = _migrated_map()
    data[SectionKey.OUT.value] = {"outcomes": ["Birinci nəticə", "", "İkinci nəticə"]}

    body = _blocks(data)[str(BLOCK_TITLES["outcomes"])]

    assert body.split("\n") == ["TN1. Birinci nəticə", "TN2. İkinci nəticə"]


def test_a_teacher_split_and_the_rule_text_live_together():
    body = _assessment(_migrated_map(midterm=20, project=10, note=LEGACY_RULE_TEXT))

    assert body.split("\n")[0] == FORMULA
    assert "348" in body


# ── 3. Sərbəst iş: bal MƏLUM DEYİLSƏ yazılmır ────────────────────────────────


def test_selfwork_topics_without_a_known_option_carry_no_score():
    data = _migrated_map()
    data[SectionKey.SELF.value] = {
        "option": "",  # mənbədə variant YOXDUR
        "topics": [{"title": "Birinci mövzu"}, {"title": "İkinci mövzu"}],
        "archived": [],
    }

    body = build_preview_blocks(data)[6]["body"]

    assert body.split("\n") == ["1. Birinci mövzu", "2. İkinci mövzu"]
    assert POINTS not in body  # bal MƏLUM DEYİL → heç bir bal yazılmır


def test_selfwork_score_is_printed_when_the_option_is_known():
    body = build_preview_blocks(complete_section_data())[6]["body"]  # 2x5

    assert body.split("\n") == [
        f"1. Birinci sərbəst iş mövzusu (5 {POINTS})",
        f"2. İkinci sərbəst iş mövzusu (5 {POINTS})",
    ]


# ── 4. Blok siyahısının forması dəyişmir ─────────────────────────────────────


def test_the_document_still_has_the_same_eight_blocks_in_the_same_order():
    titles = list(_blocks(complete_section_data()))

    assert len(titles) == 8
    assert titles[5] == str(BLOCK_TITLES["assessment"])
    assert titles[6] == str(BLOCK_TITLES["selfwork"])
    assert titles[7] == str(BLOCK_TITLES["literature"])
