"""Yeni giriş balının sərhədləri; gözləntilər qaydadan müstəqil sabit rəqəmlərdir.

Sahib 2026-10-10: sərbəst iş ləğv (defolt), midterm tavanı 30; RİM-də sərbəst iş açılsa köhnə 20 + 10 qayıdır —
hər iki variant burada kilidlənib (``settings`` fiksturası ``ACADEMIC_SELFWORK_ENABLED``)."""

from decimal import Decimal

import pytest

from apps.registrar import entry_standard as standard

KEYS = ("attendance", "activity", "midterm", "selfwork", "total")


def parts(**overrides):
    values = dict(
        cap=50,
        lesson_hours=30,
        absence_hours=0,
        limit_percent=25,
        exempt=False,
        score_sum=0,
        score_count=0,
        interim_total=0,
        selfwork_points=0,
        selfwork_counted=True,
    )
    values.update(overrides)
    return standard.compose_from_totals(**values)


def _tuple(result):
    return tuple(getattr(result, key) for key in KEYS)


#: (overrides, yeni qayda — sərbəst iş söndürülü, midterm ≤ 30, köhnə qayda — sərbəst iş açıq, midterm ≤ 20)
CASES = [
    ({}, ("10.00", "0", "0", "0", "10"), ("10.00", "0", "0", "0", "10")),
    ({"lesson_hours": 0}, ("10.00", "0", "0", "0", "10"), ("10.00", "0", "0", "0", "10")),
    ({"absence_hours": 8}, ("0", "0", "0", "0", "0"), ("0", "0", "0", "0", "0")),
    ({"absence_hours": 8, "exempt": True}, ("7.33", "0", "0", "0", "7"), ("7.33", "0", "0", "0", "7")),
    ({"score_sum": 15, "score_count": 2}, ("10.00", "7.50", "0", "0", "18"), ("10.00", "7.50", "0", "0", "18")),
    (
        {"score_sum": 34, "score_count": 4, "absence_hours": 2, "interim_total": 17, "selfwork_points": 9},
        ("9.33", "8.50", "17", "0", "35"),
        ("9.33", "8.50", "17", "9", "44"),
    ),
    (
        {"score_sum": 30, "score_count": 3, "interim_total": 25, "selfwork_points": 15},
        ("10.00", "10.00", "25", "0", "45"),
        ("10.00", "10.00", "20", "10", "50"),
    ),
    (
        {"interim_total": 35, "score_sum": 30, "score_count": 3},
        ("10.00", "10.00", "30", "0", "50"),
        ("10.00", "10.00", "20", "0", "40"),
    ),
    (
        {"interim_total": 20, "selfwork_points": 10, "cap": 35},
        ("10.00", "0", "20", "0", "30"),
        ("10.00", "0", "20", "10", "35"),
    ),
    (
        {"selfwork_points": 10, "selfwork_counted": False},
        ("10.00", "0", "0", "0", "10"),
        ("10.00", "0", "0", "0", "10"),
    ),
]


@pytest.mark.parametrize("overrides, expected, _old", CASES)
def test_composition_new_rule(overrides, expected, _old):
    result = parts(**overrides)
    assert _tuple(result) == tuple(map(Decimal, expected))
    assert (result.midterm_max, result.selfwork_active) == (Decimal("30"), False)


@pytest.mark.parametrize("overrides, _new, expected", CASES)
def test_composition_old_rule_when_selfwork_enabled(settings, overrides, _new, expected):
    """Geri dönüş (sahibin tələbi): RİM-də sərbəst iş açılanda 2026-09-25 rəqəmləri bayt-bayt qayıdır."""
    settings.ACADEMIC_SELFWORK_ENABLED = True
    result = parts(**overrides)
    assert _tuple(result) == tuple(map(Decimal, expected))
    assert (result.midterm_max, result.selfwork_active) == (Decimal("20"), True)


def test_barred_and_athlete_are_distinct():
    assert parts(absence_hours=8).attendance_barred
    assert not parts(absence_hours=8, exempt=True).attendance_barred


def test_parts_carry_their_maxima():
    result = parts()
    assert (result.attendance_max, result.activity_max, result.selfwork_max) == (10, 10, 10)
    assert standard.STANDARD_TOTAL == 50


@pytest.mark.parametrize("year, expected", [("2025/2026", False), ("2026/2027", True), ("2027/2028", True)])
def test_mode_boundary(year, expected):
    assert standard.is_midterm_fields(year, None) is expected


def test_organization_override():
    assert not standard.is_midterm_fields("2026/2027", None, from_year_raw=2027)
    assert standard.is_midterm_fields("2025/2026", None, from_year_raw=2025)
