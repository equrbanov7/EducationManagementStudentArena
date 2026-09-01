"""Nərdivanın son iki pilləsinin testləri — ``scripts/legacy_reconcile/write_replay``.

Bu testlər BAZAYA TOXUNMUR: ``replay_writes`` saf funksiyadır, sətir axını və
xəritələri arqument kimi alır.  Ona görə həm CI-də (sqlite loop), həm də
repetisiya işləyərkən təhlükəsizdir.

Yoxlanılan invariantlar:
  * qapı sırası ``rehearsal_journal_marks_phase._decide`` ilə eynidir;
  * dərs slotu tapılmayan xana ``lesson_missing``-dir, ``written`` DEYİL;
  * hədəf açarı toqquşması sətir yaratmır — və EYNİ dəyər/FƏRQLİ dəyər ayrılır
    (ledger hər ikisini «yazıldı» sayır, ona görə nərdivan onu özü hesablamalıdır);
  * toqquşma həm birləşmiş yazılışda, həm də eyni legacy açarın normallaşan
    J-V4 açarlarında tutulur (yaddaş optimizasiyasının doğruluq şərti);
  * canlı seçkidən sonra gələn arxiv hədəfi konflikt yox, superseded sayılır;
  * nərdivan bu pillələrlə sıfıra bağlanır.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:  # skript Django kontekstindən kənarda da işləyir
    sys.path.insert(0, str(ROOT))

from apps.legacy_import.services.rehearsal_journal_points_source import CellElection  # noqa: E402
from scripts.legacy_reconcile.analysis import Ladder  # noqa: E402
from scripts.legacy_reconcile.collect import (  # noqa: E402
    build_ladders,
    importer_ordered_winners,
    offering_journal_keys,
)
from scripts.legacy_reconcile.grade_replay_facts import replay_grade_fact_rows  # noqa: E402
from scripts.legacy_reconcile.render_steps import recovery_block  # noqa: E402
from scripts.legacy_reconcile.source_sql import (  # noqa: E402
    cell_election_keys_sql,
    deduped_cell_keys_sql,
    lesson_slot_source_sql,
)
from scripts.legacy_reconcile.target_sql import (  # noqa: E402
    ENROLLMENT_OFFERING_SQL,
    LESSON_SLOT_SQL,
    LESSON_SYNTH_COLUMN_SQL,
    LESSON_SYNTH_COUNT_SQL,
    LESSON_SYNTH_MARK_SQL,
)
from scripts.legacy_reconcile.transport import assert_read_only  # noqa: E402
from scripts.legacy_reconcile.write_replay import (  # noqa: E402
    LABEL_COLLISION_OTHER,
    LABEL_COLLISION_SAME,
    LABEL_LESSON_SOURCE_ABSENT,
    LABEL_LESSON_SOURCE_PRESENT,
    SHAPE_ABSENT,
    SHAPE_PRESENT,
    SHAPE_SCORE,
    STEP_ARCHIVE_SUPERSEDED,
    STEP_COLLISION,
    STEP_COLLISION_OTHER,
    STEP_COLLISION_SAME,
    STEP_DEDUPED,
    STEP_LESSON_MISSING,
    STEP_LESSON_SOURCE_ABSENT,
    STEP_LESSON_SOURCE_PRESENT,
    STEP_ORPHAN,
    STEP_SYNTH_TIME_UNKNOWN,
    STEP_UNRESOLVED,
    STEP_WRITTEN,
    SUBSTEP_DAY_ABSENT,
    SUBSTEP_DAY_PRESENT_TIME_DIFFERS,
    SUBSTEP_IMPOSSIBLE_DATE,
    SUBSTEP_LEAP_DEPENDENT_DATE,
    SUBSTEP_SLOT_NOT_MATERIALISED,
    SUBSTEP_UNREADABLE_TIME,
    identity_residuals,
    is_readable_time,
    multi_key_enrollment_targets,
    replay_writes,
    rung_overlaps,
    source_slot_reason,
    value_shape,
)

# ── Kiçik, əl ilə qurulmuş dünya ─────────────────────────────────────────────
#
# İki legacy jurnal (``J1``, ``J2``) BİR açılışa (``off-1``) birləşir — yəni
# ``J1:7`` və ``J2:7`` eyni yazılışa (``enr-1``) gedir.  ``J3`` ayrıca açılışdır,
# ``J9`` isə heç bir açılışa çevrilməyib (orphan).

OFFERINGS = {"J1": "off-1", "J2": "off-1", "J3": "off-2"}
ENROLLMENTS = {"J1:7": "enr-1", "J2:7": "enr-1", "J3:7": "enr-2", "J3:8": "enr-3"}
ENROLLMENT_OFFERINGS = {"enr-1": "off-1", "enr-2": "off-2", "enr-3": "off-2"}
LESSON_SLOTS = {("off-1", 3, 9, "11:30"), ("off-2", 3, 9, "11:30")}

# MƏNBƏNİN öz dərs indeksi: ``J3``-ün 10-cu günü mənbədə VAR (amma hədəfdə
# materiallaşmayıb), 11-ci gün isə mənbədə də yoxdur.  ``J3``-ün 12-ci günü
# mənbədə var, saatı isə fərqlidir — «gün var, saat yox» alt-halı.
SOURCE_LESSON_SLOTS = {
    ("J1", 3, 9, "11:30"),
    ("J2", 3, 9, "11:30"),
    ("J3", 3, 9, "11:30"),
    ("J3", 3, 10, "11:30"),
    ("J3", 3, 12, "08:30"),
}


def _replay(rows, source_slots=None):
    return replay_writes(
        rows,
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS,
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS if source_slots is None else source_slots,
    )


def _mark(uniqid, student, day, point, time_text="11:30", month="03"):
    return (uniqid, student, "marks", month, day, time_text, point)


def _source_row(row, pk, *, archive=False, local_repeat=False):
    table = "journals_dates_points_archive" if archive else "journals_dates_points"
    return (*row, table, pk, int(archive), int(local_repeat))


def test_importer_order_includes_cell_election_bucket_false_positives():
    """Exact-dublikat olmayan hash-bucket namizədi də cədvəlin sonuna keçir."""

    election = CellElection(expected_rows=1)
    first = _mark("J1", "7", "9", "5")
    first_key = ("J1", "03", "9", 7, "11:30")
    collision = None
    for number in range(1, 10_000):
        candidate = (f"X{number}", "03", "9", 7, "11:30")
        if election.bucket(candidate) == election.bucket(first_key):
            collision = candidate
            break
    assert collision is not None
    election.observe(first_key)
    election.observe(collision)

    second = _mark("J1", "8", "9", "6")
    second_key = ("J1", "03", "9", 8, "11:30")
    election.observe(second_key)
    elections = {
        ("journals_dates_points", "marks"): election,
    }
    ordered = list(
        importer_ordered_winners(
            [_source_row(first, 1), _source_row(second, 2)],
            elections,
        )
    )
    assert [row[8] for row in ordered] == [2, 1]


def test_election_key_query_is_read_only_and_keeps_unwritable_rows_before_distill():
    sql = cell_election_keys_sql()
    assert_read_only(sql)
    assert "domain <> 'unknown_code'" in sql
    assert "COALESCE(point" not in sql
    assert "BETWEEN 1 AND 31" not in sql
    assert "ORDER BY source_order, pk" in sql


def test_offering_keys_preserve_colons_inside_the_opaque_journal_id():
    assert "journal:part" in offering_journal_keys({"journal:part:77"})


# ── Qapı sırası ──────────────────────────────────────────────────────────────


def test_cell_without_offering_is_orphan_not_lesson_missing():
    """Orphan qapısı BİRİNCİDİR — açılışsız jurnal dərs qapısına çatmır."""

    result = _replay([_mark("J9", "7", "9", "ie")])
    assert result.step("marks", STEP_ORPHAN) == 1
    assert result.step("marks", STEP_LESSON_MISSING) == 0
    assert result.step("marks", STEP_WRITTEN) == 0


def test_cell_without_enrollment_is_unresolved_not_lesson_missing():
    result = _replay([_mark("J3", "999", "9", "ie")])
    assert result.step("marks", STEP_UNRESOLVED) == 1
    assert result.step("marks", STEP_LESSON_MISSING) == 0


def test_cell_whose_lesson_slot_never_materialised_is_not_written():
    """Nərdivanın YENİ pilləsi: slot yoxdursa ``LessonMark`` yarana bilmir."""

    result = _replay([_mark("J3", "7", "10", "5")])  # 10-cu gün üçün slot yoxdur
    assert result.step("marks", STEP_LESSON_MISSING) == 1
    assert result.step("marks", STEP_WRITTEN) == 0
    assert result.lesson_missing_journals == {"J3"}


def test_unresolved_calendar_evidence_exposes_exact_source_payload_and_hash_key():
    row = _source_row(_mark("J3", "7", "10", "8"), 77)
    result = _replay([row])
    assert len(result.unresolved_calendar_evidence) == 1
    evidence = result.unresolved_calendar_evidence[0]
    assert evidence.source_row_hash_key == ("journals_dates_points", 77)
    assert (evidence.journal_uniqid, evidence.student_ref) == ("J3", "7")
    assert (evidence.month, evidence.day, evidence.raw_day, evidence.time_text) == (3, 10, "10", "11:30")
    assert (evidence.raw_value, evidence.normalized_value) == ("8", "score:8")
    assert evidence.issue_reason == f"{STEP_LESSON_SOURCE_PRESENT}:{SUBSTEP_SLOT_NOT_MATERIALISED}"


def test_unresolved_calendar_evidence_starts_only_after_enrollment_resolution():
    rows = [_mark("J9", "7", "9", "ie"), _mark("J3", "999", "9", "ie")]
    result = _replay(rows)
    assert result.unresolved_calendar_evidence == []


def test_lesson_slot_mismatch_on_time_counts_as_missing():
    """Gün var, saat başqadır → yenə slot yoxdur (saat açarın hissəsidir)."""

    result = _replay([_mark("J3", "7", "9", "5", time_text="15:00")])
    assert result.step("marks", STEP_LESSON_MISSING) == 1


def test_resolved_cell_with_slot_is_written():
    result = _replay([_mark("J3", "7", "9", "7")])
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_DEDUPED) == 1


# ── Hədəf açarı toqquşması ───────────────────────────────────────────────────


def test_merged_journals_collide_on_the_same_target_key():
    """İki jurnal bir açılışa birləşir → ikinci xana sətir YARATMIR."""

    result = _replay([_mark("J1", "7", "9", "ie"), _mark("J2", "7", "9", "ie")])
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_COLLISION) == 1
    assert result.step("marks", STEP_COLLISION_SAME) == 1
    assert result.step("marks", STEP_COLLISION_OTHER) == 0


def test_collision_with_a_different_value_is_reported_separately():
    """Fərqli dəyər = HƏQİQİ İTKİ; uduzan dəyər heç yerdə saxlanmır."""

    result = _replay([_mark("J1", "7", "9", "qb"), _mark("J2", "7", "9", "ie")])
    assert result.step("marks", STEP_COLLISION) == 1
    assert result.step("marks", STEP_COLLISION_SAME) == 0
    assert result.step("marks", STEP_COLLISION_OTHER) == 1
    assert result.collision_journals == {"J2"}


def test_collision_evidence_keeps_exact_loser_and_winner_source_identity():
    rows = [
        _source_row(_mark("J1", "7", "9", "qb"), 101),
        _source_row(_mark("J2", "7", "9", "ie"), 205),
    ]
    result = _replay(rows)
    assert len(result.conflict_evidence) == 1
    evidence = result.conflict_evidence[0]
    assert (evidence.source_table, evidence.source_pk, evidence.raw_value) == (
        "journals_dates_points",
        205,
        "ie",
    )
    assert (evidence.winner_source_table, evidence.winner_source_pk, evidence.winner_raw_value) == (
        "journals_dates_points",
        101,
        "qb",
    )
    assert evidence.normalized_value == "status:present"
    assert evidence.winner_normalized_value == "status:absent"
    assert evidence.source_row_hash_key == ("journals_dates_points", 205)
    assert evidence.winner_source_row_hash_key == ("journals_dates_points", 101)
    assert result.unresolved_calendar_evidence == []


def test_numeric_text_variants_are_the_same_importer_value():
    """J4/J5/J6 raw mətn yox, Decimal/int dəyəri müqayisə edir."""

    result = _replay([_mark("J1", "7", "9", "07"), _mark("J2", "7", "9", "7")])
    assert result.step("marks", STEP_COLLISION_SAME) == 1
    assert result.step("marks", STEP_COLLISION_OTHER) == 0
    assert result.conflict_evidence == []


def test_same_journal_never_collides_with_itself():
    """Dedup açarı ``uniqid``-i saxlayır → tək jurnalda toqquşma mümkün deyil."""

    rows = [_mark("J3", "7", "9", "ie"), _mark("J3", "8", "9", "ie")]
    result = _replay(rows)
    assert result.step("marks", STEP_COLLISION) == 0
    assert result.step("marks", STEP_WRITTEN) == 2


def test_components_collide_per_month_code_not_per_day():
    """Komponent açarı ``(komponent, yazılış)``-dır — gün iştirak etmir."""

    rows = [
        ("J1", "7", "components", "k1", "0", "00:00", "9"),
        ("J2", "7", "components", "k1", "0", "00:00", "7"),
        ("J2", "7", "components", "k2", "0", "00:00", "7"),
    ]
    result = _replay(rows)
    assert result.step("components", STEP_WRITTEN) == 2  # k1 + k2
    assert result.step("components", STEP_COLLISION) == 1
    assert result.step("components", STEP_COLLISION_OTHER) == 1


def test_same_legacy_enrollment_can_collide_after_target_normalisation():
    """Tək ``uniqid:student`` də komponentin gün/saatı hədəf açarında itirir."""

    rows = [
        _source_row(("J3", "7", "components", "k1", "1", "09:00", "9"), 10, local_repeat=True),
        _source_row(("J3", "7", "components", "k1", "2", "10:00", "7"), 11, local_repeat=True),
    ]
    result = _replay(rows)
    assert result.step("components", STEP_WRITTEN) == 1
    assert result.step("components", STEP_COLLISION_OTHER) == 1
    assert [item.source_pk for item in result.conflict_evidence] == [11]


def test_same_journal_day_text_variants_are_tracked_without_a_merged_enrollment():
    rows = [
        _source_row(_mark("J3", "7", "9", "ie"), 20, local_repeat=True),
        _source_row(_mark("J3", "7", "09", "qb"), 21, local_repeat=True),
    ]
    result = _replay(rows)
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_COLLISION_OTHER) == 1


def test_archive_existing_target_is_superseded_not_a_conflict():
    rows = [
        _source_row(_mark("J1", "7", "9", "ie"), 10, local_repeat=True),
        _source_row(_mark("J2", "7", "9", "qb"), 2, archive=True, local_repeat=True),
    ]
    result = _replay(rows)
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_ARCHIVE_SUPERSEDED) == 1
    assert result.step("marks", STEP_COLLISION) == 0
    assert result.conflict_evidence == []


def test_live_row_after_archive_is_rejected_fail_closed():
    rows = [
        _source_row(_mark("J1", "7", "9", "ie"), 1, archive=True),
        _source_row(_mark("J2", "7", "9", "ie"), 2),
    ]
    with pytest.raises(ValueError, match="source_order_invalid"):
        _replay(rows)


def test_finals_collide_per_exam_code():
    rows = [
        ("J1", "7", "finals", "im", "0", "00:00", "47"),
        ("J2", "7", "finals", "im", "0", "00:00", "48"),
        ("J2", "7", "finals", "im2", "0", "00:00", "48"),
    ]
    result = _replay(rows)
    assert result.step("finals", STEP_WRITTEN) == 2
    assert result.step("finals", STEP_COLLISION_OTHER) == 1


def test_components_and_finals_never_use_the_lesson_gate():
    """Slot qapısı YALNIZ təqvim domenindədir — komponent dərsə bağlanmır."""

    rows = [("J3", "7", "components", "si", "0", "", "10"), ("J3", "7", "finals", "im", "0", "", "88")]
    result = _replay(rows)
    assert result.step("components", STEP_LESSON_MISSING) == 0
    assert result.step("finals", STEP_LESSON_MISSING) == 0
    assert result.step("components", STEP_WRITTEN) == 1
    assert result.step("finals", STEP_WRITTEN) == 1


def test_unknown_month_code_is_left_out_of_every_domain():
    """``unknown_code`` heç bir domenə düşmür — hesabat onu ayrıca göstərir."""

    result = _replay([("J3", "7", "unknown_code", "pa", "0", "", "5")])
    assert sum(sum(counter.values()) for counter in result.counts.values()) == 0


# ── Yaddaş optimizasiyasının doğruluq şərti ──────────────────────────────────


def test_multi_key_enrollment_targets_finds_only_merged_targets():
    assert multi_key_enrollment_targets(ENROLLMENTS) == {"enr-1"}
    assert multi_key_enrollment_targets({"a": "x", "b": "y"}) == set()


def test_replay_result_is_identical_when_every_target_key_is_tracked():
    """«Yalnız birləşmiş yazılışı izlə» qısayolu nəticəni DƏYİŞMİR.

    Bu, ``multi_key_enrollment_targets`` sənədindəki riyazi iddianın icra
    yoxlamasıdır: bütün yazılışlar izlənsə də saylar eyni qalır.
    """

    rows = [
        _mark("J1", "7", "9", "ie"),
        _mark("J2", "7", "9", "qb"),
        _mark("J3", "7", "9", "5"),
        _mark("J3", "8", "9", "5"),
    ]
    lean = _replay(rows)
    full = replay_writes(
        rows,
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS,
        multi_key_enrollments=set(ENROLLMENTS.values()),  # HAMISI izlənir
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert lean.counts == full.counts


# ── İtkinin tərkibi ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("point", "expected"),
    [("ie", SHAPE_PRESENT), ("qb", SHAPE_ABSENT), ("0", SHAPE_SCORE), ("10", SHAPE_SCORE)],
)
def test_value_shape_separates_attendance_from_real_marks(point, expected):
    assert value_shape(point) == expected


def test_lesson_missing_shapes_separate_lost_marks_from_lost_attendance():
    rows = [_mark("J3", "7", "10", "8"), _mark("J3", "7", "11", "qb"), _mark("J3", "8", "12", "ie")]
    result = _replay(rows)
    assert result.lesson_missing_shapes[SHAPE_SCORE] == 1
    assert result.lesson_missing_shapes[SHAPE_ABSENT] == 1
    assert result.lesson_missing_shapes[SHAPE_PRESENT] == 1


# ── Nərdivana inteqrasiya ────────────────────────────────────────────────────


def _facts(replay):
    """Nərdivanın tələb etdiyi minimal mənbə/hədəf fakt dəsti."""

    deduped = replay.step("marks", STEP_DEDUPED)
    written = replay.step("marks", STEP_WRITTEN)
    source_facts = {
        # Xam mənbədə bir dublikat da var (J-V4 uduzanı) — dedup pilləsi onu çıxır.
        "classification": {("live", 1, "marks", "writable"): deduped + 1},
        "raw_writable": {"marks": deduped + 1},
    }
    target_facts = {"entity_counts": {"lessonmark": written}}
    return source_facts, target_facts


def test_new_steps_close_the_ladder_to_zero():
    rows = [
        _mark("J9", "7", "9", "ie"),  # orphan
        _mark("J3", "999", "9", "ie"),  # həll olunmayan yazılış
        _mark("J3", "7", "10", "8"),  # dərs slotu yoxdur
        _mark("J1", "7", "9", "ie"),  # yazılır
        _mark("J2", "7", "9", "qb"),  # toqquşma (fərqli dəyər)
    ]
    replay = _replay(rows)
    source_facts, target_facts = _facts(replay)
    ladder = build_ladders(source_facts, target_facts, replay)["marks"]
    labels = [label for label, _count in ladder.steps]
    assert LABEL_LESSON_SOURCE_ABSENT in labels
    assert LABEL_LESSON_SOURCE_PRESENT in labels
    assert LABEL_COLLISION_SAME in labels
    assert LABEL_COLLISION_OTHER in labels
    assert ladder.unexplained == 0
    assert ladder.balanced


def test_ladder_without_replay_leaves_the_write_steps_out():
    """``--skip-deep``: yeni pillələr YAZILMIR, qalıq açıq qalır."""

    source_facts = {
        "classification": {("live", 1, "marks", "writable"): 100},
        "raw_writable": {"marks": 100},
    }
    ladder = build_ladders(source_facts, {"entity_counts": {"lessonmark": 10}}, None)["marks"]
    assert [label for label, _count in ladder.steps] == [
        "boş xana (mənbədə dəyər yoxdur)",
        "oxunmayan xana (karantin)",
        "arxiv örtüşməsi (J-V7 kəsimindən sonra)",
    ]
    assert ladder.unexplained == 90


def test_lesson_step_is_absent_for_component_and_final_domains():
    """Komponent/imtahan domenində dərs slotu pilləsi STRUKTUR olaraq yoxdur."""

    replay = _replay([("J3", "7", "components", "k1", "0", "", "9")])
    ladders = build_ladders(
        {"classification": {}, "raw_writable": {}},
        {"entity_counts": {}},
        replay,
    )
    component_labels = [label for label, _ in ladders["components"].steps]
    assert LABEL_LESSON_SOURCE_ABSENT not in component_labels
    assert LABEL_LESSON_SOURCE_PRESENT not in component_labels
    assert LABEL_COLLISION_SAME in component_labels
    assert LABEL_COLLISION_OTHER in component_labels


def test_a_missed_write_still_opens_the_gate():
    """Qapı vacuum DEYİL: pillələr hədəfin sayından asılı olmadan hesablanır.

    Yazılması gözlənilən bir sətir hədəfə düşməsə (hər hansı başqa səbəbdən)
    nərdivan yenə 🔴 verir — yeni pillələr onu «bağlaya» bilmir.
    """

    replay = _replay([_mark("J3", "7", "9", "7")])
    source_facts, target_facts = _facts(replay)
    target_facts["entity_counts"]["lessonmark"] -= 1  # sətir hədəfdə yoxdur
    ladder = build_ladders(source_facts, target_facts, replay)["marks"]
    assert ladder.unexplained == 1
    assert not ladder.balanced


# ── Oxu-only müqaviləsi ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sql", [deduped_cell_keys_sql(), lesson_slot_source_sql(), LESSON_SLOT_SQL, ENROLLMENT_OFFERING_SQL]
)
def test_new_queries_pass_the_read_only_gate(sql):
    assert_read_only(sql)


def test_deduped_cell_keys_sql_mirrors_the_two_importer_elections():
    sql = deduped_cell_keys_sql()
    assert "PARTITION BY source_order, journal_uniqid, student_id, mid, dn, tm" in sql
    assert "ROW_NUMBER() OVER" in sql
    assert "WHERE election_rank = 1 AND" in sql  # yazı qapısı seçkidən SONRA
    assert "TIME_TO_SEC(time) >= 86400" in sql  # importer-in ``normalized_time`` güzgüsü
    assert "ORDER BY source_order, CASE WHEN election_count > 1 THEN 1 ELSE 0 END, pk" in sql
    # Arxiv öz seçkisindədir və J-V7 kəsimindən sonrakı sətirlər axına düşmür.
    assert "'journals_dates_points_archive'" in sql and "added_date" in sql
    assert "local_target_repeat" in sql
    elected = sql.split("), elected AS (", 1)[1].split("), annotated AS (", 1)[0]
    assert "BETWEEN 1 AND 31" not in elected  # gün qapısı J4 distill-dən sonra gəlir
    assert isinstance(Ladder(name="marks", source_total=0, target=0).steps, list)


def test_day_number_text_variants_map_to_the_same_lesson():
    """Legacy ``day_number`` mətn sütunudur: ``"9"`` və ``"09"`` EYNİ dərsdir.

    Normalizasiya olmasa iki variant süni şəkildə «toqquşmayan» görünür və
    toqquşma pilləsi az sayardı.
    """

    result = _replay([_mark("J1", "7", "9", "ie"), _mark("J2", "7", "09", "qb")])
    assert result.step("marks", STEP_LESSON_MISSING) == 0
    assert result.step("marks", STEP_COLLISION) == 1
    assert result.step("marks", STEP_COLLISION_OTHER) == 1


@pytest.mark.parametrize("raw_day", ["0", "32", "abc"])
def test_invalid_day_still_becomes_the_same_j12_unresolved_grade_fact(raw_day):
    """J4 day parse uğursuzluğunu ``(0, 0)``-a salır; replay də atmamalıdır."""

    result = _replay([_source_row(_mark("J3", "7", raw_day, "8", month="04"), 81)])
    assert result.step("marks", STEP_LESSON_SOURCE_ABSENT) == 1
    evidence = result.unresolved_calendar_evidence[0]
    assert (evidence.month, evidence.day, evidence.raw_day) == (0, 0, raw_day)
    extra = replay_grade_fact_rows(result)
    assert len(extra) == 1
    assert (extra[0][3], extra[0][7], extra[0][14]) == ("00", "calendar:00:0:11:30", "8")


# ── YENİ: «dərs slotu tapılmadı» pilləsinin MƏNBƏ ilə ikiyə bölünməsi ────────


def test_missing_lesson_splits_by_whether_the_source_has_the_slot():
    """Eyni «slot yoxdur» halı İKİ FƏRQLİ SƏBƏBƏ bölünür.

    ``J3``-ün 10-cu günü MƏNBƏDƏ var (hədəfdə materiallaşmayıb) → köçürmə
    qərarı; 11-ci gün mənbədə də yoxdur → mənbənin öz boşluğu (J12 hədəfi).
    """

    result = _replay([_mark("J3", "7", "10", "8"), _mark("J3", "7", "11", "9")])
    assert result.step("marks", STEP_LESSON_MISSING) == 2
    assert result.step("marks", STEP_LESSON_SOURCE_PRESENT) == 1
    assert result.step("marks", STEP_LESSON_SOURCE_ABSENT) == 1


def test_source_absent_substep_separates_missing_day_from_missing_time():
    """«Mənbədə yoxdur» nə qədər dərindir: gün də yoxdur, yoxsa yalnız saat?"""

    rows = [
        _mark("J3", "7", "11", "9"),  # gün ümumiyyətlə yoxdur
        _mark("J3", "7", "12", "9"),  # gün var (08:30), saat 11:30 → uyğun gəlmir
    ]
    result = _replay(rows)
    assert result.step("marks", STEP_LESSON_SOURCE_ABSENT) == 2
    assert result.source_slot_substeps[SUBSTEP_DAY_ABSENT] == 1
    assert result.source_slot_substeps[SUBSTEP_DAY_PRESENT_TIME_DIFFERS] == 1


def test_empty_source_index_is_refused_instead_of_silently_blaming_the_source():
    """Fail-closed: indeks boşdursa BÜTÜN itki səhvən «mənbədə yoxdur» olardı."""

    with pytest.raises(ValueError, match="source_lesson_slots_empty"):
        _replay([_mark("J3", "7", "10", "8")], source_slots=set())


def test_recovered_lesson_drops_the_source_absent_rung_to_zero():
    """J12-nin proqnozu: dərs hədəfdə yaranan kimi pillə SIFIRA enir.

    Bərpa hədəfdə ``Lesson`` yaradır — yəni slot xəritəsinə yeni açar düşür və
    xana artıq dərs qapısına ilişmir.  Nərdivan bunu HEÇ BİR xüsusi bilik
    olmadan görür: pillə sadəcə boşalır.
    """

    row = _mark("J3", "7", "11", "9")
    before = _replay([row])
    assert before.step("marks", STEP_LESSON_SOURCE_ABSENT) == 1

    after = replay_writes(
        [row],
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS | {("off-2", 3, 11, "11:30")},  # J12 bərpası
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert after.step("marks", STEP_LESSON_SOURCE_ABSENT) == 0
    assert after.step("marks", STEP_LESSON_MISSING) == 0
    assert after.step("marks", STEP_WRITTEN) == 1


# ── YENİ: pillələrin ayrıqlığı ÖLÇÜLÜR ──────────────────────────────────────


def test_every_cell_lands_on_exactly_one_rung():
    """Bütöv = hissələrin cəmi.  Qalıq varsa pillələr ya örtüşür, ya boşluq var."""

    rows = [
        _mark("J9", "7", "9", "ie"),  # orphan
        _mark("J3", "999", "9", "ie"),  # həll olunmayan yazılış
        _mark("J3", "7", "10", "8"),  # slot mənbədə VAR
        _mark("J3", "7", "11", "8"),  # slot mənbədə YOXDUR
        _mark("J1", "7", "9", "ie"),  # yazılır
        _mark("J2", "7", "9", "qb"),  # toqquşma — fərqli dəyər
    ]
    result = _replay(rows)
    assert [residual for *_head, residual in identity_residuals(result)] == [0] * 9


def test_rung_overlap_is_measured_at_journal_and_enrollment_level():
    """Xana səviyyəsində kəsişmə 0-dır, JURNAL səviyyəsində ola bilər — ölçülür."""

    rows = [
        _mark("J1", "7", "9", "ie"),  # yazılır
        _mark("J2", "7", "9", "qb"),  # toqquşma (fərqli dəyər), jurnal J2
        _mark("J2", "7", "11", "5"),  # slot mənbədə yoxdur, jurnal J2
    ]
    result = _replay(rows)
    overlaps = {
        (first, second): (journals, enrollments) for first, second, journals, enrollments in rung_overlaps(result)
    }
    assert overlaps[(STEP_LESSON_SOURCE_ABSENT, STEP_COLLISION_OTHER)] == (1, 1)
    assert overlaps[(STEP_LESSON_SOURCE_ABSENT, STEP_LESSON_SOURCE_PRESENT)] == (0, 0)
    # Kəsişməyə baxmayaraq xana sayı ikiqat GETMİR:
    assert [residual for *_head, residual in identity_residuals(result)] == [0] * 9


def test_rung_shapes_separate_lost_marks_per_rung():
    """İtkinin ağırlığı pillə-pillə ayrılır (bal vs davamiyyət)."""

    rows = [_mark("J3", "7", "10", "8"), _mark("J3", "7", "11", "qb")]
    result = _replay(rows)
    assert result.rung_shapes[STEP_LESSON_SOURCE_PRESENT][SHAPE_SCORE] == 1
    assert result.rung_shapes[STEP_LESSON_SOURCE_ABSENT][SHAPE_ABSENT] == 1


def test_lesson_slot_source_sql_joins_journals_for_the_uniqid_key():
    sql = lesson_slot_source_sql()
    assert "journals_dates_added_by_teacher" in sql
    assert "JOIN journals j ON j.id = t.journal_id" in sql
    assert "j.uniqid" in sql


def test_lesson_slot_sql_keeps_lessons_whose_start_time_is_unknown():
    """J12 saatı oxunmayan dərsi ``start_time = NULL`` ilə yaradır — süzülməməlidir.

    Süzülsəydi nərdivan hədəfdə MÖVCUD olan sətirləri «yazılmayıb» sayardı
    (bərpa nüsxəsində ölçülüb: 18 xana).
    """

    assert "start_time IS NOT NULL" not in LESSON_SLOT_SQL
    assert "COALESCE(to_char(l.start_time, 'HH24:MI'), '')" in LESSON_SLOT_SQL


def test_cell_with_unknown_time_matches_a_lesson_with_null_start_time():
    """Saatı oxunmayan xana ('' açarı) NULL saatlı dərsə bağlanır."""

    result = replay_writes(
        [_mark("J3", "7", "13", "8", time_text="")],
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS | {("off-2", 3, 13, "")},  # NULL start_time
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_LESSON_MISSING) == 0


# ── YENİ: 1-ci pillənin «bərpadan sonra sıfır» proqnozu hesabatda ────────────


def test_recovery_block_says_the_copy_predates_the_recovery():
    """Sxem bərpanı tanımırsa ölçmə bərpadan ƏVVƏLKİ vəziyyətdir — açıq yazılır."""

    text = recovery_block({"present": False}, 164_747)
    assert "tanIMIR".upper() in text.upper()
    assert "164,747" in text


def test_recovery_block_separates_schema_from_an_unused_recovery():
    """Sütun var, sintetik dərs yoxdur → bərpa İŞLƏDİLMƏYİB (pillə açıq qalır)."""

    text = recovery_block({"present": True, "lessons": 0}, 100)
    assert "işlədilməyib" in text
    assert "100" in text


def test_recovery_block_confirms_the_prediction_when_the_rung_is_empty():
    text = recovery_block({"present": True, "lessons": 11_607, "marks": 161_775}, 0)
    assert "TUTDU" in text
    assert "11,607" in text and "161,775" in text


def test_recovery_block_refuses_to_declare_success_when_the_rung_is_not_empty():
    """Bərpa var, amma pillə dolu → 🔴; hesabat uğuru İDDİA ETMİR."""

    text = recovery_block({"present": True, "lessons": 11_607, "marks": 161_775}, 42)
    assert "TUTMADI" in text
    assert "42" in text


@pytest.mark.parametrize("sql", [LESSON_SYNTH_COLUMN_SQL, LESSON_SYNTH_COUNT_SQL, LESSON_SYNTH_MARK_SQL])
def test_recovery_queries_pass_the_read_only_gate(sql):
    assert_read_only(sql)


def test_recovery_count_query_is_tenant_scoped_on_both_tables():
    """Xana sayğacı HƏR İKİ cədvəldə tenant süzgəcindən keçməlidir (RLS güzgüsü)."""

    assert "l.organization_id = %s::uuid" in LESSON_SYNTH_MARK_SQL
    assert "m.organization_id = %s::uuid" in LESSON_SYNTH_MARK_SQL
    assert "l.organization_id = %s::uuid" in LESSON_SYNTH_COUNT_SQL


# ── YENİ: J12-nin «oxunmayan saat» güzgüsü ──────────────────────────────────


@pytest.mark.parametrize(
    ("text", "readable"),
    [
        ("11:30", True),
        ("00:00", True),
        ("23:59", True),
        ("80:30", False),
        ("45:00", False),
        ("10:0_", False),
        ("", False),
    ],
)
def test_is_readable_time_rejects_the_legacy_clock_errors(text, readable):
    """``80:30`` MariaDB üçün qanuni TIME-dır, divar saatı üçün YOX."""

    assert is_readable_time(text) is readable


def test_unreadable_time_cell_binds_to_the_recovered_null_time_lesson():
    """J12 güzgüsü: pozuq saatlı xana ``start_time = NULL`` dərsinə oturur.

    Ölçülüb (``emsarena_j12_verify``): bu qayda olmadan bərpa nüsxəsində 18
    xana «yazılmayıb» sayılırdı, halbuki hədəfdə MÖVCUD idi.
    """

    row = _mark("J3", "7", "14", "ie", time_text="80:30")
    before = _replay([row])
    assert before.step("marks", STEP_LESSON_MISSING) == 1

    after = replay_writes(
        [row],
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS | {("off-2", 3, 14, "")},  # J12: saat naməlum
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert after.step("marks", STEP_WRITTEN) == 1
    assert after.step("marks", STEP_SYNTH_TIME_UNKNOWN) == 1
    assert after.step("marks", STEP_LESSON_MISSING) == 0


def test_readable_time_never_falls_back_to_the_null_time_lesson():
    """Oxunaqlı saat ehtiyat axtarışa DÜŞMÜR — yoxsa qonşu dərsə sürüşərdi."""

    result = replay_writes(
        [_mark("J3", "7", "14", "ie", time_text="15:00")],
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS | {("off-2", 3, 14, "")},
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert result.step("marks", STEP_LESSON_MISSING) == 1
    assert result.step("marks", STEP_SYNTH_TIME_UNKNOWN) == 0


def test_fallback_is_a_no_op_without_a_null_time_lesson():
    """Bərpasız nüsxədə (0 boş saatlı dərs) qayda heç nəyi dəyişmir."""

    result = _replay([_mark("J3", "7", "14", "ie", time_text="80:30")])
    assert result.step("marks", STEP_SYNTH_TIME_UNKNOWN) == 0
    assert result.step("marks", STEP_LESSON_MISSING) == 1


def test_two_unreadable_times_on_one_day_collide_on_the_same_recovered_lesson():
    """İki pozuq saat BİR dərsə düşür → hədəf açarı toqquşması (sətir bir dənədir)."""

    rows = [
        _mark("J1", "7", "14", "ie", time_text="80:30"),
        _mark("J2", "7", "14", "qb", time_text="45:00"),
    ]
    result = replay_writes(
        rows,
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS | {("off-1", 3, 14, "")},
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert result.step("marks", STEP_WRITTEN) == 1
    assert result.step("marks", STEP_COLLISION_OTHER) == 1
    assert [residual for *_head, residual in identity_residuals(result)] == [0] * 9


# ── YENİ: 2-ci pillənin daxili bölgüsü (mənbənin təqvim/saat səhvi) ─────────


@pytest.mark.parametrize(
    ("month", "day", "time_text", "expected"),
    [
        ("04", "31", "08:30", SUBSTEP_IMPOSSIBLE_DATE),  # aprelin 31-i yoxdur
        ("09", "31", "08:30", SUBSTEP_IMPOSSIBLE_DATE),
        ("11", "31", "18:40", SUBSTEP_IMPOSSIBLE_DATE),
        ("02", "30", "12:00", SUBSTEP_IMPOSSIBLE_DATE),
        ("02", "29", "12:00", SUBSTEP_LEAP_DEPENDENT_DATE),  # il sütunu YOXDUR
        ("03", "31", "80:30", SUBSTEP_UNREADABLE_TIME),  # tarix qanuni, saat yox
        ("03", "31", "11:30", SUBSTEP_SLOT_NOT_MATERIALISED),  # hər ikisi qanuni → AÇIQ
        ("13", "01", "11:30", SUBSTEP_IMPOSSIBLE_DATE),  # 13-cü ay
        ("xx", "01", "11:30", SUBSTEP_IMPOSSIBLE_DATE),  # rəqəm deyil
    ],
)
def test_source_slot_reason_names_every_measured_case(month, day, time_text, expected):
    assert source_slot_reason(month, day, time_text) == expected


def test_second_rung_is_split_by_the_source_own_calendar_error():
    """Ölçüldü (52ea): 105 xananın hamısı mənbənin təqvim/saat səhvidir."""

    rows = [
        _mark("J3", "7", "10", "8"),  # tarix də, saat da qanuni → adsız qalıq
        _mark("J3", "8", "10", "9"),
    ]
    result = replay_writes(
        rows,
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS,
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS,
    )
    assert result.step("marks", STEP_LESSON_SOURCE_PRESENT) == 2
    assert result.source_present_substeps[SUBSTEP_SLOT_NOT_MATERIALISED] == 2


def test_impossible_date_lands_in_the_named_bucket_not_the_open_one():
    """31 noyabr mənbə slotu var, hədəf dərsi YOXDUR — səbəb adlandırılır."""

    row = ("J3", "7", "marks", "11", "31", "18:40", "ie")
    result = replay_writes(
        [row],
        offering_journals=offering_journal_keys(OFFERINGS),
        enrollments=ENROLLMENTS,
        enrollment_offerings=ENROLLMENT_OFFERINGS,
        lesson_slots=LESSON_SLOTS,
        multi_key_enrollments=multi_key_enrollment_targets(ENROLLMENTS),
        source_lesson_slots=SOURCE_LESSON_SLOTS | {("J3", 11, 31, "18:40")},
    )
    assert result.step("marks", STEP_LESSON_SOURCE_PRESENT) == 1
    assert result.source_present_substeps[SUBSTEP_IMPOSSIBLE_DATE] == 1
    assert result.source_present_substeps[SUBSTEP_SLOT_NOT_MATERIALISED] == 0


def test_first_rung_substeps_are_not_polluted_by_the_second():
    """İki pillənin alt-bölgüsü AYRI sayğaclardır — qarışmır."""

    result = _replay([_mark("J3", "7", "11", "9")])  # mənbədə də yoxdur
    assert sum(result.source_present_substeps.values()) == 0
    assert sum(result.source_slot_substeps.values()) == 1
