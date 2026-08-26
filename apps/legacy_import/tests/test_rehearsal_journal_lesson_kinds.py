"""J3 dərs NÖVÜ törəməsinin testləri (``rehearsal_journal_lesson_kinds``).

Semantika canlı mənbədə ölçülüb (modulun docstring-inə bax); burada həmin
qərar nərdivanının SABİTLİYİ qorunur: ``sem_muh=1`` mühazirədir (bal xanası
BAĞLI), qalan tanınan kodlar ballana bilən növdür, ``lab`` isə müstəqil
laboratoriya bayrağıdır.
"""

import pytest

from apps.legacy_import.services.rehearsal_journal_lesson_kinds import (
    ABSENT_RULE_CODE,
    CONFLICT_RULE_CODE,
    LAB,
    LECTURE,
    SEMINAR,
    LessonKindIndex,
    cell_kind,
    slot_key,
)

_SLOT = slot_key(uniqid="rooBx39tsK", month=12, day=30, time_text="14:00")
_OTHER = slot_key(uniqid="rooBx39tsK", month=12, day=30, time_text="15:00")


@pytest.mark.parametrize(
    "lab, sem_muh, expected",
    [
        # ``sem_muh=1`` = mühazirə: canlı mənbədə slotların yalnız 0.1 %-i ballanır.
        (0, 1, LECTURE),
        # 0 = seminar (41.2 % ballanır), 2/3 = praktiki/məşğələ (70.7 % / 26.6 %)
        # — hədəf enumunda hər üçü bal xanası AÇIQ olan SEMINAR-a düşür.
        (0, 0, SEMINAR),
        (0, 2, SEMINAR),
        (0, 3, SEMINAR),
        # ``lab`` MÜSTƏQİL bayraqdır və ``sem_muh``-dan asılı olmayaraq udur.
        (1, 0, LAB),
        (1, 1, LAB),
        (1, 2, LAB),
        (1, 3, LAB),
        # Naməlum kod → boş: çağıran defolt ``lecture``-a düşür (təxmin yoxdur).
        (0, 4, ""),
        (0, 9, ""),
        (0, -1, ""),
        (2, 0, ""),
    ],
)
def test_the_cell_kind_ladder_follows_the_measured_semantics(lab, sem_muh, expected):
    assert cell_kind(lab=lab, sem_muh=sem_muh) == expected


def test_an_unseen_slot_defaults_to_lecture_with_an_info_code():
    index = LessonKindIndex()

    assert index.resolve(_SLOT) == (LECTURE, ABSENT_RULE_CODE)
    assert len(index) == 0


def test_a_slot_of_unknown_cells_only_stays_the_lecture_default():
    index = LessonKindIndex()
    for _ in range(3):
        index.observe(_SLOT, cell_kind(lab=0, sem_muh=7))

    # Naməlum xana heç vaxt sayılmır → slot "yoxdur" kimi qalır.
    assert index.resolve(_SLOT) == (LECTURE, ABSENT_RULE_CODE)


def test_a_homogeneous_slot_resolves_without_an_issue():
    index = LessonKindIndex()
    for _ in range(4):
        index.observe(_SLOT, SEMINAR)

    assert index.resolve(_SLOT) == (SEMINAR, "")


def test_the_majority_wins_and_a_mixed_slot_is_flagged():
    index = LessonKindIndex()
    for _ in range(5):
        index.observe(_SLOT, SEMINAR)
    index.observe(_SLOT, LECTURE)

    # Canlı mənbədə qarışıq slot nadirdir (355k-dan 313-ü), amma qərar
    # deterministikdir: əksəriyyət udur, sətir INFO ilə işarələnir.
    assert index.resolve(_SLOT) == (SEMINAR, CONFLICT_RULE_CODE)


def test_a_tie_is_broken_by_the_documented_precedence_not_by_source_order():
    forward = LessonKindIndex()
    forward.observe(_SLOT, LECTURE)
    forward.observe(_SLOT, SEMINAR)

    backward = LessonKindIndex()
    backward.observe(_SLOT, SEMINAR)
    backward.observe(_SLOT, LECTURE)

    # Bərabərlikdə bal xanasını AÇIQ saxlayan növ udur — yazılmış bal
    # görünməz qalmasın; nəticə mənbə sırasından ASILI DEYİL.
    assert forward.resolve(_SLOT) == backward.resolve(_SLOT) == (SEMINAR, CONFLICT_RULE_CODE)

    lab_tie = LessonKindIndex()
    lab_tie.observe(_SLOT, SEMINAR)
    lab_tie.observe(_SLOT, LAB)
    assert lab_tie.resolve(_SLOT) == (LAB, CONFLICT_RULE_CODE)


def test_slots_never_bleed_into_each_other():
    index = LessonKindIndex()
    index.observe(_SLOT, SEMINAR)
    index.observe(_OTHER, LECTURE)

    assert index.resolve(_SLOT) == (SEMINAR, "")
    assert index.resolve(_OTHER) == (LECTURE, "")
    assert len(index) == 2
    assert index.keys() == frozenset({_SLOT, _OTHER})


def test_the_packed_counters_survive_a_large_slot():
    """Sayğac sahəsi 21 bitdir — ən böyük jurnal onu daşdıra bilməz."""

    index = LessonKindIndex()
    for _ in range(5_000):
        index.observe(_SLOT, SEMINAR)
    for _ in range(4_999):
        index.observe(_SLOT, LECTURE)

    assert index.resolve(_SLOT) == (SEMINAR, CONFLICT_RULE_CODE)


def test_the_slot_key_normalizes_the_calendar_parts():
    """Mənbədə gün/ay sıfır-doldurulmuş MƏTNdir, dərs cədvəlində ``int``."""

    assert slot_key(uniqid="a", month=4, day=3, time_text="08:30") == ("a", 4, 3, "08:30")
    assert slot_key(uniqid="a", month=4, day=3, time_text="08:30") != ("a", "04", "03", "08:30")
