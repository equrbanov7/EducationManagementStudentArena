"""«Mühasibatlıq» — müəllim sətirlərinin hesabı (plan ↔ fakt), filtr və sıralama (yaddaşda, sorğusuz)."""

from __future__ import annotations

from core.search_text import tolerant_match

from . import constants as C
from .periods import apportion
from .ranges import range_plan_kinds


def plan_status(planned: float, held: float) -> str:
    """Plan ↔ fakt statusu: ±band («Sistem tənzimləmələri» → ``accounting.deviation_percent``) «plana uyğun»dur."""
    if planned <= 0:
        return C.STATUS_NO_PLAN if held > 0 else C.STATUS_IDLE
    ratio = held / planned
    tolerance = C.deviation_tolerance()
    if ratio < 1 - tolerance:
        return C.STATUS_UNDER
    if ratio > 1 + tolerance:
        return C.STATUS_OVER
    return C.STATUS_ON_PLAN


def _pct(planned: float, held: float):
    return int(round(held * 100 / planned)) if planned > 0 else None


def _round(value: float) -> float:
    return round(value + 0.0, 1)


def teacher_months(planned_kinds: dict, held_months: dict, month_keys, day_counts) -> dict:
    """Ay → {planned, planned_kinds, held, kinds, lessons} (plan hər növ üçün ayrıca bölünür, cəm dəqiqdir)."""
    shares = {kind: apportion(hours, day_counts) for kind, hours in planned_kinds.items() if hours}
    out = {}
    for key in month_keys:
        cell = held_months.get(key, {})
        planned_kinds_month = {kind: shares[kind].get(key, 0.0) for kind in shares}
        out[key] = {
            "planned": _round(sum(planned_kinds_month.values())),
            "planned_kinds": planned_kinds_month,
            "kinds": {kind: cell.get(kind, [0, 0])[0] for kind in C.KIND_KEYS},
            "held": sum(value[0] for value in cell.values()),
            "lessons": sum(value[1] for value in cell.values()),
        }
    return out


def _range_cell(planned_kinds: dict, range_months: dict, day_counts, range_counts) -> dict:
    """Aralıq rejimi: plan — aylıq payların iş günlərinə görə kəsilməsi (``ranges.py``), fakt — aralığın dərsləri."""
    kinds = dict.fromkeys(C.KIND_KEYS, 0)
    lessons = 0
    for cell in range_months.values():
        for kind, (hours, count) in cell.items():
            if kind in kinds:
                kinds[kind] += hours
            lessons += count
    plan_kinds = range_plan_kinds(planned_kinds, day_counts, range_counts)
    return {
        "planned": _round(sum(plan_kinds.values())),
        "planned_kinds": plan_kinds,
        "kinds": kinds,
        "lessons": lessons,
    }


