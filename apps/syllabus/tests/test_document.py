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

import logging
import re

from apps.syllabus.constants import SectionKey
from apps.syllabus.document import (
    _EMPTY,
    _POINTS,
    _WEIGHTS_UNSPECIFIED,
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
UNSPECIFIED = str(_WEIGHTS_UNSPECIFIED)


def _blocks(section_map):
    return {str(block["title"]): block["body"] for block in build_preview_blocks(section_map)}


def _assessment(section_map):
    return build_preview_blocks(section_map)[5]["body"]


def _migrated_map(**assess):
    """Köçürmə borusunun yazdığı forma: bölgü 0/0, mətn ``note``-da."""
    data = {key: blank_section_data(key) for key in (choice.value for choice in SectionKey)}
    data[SectionKey.ASSESS.value] = {"midterm": 0, "project": 0, "note": "", "exam_questions": [], **assess}
    return data


# ── 1. Köçürülmüş sillabus: mənbə mətni görünür, uydurma bölgü YOX ───────────


def test_the_migrated_rule_text_reaches_the_reader_instead_of_a_default_split():
    body = _assessment(_migrated_map(note=LEGACY_RULE_TEXT))

    assert SPLIT_RE.search(body) is None
    assert "348" in body
    # Mənbə mətni blokun BAŞINDADIR — üstünə heç nə əlavə edilmir.
    assert body.split("\n") == LEGACY_RULE_TEXT.split("\n")


def test_the_unspecified_label_never_contradicts_the_text_under_it():
    """Canlı ölçmə (8,260 uniqid): etiket 5,942 blokda çıxırdı, 4,071-i (68.5 %)
    bölgünü elə öz mətnində AÇIQ deyirdi — tələbə əvvəlcə «göstərilməyib»,
    sonra bölgünün özünü oxuyurdu.  Etiket indi yalnız blok BOŞ olanda çıxır.
    """
    note = "məşğələ (0-30 bal), sərbəst iş (0-10 bal), davamiyyət (0-10 bal), imtahan (0-50 bal)"

    body = _assessment(_migrated_map(note=note))

    assert body == note
    assert UNSPECIFIED not in body


def test_an_unfilled_split_is_named_honestly_when_the_block_is_otherwise_empty():
    body = _assessment(_migrated_map())

    assert body == UNSPECIFIED  # boşluq susmur — açıq deyilir
    assert "=" not in body and "+" not in body  # cəm sətri YOXDUR


def test_exam_questions_are_shown_too():
    """Mənbədə 20,835 sual sətri var; əvvəllər heç biri oxunmurdu."""
    body = _assessment(_migrated_map(note=LEGACY_RULE_TEXT, exam_questions=["1. Alqoritm nədir?", "2. Yığın və növbə"]))

    assert "1. Alqoritm nədir?" in body
    assert "2. Yığın və növbə" in body


def test_questions_alone_are_enough_to_fill_the_block():
    body = _assessment(_migrated_map(exam_questions=["Sual 1"]))

    assert "Sual 1" in body
    assert SPLIT_RE.search(body) is None


def test_an_empty_assessment_section_names_the_missing_split_not_a_generic_blank():
    """Blokun struktur məzmunu MƏHZ bölgüdür, ona görə ümumi «— doldurulmayıb —»
    əvəzinə dəqiq etiket çıxır.  Digər bloklar ümumi işarəni saxlayır."""
    section_map = _migrated_map()

    assert _assessment(section_map) == UNSPECIFIED
    assert _blocks(section_map)[str(BLOCK_TITLES["description"])] == EMPTY


# ── 2. Canlı redaktə axını: müəllimin doldurduğu bölgü GÖSTƏRİLİR ────────────


def test_a_teacher_filled_split_is_still_printed_in_full():
    body = _assessment(complete_section_data())  # midterm 20 / project 10

    assert body == f"10 + 10 + 20 + 10 + 50 = 100 {POINTS}"


def test_a_zero_midterm_saved_by_the_teacher_is_not_mistaken_for_an_empty_split():
    """Sürüşdürücü 0-da qalanda avtosave ``project``-i 30 yazır — bu, REAL bölgüdür."""
    body = _assessment(_migrated_map(midterm=0, project=30))

    assert body == f"10 + 10 + 0 + 30 + 50 = 100 {POINTS}"


def test_an_impossible_total_is_refused_and_warned_about(caplog):
    """Cəm HESABLANIR (köhnə kod dəyərdən asılı olmayaraq «= 100» yazırdı), amma
    siyasətlə MÜMKÜN OLMAYAN cəm tələbəyə qayda kimi verilmir.

    ``save_section`` sərbəst JSON qəbul edir, yəni 20/20 cütlüyü saxlanıla
    bilər — onun cəmi 110-dur, belə qayda universitetdə yoxdur.  Əvvəl bu sətir
    olduğu kimi çıxırdı və heç bir xəbərdarlıq qalxmırdı.
    """
    with caplog.at_level(logging.WARNING, logger="apps.syllabus.document"):
        body = _assessment(_migrated_map(midterm=20, project=20, note=LEGACY_RULE_TEXT))

    assert SPLIT_RE.search(body) is None
    assert "348" in body  # müəllimin ÖZ mətni susdurulmur
    assert "assessment_weights_off_policy" in caplog.text
    assert "total=110" in caplog.text


def test_a_half_filled_pair_is_not_completed_from_the_policy(caplog):
    """``project`` açarı YOXDURSA ikinci yarı siyasətdən ÇIXARILMIR.

    Köhnə budaq ``project = 30 − midterm`` yazırdı: heç kimin saxlamadığı rəqəm
    tələbəyə real qayda kimi çıxırdı — məhz ləğv etdiyimiz sinifdən.  İndi
    yarımçıq cütlük cəmi 100 vermir, ona görə fail-closed süzülür.
    """
    section_map = _migrated_map(midterm=20, note=LEGACY_RULE_TEXT)
    del section_map[SectionKey.ASSESS.value]["project"]  # açar HEÇ YAZILMAYIB

    with caplog.at_level(logging.WARNING, logger="apps.syllabus.document"):
        body = _assessment(section_map)

    assert SPLIT_RE.search(body) is None
    assert "assessment_weights_off_policy" in caplog.text


# ── 2b. Abzas boşluğu OXUCUYA ÇATIR ──────────────────────────────────────────


def test_a_paragraph_break_inside_the_rule_text_survives_the_reader():
    """``legacy_text.clean_multiline_text`` abzas boşluğunu QƏSDƏN saxlayır
    (canlı: 588 sətir); oxucu əvvəl onların 588-ni də atırdı."""
    note = "Birinci abzas.\n\nİkinci abzas."

    body = _assessment(_migrated_map(note=note))

    assert body.split("\n") == ["Birinci abzas.", "", "İkinci abzas."]


def test_the_numbered_outcome_list_still_drops_blank_lines():
    """⚠️ ``outcomes`` NÖMRƏLƏNİR — orada boş sətir «TN2. » yaradardı."""
    data = _migrated_map()
    data[SectionKey.OUT.value] = {"outcomes": ["Birinci nəticə", "", "İkinci nəticə"]}

    body = _blocks(data)[str(BLOCK_TITLES["outcomes"])]

    assert body.split("\n") == ["TN1. Birinci nəticə", "TN2. İkinci nəticə"]


def test_a_teacher_split_and_the_rule_text_live_together():
    body = _assessment(_migrated_map(midterm=20, project=10, note=LEGACY_RULE_TEXT))

    assert body.split("\n")[0] == f"10 + 10 + 20 + 10 + 50 = 100 {POINTS}"
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
