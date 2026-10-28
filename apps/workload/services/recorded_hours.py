"""Separate recorded work from the official allocation; never change assignment totals."""

from types import SimpleNamespace

from apps.registrar.public import recorded_teaching_hours

from .plan_calendar import season_from_period


def teacher_recorded_hours(actor, *, academic_year="", season=""):
    rows = recorded_teaching_hours(actor=actor)
    years = sorted({row["academic_year"] for row in rows}, reverse=True)
    if academic_year:
        rows = [row for row in rows if row["academic_year"] == academic_year]
    if season:
        rows = [row for row in rows if season_from_period(SimpleNamespace(start_date=row["period_start"])) == season]
    for row in rows:
        for kind in ("lecture", "seminar", "lab"):
            row[kind + "_hours"] = row["hours"].get(kind, 0)
    return {
        "rows": rows,
        "years": years,
        "total_hours": sum(row["total_hours"] for row in rows),
        "unknown_hours": sum(row["unknown_hours"] for row in rows),
    }