def build_rows(
    persons: dict,
    held: dict,
    planned: dict,
    *,
    month_keys,
    day_counts,
    month: str,
    range_held: dict | None = None,
    range_counts: dict | None = None,
) -> list[dict]:
    """Hər müəllim üçün bir sətir; ``month`` — seçilmiş ay («YYYY-MM»), ``"all"`` (bütün semestr) və ya
    ``"range"`` (sərbəst aralıq: ``range_held`` — aralığın fakt matrisi, ``range_counts`` — aralığın iş günləri)."""
    rows = []
    for teacher_id, person in persons.items():
        held_months = held.get(teacher_id, {})
        planned_kinds = {kind: int(planned.get(teacher_id, {}).get(kind, 0)) for kind in C.KIND_KEYS}
        hourly_kinds = planned.get(teacher_id, {}).get(C.HOURLY_KEY, {})
        months = teacher_months(planned_kinds, held_months, month_keys, day_counts)
        held_sem_kinds = {kind: 0 for kind in C.KIND_KEYS}
        lessons_sem = 0
        for cell in held_months.values():  # semestr cəmi: siyahıdan kənar tarixli dərslər də daxil
            for kind, (hours, lessons) in cell.items():
                if kind in held_sem_kinds:
                    held_sem_kinds[kind] += hours
                lessons_sem += lessons
        planned_sem = sum(planned_kinds.values())
        held_sem = sum(held_sem_kinds.values())
        if month == "all":
            planned_now, kinds_now, lessons_now = float(planned_sem), held_sem_kinds, lessons_sem
            plan_kinds_now = {kind: float(hours) for kind, hours in planned_kinds.items()}
        elif month == "range":
            cell = _range_cell(planned_kinds, (range_held or {}).get(teacher_id, {}), day_counts, range_counts or {})
            planned_now, kinds_now, lessons_now = cell["planned"], cell["kinds"], cell["lessons"]
            plan_kinds_now = cell["planned_kinds"]
        else:
            cell = months.get(month) or {
                "planned": 0.0,
                "planned_kinds": {},
                "kinds": dict.fromkeys(C.KIND_KEYS, 0),
                "lessons": 0,
            }
            planned_now, kinds_now, lessons_now = cell["planned"], cell["kinds"], cell["lessons"]
            plan_kinds_now = {kind: round(cell["planned_kinds"].get(kind, 0.0), 1) for kind in C.KIND_KEYS}
        held_now = sum(kinds_now.values())
        rows.append(
            {
                **person,
                "planned_sem": planned_sem,
                "planned_sem_kinds": planned_kinds,
                #: Semestr planının saathesabı hissəsi (``TeacherAssignment.is_hourly_paid``) — ödəniş etiketi üçün.
                "planned_hourly_sem": sum(int(hourly_kinds.get(kind, 0) or 0) for kind in C.KIND_KEYS),
                "held_sem": held_sem,
                "held_sem_kinds": held_sem_kinds,
                "lessons_sem": lessons_sem,
                "months": months,
                "planned": _round(planned_now),
                "planned_kinds": plan_kinds_now,
                "kinds": kinds_now,
                "held": held_now,
                "lessons": lessons_now,
                "diff": _round(held_now - planned_now),
                "pct": _pct(planned_now, held_now),
                "status": plan_status(planned_now, held_now),
            }
        )
    return rows


def apply_filters(rows, filters) -> list[dict]:
    out = []
    for row in rows:
        if filters.faculty and row["faculty_id"] != filters.faculty:
            continue
        if filters.chair and row["chair_id"] != filters.chair:
            continue
        if filters.deviation and row["status"] not in C.DEVIATION_STATUSES:
            continue
        if filters.q and not tolerant_match(filters.q, row["name"], row["username"], row["chair"]):
            continue
        out.append(row)
    return out


def sort_rows(rows, filters) -> list[dict]:
    key = filters.sort.lstrip("-")
    reverse = filters.sort.startswith("-")

    def by(row):
        name = row["name"].casefold()
        if key == "pct":
            return (row["pct"] is None, row["pct"] or 0, name)
        if key in ("planned", "held", "diff"):
            return (row[key], name)
        return (name,)

    ordered = sorted(rows, key=by, reverse=reverse)
    if key == "pct" and reverse:  # planı olmayanlar həmişə sonda
        ordered = [row for row in ordered if row["pct"] is not None] + [row for row in ordered if row["pct"] is None]
    return ordered


def totals(rows) -> dict:
    planned = _round(sum(row["planned"] for row in rows))
    held = sum(row["held"] for row in rows)
    kinds = {kind: sum(row["kinds"][kind] for row in rows) for kind in C.KIND_KEYS}
    return {
        "planned": planned,
        "held": held,
        "kinds": kinds,
        "diff": _round(held - planned),
        "pct": _pct(planned, held),
        "over": sum(1 for row in rows if row["status"] == C.STATUS_OVER),
        "under": sum(1 for row in rows if row["status"] == C.STATUS_UNDER),
        "no_plan": sum(1 for row in rows if row["status"] == C.STATUS_NO_PLAN),
        "teachers": len(rows),
    }


__all__ = ["apply_filters", "build_rows", "plan_status", "sort_rows", "teacher_months", "totals"]
