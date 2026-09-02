"""İş günü hesabı — həftə sonu atlanır, banner tonu düzgün seçilir."""

from __future__ import annotations

from datetime import date

from apps.applications.sla import add_working_days, is_working_day, sla_banner, working_days_between

# 2026-09-02 çərşənbədir; 2026-09-05 şənbə, 2026-09-06 bazar günüdür.
WEDNESDAY = date(2026, 9, 2)
FRIDAY = date(2026, 9, 4)
SATURDAY = date(2026, 9, 5)
MONDAY = date(2026, 9, 7)


def test_weekend_is_not_a_working_day():
    assert is_working_day(FRIDAY)
    assert not is_working_day(SATURDAY)
    assert not is_working_day(date(2026, 9, 6))
    assert is_working_day(MONDAY)


def test_three_working_days_from_wednesday_lands_on_monday():
    assert add_working_days(WEDNESDAY, 3) == MONDAY


def test_two_working_days_from_wednesday_stay_in_the_week():
    assert add_working_days(WEDNESDAY, 2) == FRIDAY


def test_zero_or_negative_days_return_the_start():
    assert add_working_days(WEDNESDAY, 0) == WEDNESDAY
    assert add_working_days(WEDNESDAY, -3) == WEDNESDAY


def test_ten_working_days_skip_two_weekends():
    assert add_working_days(WEDNESDAY, 10) == date(2026, 9, 16)


def test_working_days_between_skips_the_weekend():
    assert working_days_between(WEDNESDAY, MONDAY) == 3
    assert working_days_between(FRIDAY, MONDAY) == 1
    assert working_days_between(WEDNESDAY, WEDNESDAY) == 0


def test_working_days_between_is_signed():
    assert working_days_between(MONDAY, WEDNESDAY) == -3


def test_holidays_are_excluded_when_supplied():
    assert add_working_days(WEDNESDAY, 1, holidays={date(2026, 9, 3)}) == FRIDAY


def test_banner_reports_remaining_days_when_on_time():
    banner = sla_banner(due_on=MONDAY, sla_days=3, today=WEDNESDAY, is_open=True, status_label="Baxılır")
    assert banner["tone"] == "ontime"
    assert banner["days"] == 3


def test_banner_reports_overdue_days():
    banner = sla_banner(due_on=WEDNESDAY, sla_days=3, today=MONDAY, is_open=True, status_label="Baxılır")
    assert banner["tone"] == "overdue"
    assert banner["days"] == 3


def test_closed_application_gets_the_closed_tone():
    banner = sla_banner(due_on=WEDNESDAY, sla_days=3, today=MONDAY, is_open=False, status_label="Həll olunub")
    assert banner["tone"] == "closed"
    assert banner["status_label"] == "Həll olunub"
