"""``scripts/legacy_reconcile_report.py`` məntiq funksiyalarının testləri.

Bu testlər BAZAYA TOXUNMUR: yalnız saf funksiyalar (nərdivan balansı, xana
təsnifatı, histoqram, dedup, formatlayıcılar və oxu-only qapısı) yoxlanılır.
Ona görə həm CI-də (sqlite loop), həm də repetisiya işləyərkən təhlükəsizdir.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:  # skript Django kontekstindən kənarda da işləyir
    sys.path.insert(0, str(ROOT))

from scripts.legacy_reconcile.analysis import (  # noqa: E402
    DELTA_BUCKETS,
    Ladder,
    bucket_deltas,
    classify_cell,
    clean_legacy_text,
    dedup_cells,
    delta_bucket,
    diff_flag,
    domain_of,
    entry_score,
    fmt_int,
    fmt_num,
    fmt_pct,
    fmt_signed,
    ladder_table,
    md_table,
    pick_sample,
    summarise_cells,
    total_score,
    unescape_batch_field,
)
from scripts.legacy_reconcile.collect import _archive_overlap, _sum_outcome, out_of_scope_cells  # noqa: E402
from scripts.legacy_reconcile.render_detail import _compare_if_present  # noqa: E402
from scripts.legacy_reconcile.sampling import stratified_sample  # noqa: E402
from scripts.legacy_reconcile.transport import ReadOnlyViolation, assert_read_only  # noqa: E402

# ── Xana təsnifatı ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("month", "day", "point", "expected"),
    [
        ("01", "17", "ie", ("marks", "writable")),
        ("12", "1", "qb", ("marks", "writable")),
        ("04", "17", "7", ("marks", "writable")),
        ("04", "17", "10", ("marks", "writable")),
        ("04", "17", "11", ("marks", "unreadable")),  # şkaladan kənar → təhrif YOX
        ("04", "17", "", ("marks", "empty")),
        ("04", "17", "l", ("marks", "unreadable")),
        ("04", "0", "5", ("marks", "unreadable")),  # gün nömrəsi pozuq
        ("04", "32", "5", ("marks", "unreadable")),
        ("04", "abc", "5", ("marks", "unreadable")),
        ("k1", "0", "9", ("components", "writable")),
        ("si", "0", "10", ("components", "writable")),
        ("k2", "0", "11", ("components", "unreadable")),
        ("k3", "0", "qb", ("components", "unreadable")),  # davamiyyət kodu bal deyil
        ("si", "0", "", ("components", "empty")),
        ("im", "0", "100", ("finals", "writable")),
        ("im2", "0", "45", ("finals", "writable")),
        ("im", "0", "101", ("finals", "unreadable")),
        ("im", "0", "", ("finals", "empty")),
        ("zz", "0", "5", ("unknown_code", "out_of_scope")),
        ("", "0", "5", ("unknown_code", "out_of_scope")),
    ],
)
def test_classify_cell(month, day, point, expected):
    assert classify_cell(month, day, point) == expected


def test_domain_of_covers_every_calendar_month():
    assert {domain_of(f"{month:02d}") for month in range(1, 13)} == {"marks"}
    assert domain_of("13") == "unknown_code"
    assert domain_of("1") == "unknown_code"  # sıfır doldurulmamış forma qəbul edilmir


def test_ie_is_attendance_not_a_score():
    """``ie`` bal deyil — davamiyyətdir; təsnifat onu bala çevirmir."""

    domain, outcome = classify_cell("05", "3", "ie")
    assert (domain, outcome) == ("marks", "writable")
    summary = summarise_cells([("J1", "7", "05", "3", "", "ie", 0, "", 1)])
    assert summary[("7", "J1")]["istirak"] == 1
    assert summary[("7", "J1")]["seminar_sum"] == Decimal("0")
    assert summary[("7", "J1")]["seminar_count"] == 0


# ── Nərdivan (sətir mühasibatı) ──────────────────────────────────────────────


def test_ladder_balances_when_every_row_is_accounted():
    ladder = Ladder(name="marks", source_total=100, target=70)
    ladder.deduct("boş", 10)
    ladder.deduct("orphan", 20)
    assert ladder.expected == 70
    assert ladder.unexplained == 0
    assert ladder.balanced


def test_ladder_reports_silent_loss_openly():
    ladder = Ladder(name="marks", source_total=100, target=50)
    ladder.deduct("boş", 10)
    assert ladder.unexplained == 40
    assert not ladder.balanced
    rows = ladder_table(ladder)
    assert rows[-1][0].startswith("🔴")
    assert rows[-1][-1] == "**+40**"


def test_ladder_flags_surplus_rows_in_target():
    """Hədəfdə ARTIQ sətir də izahsız fərqdir — mənfi işarə ilə görünür."""

    ladder = Ladder(name="finals", source_total=100, target=120)
    assert ladder.unexplained == -20
    assert ladder_table(ladder)[-1][-1] == "**-20**"


def test_ladder_table_running_remainder_is_monotonic():
    ladder = Ladder(name="marks", source_total=100, target=40)
    ladder.deduct("boş", 10)
    ladder.deduct("dublikat", 25)
    remainders = [row[2] for row in ladder_table(ladder)[1:3]]
    assert remainders == ["90", "65"]


# ── Aqreqat köməkçiləri ──────────────────────────────────────────────────────


def _classification():
    return {
        ("live", 1, "marks", "empty"): 5,
        ("live", 1, "marks", "writable"): 100,
        ("archive", 1, "marks", "empty"): 2,
        ("archive", 0, "marks", "writable"): 7,
        ("archive", 0, "marks", "empty"): 3,
        ("live", 1, "unknown_code", "out_of_scope"): 11,
    }


def test_sum_outcome_spans_live_and_archive():
    assert _sum_outcome(_classification(), "marks", "empty") == 10


def test_archive_overlap_counts_only_writable_ineligible_rows():
    """Boş/oxunmayan örtüşmələr artıq başqa pillədə çıxılıb — ikiqat sayılmır."""

    assert _archive_overlap(_classification(), "marks") == 7


def test_out_of_scope_cells_are_surfaced_not_hidden():
    assert out_of_scope_cells({"classification": _classification()}) == 11


# ── Histoqram ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("delta", "bucket"),
    [
        (0, "0"),
        (Decimal("0"), "0"),
        (1, "±1"),
        (-1, "±1"),
        (Decimal("0.5"), "±1"),
        (2, "±2"),
        (-2, "±2"),
        (Decimal("2.5"), "±3–5"),
        (5, "±3–5"),
        (-5, "±3–5"),
        (Decimal("5.1"), ">5"),
        (-40, ">5"),
    ],
)
def test_delta_bucket(delta, bucket):
    assert delta_bucket(delta) == bucket


def test_bucket_deltas_always_reports_every_bucket():
    counts = bucket_deltas([0, 0, 3, -9])
    assert set(counts) == set(DELTA_BUCKETS)
    assert counts == {"0": 2, "±1": 0, "±2": 0, "±3–5": 1, ">5": 1}


# ── Yekun balı güzgüsü ───────────────────────────────────────────────────────


def test_entry_score_is_clamped_by_scheme_cap():
    assert entry_score(40, 20, 50) == Decimal("50")
    assert entry_score(30, 5, 50) == Decimal("35")


def test_total_score_prefers_resit_over_first_exam():
    assert total_score(Decimal("40"), exam=10, resit=30) == Decimal("70")
    assert total_score(Decimal("40"), exam=10, resit=None) == Decimal("50")


def test_total_score_is_clamped_to_zero_hundred():
    assert total_score(Decimal("50"), exam=90, bonus=10) == Decimal("100")
    assert total_score(Decimal("0"), exam=None) == Decimal("0")


# ── J-V4 dedup ───────────────────────────────────────────────────────────────


def _cell(point, counter, updated, pk):
    return ("J1", "7", "04", "17", "09:00", point, counter, updated, pk)


def test_dedup_prefers_highest_update_counter():
    winners = dedup_cells([_cell("5", 0, "", 1), _cell("8", 3, "", 2), _cell("6", 1, "", 9)])
    assert len(winners) == 1
    assert winners[0][5] == "8"


def test_dedup_falls_back_to_latest_update_then_biggest_pk():
    winners = dedup_cells([_cell("5", 1, "2022-01-01", 9), _cell("7", 1, "2023-01-01", 2)])
    assert winners[0][5] == "7"
    winners = dedup_cells([_cell("5", 1, "2022-01-01", 9), _cell("7", 1, "2022-01-01", 2)])
    assert winners[0][5] == "5"


def test_dedup_keeps_distinct_time_slots_apart():
    rows = [_cell("5", 0, "", 1), ("J1", "7", "04", "17", "11:00", "9", 0, "", 2)]
    assert len(dedup_cells(rows)) == 2


def test_summarise_cells_separates_attendance_scores_and_components():
    rows = [
        ("J1", "7", "04", "17", "09:00", "qb", 0, "", 1),
        ("J1", "7", "04", "18", "09:00", "8", 0, "", 2),
        ("J1", "7", "k1", "0", "", "9", 0, "", 3),
        ("J1", "7", "si", "0", "", "10", 0, "", 4),
        ("J1", "7", "im", "0", "", "45", 0, "", 5),
        ("J1", "7", "im2", "0", "", "60", 0, "", 6),
        ("J1", "7", "04", "19", "09:00", "", 0, "", 7),  # boş — sayılmır
    ]
    summary = summarise_cells(rows)[("7", "J1")]
    assert summary["qayib"] == 1
    assert summary["seminar_sum"] == Decimal("8")
    assert summary["kollokvium"] == Decimal("9")
    assert summary["serbest"] == Decimal("10")
    assert summary["imtahan"] == Decimal("45")
    assert summary["tekrar"] == Decimal("60")


# ── Təkrarlana bilən nümunə ──────────────────────────────────────────────────


def test_pick_sample_is_reproducible_and_order_independent():
    first = pick_sample(range(500), seed=20260827, size=20)
    second = pick_sample(sorted(range(500), reverse=True), seed=20260827, size=20)
    assert first == second
    assert len(first) == 20


def test_pick_sample_returns_everything_when_pool_is_small():
    assert pick_sample([3, 1, 2], seed=1, size=20) == [1, 2, 3]


def test_stratified_sample_splits_migrated_and_skipped_students_evenly():
    eligible = list(range(1, 101))
    bridge = {f"J{key}:{key}": f"uuid-{key}" for key in range(1, 51)}  # 1..50 köçüb
    picked = stratified_sample(eligible, bridge, seed=7, size=20)
    assert len(picked) == 20
    assert sum(1 for key in picked if key <= 50) == 10
    assert sum(1 for key in picked if key > 50) == 10


def test_stratified_sample_backfills_when_one_side_is_empty():
    """Bir tərəf boşdursa nümunə kiçilmir — digər tərəfdən doldurulur."""

    picked = stratified_sample(list(range(1, 101)), {}, seed=7, size=20)
    assert len(picked) == 20


def test_stratified_sample_is_reproducible():
    eligible = list(range(1, 101))
    bridge = {f"J{key}:{key}": "x" for key in range(1, 51)}
    assert stratified_sample(eligible, bridge, seed=7, size=20) == stratified_sample(
        list(reversed(eligible)), bridge, seed=7, size=20
    )


# ── Mətn və format ───────────────────────────────────────────────────────────


def test_clean_legacy_text_decodes_entities_and_collapses_spaces():
    assert clean_legacy_text("Tərc&uuml;mə  nəzəriyyəsi ") == "Tərcümə nəzəriyyəsi"
    assert clean_legacy_text("Piriyeva  Nərgiz ") == "Piriyeva Nərgiz"
    assert clean_legacy_text(None) == ""


def test_unescape_batch_field_restores_tabs_and_newlines():
    assert unescape_batch_field(r"a\tb") == "a\tb"
    assert unescape_batch_field(r"a\nb") == "a\nb"
    assert unescape_batch_field("plain") == "plain"


def test_formatters():
    assert fmt_int(2833993) == "2,833,993"
    assert fmt_int(None) == "—"
    assert fmt_signed(0) == "0"
    assert fmt_signed(-12) == "-12"
    assert fmt_signed(12) == "+12"
    assert fmt_num(Decimal("7.00")) == "7"
    assert fmt_num(Decimal("7.25")) == "7.25"
    assert fmt_pct(1, 4) == "25.0 %"
    assert fmt_pct(1, 0) == "—"


def test_md_table_escapes_pipes_in_data():
    table = md_table(["a"], [["x|y"]])
    assert "x\\|y" in table
    assert table.splitlines()[1] == "|---|"


def test_compare_if_present_treats_missing_source_as_no_evidence():
    """Legacy `yekun` sətri yoxdursa bu uyğunsuzluq deyil — saxta 🔴 verilmir."""

    assert _compare_if_present(None, Decimal("48")) == ""
    assert _compare_if_present(Decimal("48"), Decimal("48")) == ""
    assert _compare_if_present(Decimal("48"), Decimal("50")) == "🔴"


def test_diff_flag_marks_only_real_differences():
    assert diff_flag(5, 5) == ""
    assert diff_flag(5, 6) == "🔴"
    assert diff_flag(None, None) == ""
    assert diff_flag(5, None) == "🔴"
    assert diff_flag(Decimal("5.4"), Decimal("5"), tolerance=Decimal("0.5")) == ""


# ── Oxu-only qapısı ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE registrar_lessonmark SET score = 1",
        "delete from yekun",
        "SELECT 1; DROP TABLE students",
        "INSERT INTO x VALUES (1)",
        "TRUNCATE journals",
    ],
)
def test_write_statements_are_refused(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM journals_dates_points",
        "SELECT a, b FROM t GROUP BY a",
        "SHOW TABLES",
    ],
)
def test_read_statements_pass_the_gate(sql):
    assert_read_only(sql)
