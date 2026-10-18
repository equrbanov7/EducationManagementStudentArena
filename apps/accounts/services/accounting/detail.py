"""«Mühasibatlıq» — bir müəllimin drill-down görünüşü (yalnız oxu).

* aylıq cədvəl: hər ay üçün plan (növlər üzrə bölünmüş pay), fakt (mühazirə / seminar / lab), fərq, status;
* fənn × qrup bölgüsü: seçilmiş dövrün (ay və ya bütün semestr) keçirilmiş saatı növlər üzrə — 1 sorğu;
* keçirilmiş dərslərin siyahısı: tarix, qrup, fənn, növ, saat — səhifələnir (say + dilim, 2 sorğu).

Müəllim yalnız aktorun əhatəsindədirsə açılır (``Resolved.persons`` — əhatə süzgəcindən keçmiş dəst); başqa id
«tapılmadı» boş vəziyyəti verir (mövcudluq sızdırılmır). Tələbə adı / qiyməti YOXDUR.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.utils.translation import pgettext

from core.ui import status_catalog

from . import constants as C
from . import dataset
from .filters import MONTH_ALL
from .formatting import fmt_hours, kind_cells, staff_short
from .periods import month_bounds, month_label, months
from .rows import plan_status


def _month_rows(row: dict) -> list[dict]:
    out = []
    for key, cell in row["months"].items():
        diff = round(cell["held"] - cell["planned"], 1)
        out.append(
            {
                "key": key,
                "label": month_label(key),
                "planned_text": fmt_hours(cell["planned"]),
                "kind_cells": kind_cells(cell["kinds"]),
                "held_text": fmt_hours(cell["held"]),
                "lessons": cell["lessons"],
                "diff_text": fmt_hours(diff, signed=True),
                "status_obj": status_catalog.get(C.STATUS_FAMILY, plan_status(cell["planned"], cell["held"])),
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


def period_bounds(filters):
    """(ilk gün, son gün) seçilmiş ay üçün; bütün semestr — (None, None)."""
    return (None, None) if filters.month == MONTH_ALL else month_bounds(filters.month)


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


def teacher_detail(resolved, *, base: str, url) -> dict:
    filters = resolved.filters
    teacher_id = int(filters.teacher)
    row = next((item for item in resolved.rows if item["id"] == teacher_id), None)
    if row is None:
        return {"found": False}
    start, end = period_bounds(filters)
    organization = resolved.actor.organization
    breakdown = _breakdown(
        dataset.subject_breakdown(organization, resolved.semester, [teacher_id], start=start, end=end)
    )
    lessons = lesson_list(resolved, teacher_id, page_number=filters.lpage)
    page, paginator = lessons["page"], lessons["paginator"]
    return {
        "found": True,
        "row": row,
        "name": row["name"],
        "chair": row["chair"],
        "faculty": row["faculty"],
        "staff_short": staff_short(row),
        "planned_sem_text": fmt_hours(row["planned_sem"]),
        "held_sem_text": fmt_hours(row["held_sem"]),
        "planned_sem_cells": kind_cells(row["planned_sem_kinds"]),
        "held_sem_cells": kind_cells(row["held_sem_kinds"]),
        "diff_sem_text": fmt_hours(row["held_sem"] - row["planned_sem"], signed=True),
        "months": _month_rows(row),
        "month_count": len(months(resolved.semester)),
        "breakdown": breakdown,
        "lessons": lessons["items"],
        "lessons_total": paginator.count,
        "lesson_page": page.number,
        "lesson_pages": paginator.num_pages,
        "lesson_prev_url": url(base, filters, lpage=page.number - 1) if page.has_previous() else "",
        "lesson_next_url": url(base, filters, lpage=page.number + 1) if page.has_next() else "",
        "back_label": pgettext(C.CTX, "Bütün müəllimlər"),
    }


__all__ = ["lesson_list", "period_bounds", "teacher_detail"]
