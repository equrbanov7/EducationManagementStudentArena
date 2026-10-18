"""«Mühasibatlıq» — bir müəllimin ətraflı görünüşü (yalnız oxu): səhifə drill-down-u və müəllim pəncərəsi (modal).

* növlər üzrə: seçilmiş dövrün planı ↔ faktı (mühazirə / seminar / laboratoriya), fərq, icra, status;
* aylıq cədvəl: ay / bütün semestr rejimində semestrin bütün ayları (seçilmiş ay işarələnir); aralıq rejimində
  YALNIZ aralığın ayları — qismən düşən ayın planı iş günlərinə görə kəsilir (``ranges.py``), faktı aralığın dərsləri;
* fənn × qrup bölgüsü: seçilmiş dövrün keçirilmiş saatı növlər üzrə — 1 sorğu;
* keçirilmiş dərslərin siyahısı: tarix, qrup, fənn, növ, saat — səhifələnir (say + dilim, 2 sorğu).

Müəllim yalnız aktorun əhatəsindədirsə açılır (``Resolved.rows`` — əhatə süzgəcindən keçmiş dəst); başqa id
«tapılmadı» verir (mövcudluq sızdırılmır). Tələbə adı / qiyməti YOXDUR — yalnız fənn, qrup adı və saatlar.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.utils.translation import pgettext

from core.ui import status_catalog

from ..hr_analytics.constants import STAFF_TYPES
from . import constants as C
from . import dataset
from .filters import MONTH_ALL
from .formatting import fmt_hours, kind_cells, staff_short
from .periods import month_bounds, month_label, months
from .ranges import fmt_date, month_parts, month_slice, range_label, range_months
from .rows import plan_status


def period_bounds(filters):
    """(ilk gün, son gün) seçilmiş ay / aralıq üçün; bütün semestr — (None, None)."""
    if filters.is_range:
        return filters.range_dates
    return (None, None) if filters.month == MONTH_ALL else month_bounds(filters.month)


def period_label(filters, semester) -> str:
    if filters.is_range:
        return range_label(*filters.range_dates)
    if filters.month == MONTH_ALL:
        return semester.label
    return month_label(filters.month)


def _status(planned, held):
    return status_catalog.get(C.STATUS_FAMILY, plan_status(planned, held))


def _month_row(key, label, planned, kinds, lessons, *, current=False, partial="") -> dict:
    held = sum(kinds.values())
    return {
        "key": key,
        "label": label,
        "partial": partial,
        "is_current": current,
        "planned_text": fmt_hours(planned),
        "kind_cells": kind_cells(kinds),
        "held_text": fmt_hours(held),
        "lessons": lessons,
        "diff_text": fmt_hours(round(held - planned, 1), signed=True),
        "status_obj": _status(planned, held),
    }


def _semester_months(row: dict, filters) -> list[dict]:
    return [
        _month_row(
            key,
            month_label(key),
            cell["planned"],
            cell["kinds"],
            cell["lessons"],
            current=key == filters.month,
        )
        for key, cell in row["months"].items()
    ]


def _range_month_rows(resolved, row: dict) -> list[dict]:
    """Aralığın ayları: plan — aylıq payın aralığa düşən iş günləri qədəri, fakt — aralığın dərsləri."""
    start, end = resolved.filters.range_dates
    day_counts, range_counts = resolved.day_counts or {}, resolved.range_counts or {}
    parts = {kind: month_parts(hours, day_counts, range_counts) for kind, hours in row["planned_sem_kinds"].items()}
    held = (resolved.range_held or {}).get(row["id"], {})
    out = []
    for key in range_months(start, end):
        cell = held.get(key, {})
        kinds = {kind: cell.get(kind, [0, 0])[0] for kind in C.KIND_KEYS}
        lessons = sum(value[1] for value in cell.values())
        planned = round(sum(part.get(key, 0.0) for part in parts.values()), 1)
        lo, hi, partial = month_slice(key, start, end)
        note = f"{fmt_date(lo)[:5]}–{fmt_date(hi)[:5]}" if partial else ""
        out.append(_month_row(key, month_label(key), planned, kinds, lessons, partial=note))
    return out


def kind_rows(row: dict) -> list[dict]:
    """Növlər üzrə dövrün planı ↔ faktı + «Cəmi» sətri."""
    out = []
    for key, label in C.KINDS:
        planned = float(row["planned_kinds"].get(key, 0) or 0)
        held = row["kinds"].get(key, 0)
        out.append(
            {
                "label": str(label),
                "planned_text": fmt_hours(planned),
                "held_text": fmt_hours(held),
                "diff_text": fmt_hours(round(held - planned, 1), signed=True),
                "pct": int(round(held * 100 / planned)) if planned > 0 else None,
                "status_obj": _status(planned, held),
            }
        )
    return out


def _breakdown(rows: list[dict]) -> list[dict]:
    grouped: dict = {}
    for item in rows:
        key = (item["offering__subject__name"] or "—", item["offering__group__name"] or "—")
        entry = grouped.setdefault(key, {"subject": key[0], "group": key[1], "kinds": {}, "lessons": 0})
        entry["kinds"][item["kind"]] = entry["kinds"].get(item["kind"], 0) + int(item["hours"] or 0)
        entry["lessons"] += int(item["lessons"] or 0)
    out = []
    for entry in grouped.values():
        out.append(
            {
                **entry,
                "kind_cells": kind_cells(entry["kinds"]),
                "total_text": fmt_hours(sum(entry["kinds"].values())),
            }
        )
    return out


def lesson_list(resolved, teacher_id, *, limit=None, page_number=1):
    """Keçirilmiş dərslər (səhifə və ya ixrac üçün tavanlı siyahı)."""
    start, end = period_bounds(resolved.filters)
    queryset = dataset.lesson_rows(resolved.actor.organization, resolved.semester, teacher_id, start=start, end=end)
    kinds = {key: str(label) for key, label in C.KINDS}

    def shape(item):
        return {
            "date": item["date"],
            "time": item["start_time"],
            "group": item["offering__group__name"] or "—",
            "subject": item["offering__subject__name"] or "—",
            "kind": item["kind"],
            "kind_label": kinds.get(item["kind"], item["kind"]),
            "hours": int(item["hours"] or 0),
            "topic": item["topic"] or "",
        }

    if limit is not None:
        return [shape(item) for item in queryset[:limit]]
    paginator = Paginator(queryset, C.LESSON_PAGE_SIZE)
    page = paginator.get_page(page_number)
    return {"items": [shape(item) for item in page.object_list], "page": page, "paginator": paginator}


def find_row(resolved, teacher_id: int):
    """Əhatədəki müəllimin sətri və ya ``None`` (``Resolved.rows`` artıq əhatə süzgəcindən keçib)."""
    return next((item for item in resolved.rows if item["id"] == teacher_id), None)


def detail_core(resolved, row: dict) -> dict:
    """Səhifə drill-down-u və modal üçün ortaq kontekst (lesson səhifəsi istisna) — 1 sorğu (fənn × qrup)."""
    filters = resolved.filters
    start, end = period_bounds(filters)
    breakdown = _breakdown(
        dataset.subject_breakdown(resolved.actor.organization, resolved.semester, [row["id"]], start=start, end=end)
    )
    return {
        "found": True,
        "row": row,
        "name": row["name"],
        "chair": row["chair"],
        "faculty": row["faculty"],
        "position": row.get("position") or "",
        "staff_short": staff_short(row),
        "staff_label": str(dict(STAFF_TYPES).get(row["staff_type"], "")),
        "period_label": period_label(filters, resolved.semester),
        "semester_label": resolved.semester.label,
        "is_range": filters.is_range,
        "planned_text": fmt_hours(row["planned"]),
        "held_text": fmt_hours(row["held"]),
        "diff_text": fmt_hours(row["diff"], signed=True),
        "pct": row["pct"],
        "status_obj": _status(row["planned"], row["held"]),
        "lessons_count": row["lessons"],
        "kind_rows": kind_rows(row),
        "planned_sem_text": fmt_hours(row["planned_sem"]),
        "held_sem_text": fmt_hours(row["held_sem"]),
        "planned_sem_cells": kind_cells(row["planned_sem_kinds"]),
        "held_sem_cells": kind_cells(row["held_sem_kinds"]),
        "diff_sem_text": fmt_hours(row["held_sem"] - row["planned_sem"], signed=True),
        "months": _range_month_rows(resolved, row) if filters.is_range else _semester_months(row, filters),
        "month_count": len(months(resolved.semester)),
        "breakdown": breakdown,
    }


def teacher_detail(resolved, *, base: str, url) -> dict:
    """Səhifə drill-down-u (``ac_teacher``) — dərslər «Əvvəlki / Növbəti» ilə səhifələnir."""
    filters = resolved.filters
    row = find_row(resolved, int(filters.teacher))
    if row is None:
        return {"found": False}
    lessons = lesson_list(resolved, row["id"], page_number=filters.lpage)
    page, paginator = lessons["page"], lessons["paginator"]
    return {
        **detail_core(resolved, row),
        "lessons": lessons["items"],
        "lessons_total": paginator.count,
        "lesson_page": page.number,
        "lesson_pages": paginator.num_pages,
        "lesson_prev_url": url(base, filters, lpage=page.number - 1) if page.has_previous() else "",
        "lesson_next_url": url(base, filters, lpage=page.number + 1) if page.has_next() else "",
        "back_label": pgettext(C.CTX, "Bütün müəllimlər"),
    }


__all__ = ["detail_core", "find_row", "kind_rows", "lesson_list", "period_bounds", "period_label", "teacher_detail"]
