"""«Mühasibatlıq» — Excel ixracı (panelin cari filtr dəsti üzrə).

Dövr panelin dövrüdür: ay, bütün semestr və ya sərbəst tarix aralığı (``ac_from`` / ``ac_to`` — plan aylıq payların
iş günlərinə görə kəsilməsidir, bax ``ranges.py``); başlıqda dövr yazılır.

Vərəqlər:

1. «Müəllimlər» — süzülmüş BÜTÜN müəllimlər (drill-down / modal ixracında yalnız həmin müəllim) (səhifələmə yoxdur): fakültə, kafedra, ştat, dövrün planı,
   fakt (mühazirə / seminar / lab / cəm), fərq, icra %, status, semestr planı və semestr faktı;
2. «Fənn və qrup» — həmin müəllimlərin fənn × qrup × növ üzrə keçirilmiş saatı (1 GROUP BY);
3. «Dərslər» — YALNIZ drill-down açıqdırsa (``ac_teacher``): həmin müəllimin dərs siyahısı;
4. «Dərəcələr» — ixrac anında qüvvədə olan ödəniş dərəcələri (id ilə — sətir silinmir, sonradan da oxunur).

2026-10-19 (sahib, tövsiyə olunan variant): «Müəllimlər» vərəqində vəzifə, növlər üzrə məbləğ və «Məbləğ (AZN)» =
keçirilmiş saat × dərəcə (``rates.py``). Dərəcə yoxdursa məbləğ BOŞ qalır və «Dərəcə təyin edilməyib» yazılır (0 yox).
Saathesabı hissə PLAN üzrə ayrıca sütundadır. Başlıq: «İlkin hesablama — rəsmi əmək haqqı hesabı deyil».

Hücrələr ``core.export_safety.sheet_append`` ilə yazılır (formula injection neytrallaşdırılır).
"""

from __future__ import annotations

import io

from django.utils.translation import pgettext

from core.export_safety import sheet_append
from core.ui import status_catalog

from ..hr_analytics.constants import STAFF_TYPES
from . import constants as C
from . import dataset, rates
from .detail import lesson_list, period_bounds, period_label
from .formatting import staff_short
from .rates_view import disclaimer, rate_card

_HEADER_FILL = "1F3A5F"
_HEADER_FONT = "FFFFFF"


def _kind_headers() -> list[str]:
    return [str(label) for _key, label in C.KINDS]


def _status_label(key: str) -> str:
    return str(status_catalog.label(C.STATUS_FAMILY, key))


def _period(resolved) -> str:
    return period_label(resolved.filters, resolved.semester)


def _teachers_table(resolved, rows) -> dict:
    staff_labels = {key: str(label) for key, label in STAFF_TYPES}
    header = [
        pgettext(C.CTX, "Müəllim"),
        pgettext(C.CTX, "İstifadəçi adı"),
        pgettext(C.CTX, "Fakültə"),
        pgettext(C.CTX, "Kafedra"),
        pgettext(C.CTX, "Ştat"),
        pgettext(C.CTX, "Ştat növü"),
        pgettext(C.CTX, "Vəzifə"),
        pgettext(C.CTX, "Plan (saat)"),
        *(f"{label} ({pgettext(C.CTX, 'fakt')})" for label in _kind_headers()),
        pgettext(C.CTX, "Fakt (saat)"),
        pgettext(C.CTX, "Dərs sayı"),
        pgettext(C.CTX, "Fərq (saat)"),
        pgettext(C.CTX, "İcra, %"),
        pgettext(C.CTX, "Status"),
        pgettext(C.CTX, "Semestr planı"),
        pgettext(C.CTX, "Semestr faktı"),
        pgettext(C.CTX, "Saathesabı plan (semestr, saat)"),
        *(f"{label} ({pgettext(C.CTX, 'məbləğ, AZN')})" for label in _kind_headers()),
        pgettext(C.CTX, "Məbləğ (AZN)"),
        pgettext(C.CTX, "Məbləğ qeydi"),
    ]
    body = [
        [
            row["name"],
            row["username"],
            row["faculty"],
            row["chair"],
            staff_short(row),
            staff_labels.get(row["staff_type"], ""),
            row.get("position") or "",
            row["planned"],
            *(row["kinds"][kind] for kind in C.KIND_KEYS),
            row["held"],
            row["lessons"],
            row["diff"],
            "" if row["pct"] is None else row["pct"],
            _status_label(row["status"]),
            row["planned_sem"],
            row["held_sem"],
            row.get("planned_hourly_sem", 0),
            *(row["pay"]["kinds"][kind]["amount"] for kind in C.KIND_KEYS),
            row["pay"]["amount"],
            row["pay"]["hourly_note"] if row["pay"]["amount"] is not None else rates.missing_text(row["pay"]),
        ]
        for row in rows
    ]
    return {"title": pgettext(C.CTX, "Müəllimlər"), "header": header, "rows": body}


def _breakdown_table(resolved, rows) -> dict:
    names = {row["id"]: row["name"] for row in rows}
    start, end = period_bounds(resolved.filters)
    items = dataset.subject_breakdown(resolved.actor.organization, resolved.semester, list(names), start=start, end=end)
    kinds = {key: str(label) for key, label in C.KINDS}
    body = [
        [
            names.get(item["teacher"], ""),
            item["offering__subject__name"] or "",
            item["offering__group__name"] or "",
            kinds.get(item["kind"], item["kind"]),
            int(item["lessons"] or 0),
            int(item["hours"] or 0),
        ]
        for item in sorted(items, key=lambda item: (names.get(item["teacher"], "").casefold(), str(item)))
    ]
    header = [
        pgettext(C.CTX, "Müəllim"),
        pgettext(C.CTX, "Fənn"),
        pgettext(C.CTX, "Qrup"),
        pgettext(C.CTX, "Növ"),
        pgettext(C.CTX, "Dərs sayı"),
        pgettext(C.CTX, "Saat"),
    ]
    return {"title": pgettext(C.CTX, "Fənn və qrup"), "header": header, "rows": body}


def _lessons_table(resolved) -> dict:
    items = lesson_list(resolved, int(resolved.filters.teacher), limit=C.EXPORT_LESSON_LIMIT)
    header = [
        pgettext(C.CTX, "Tarix"),
        pgettext(C.CTX, "Vaxt"),
        pgettext(C.CTX, "Qrup"),
        pgettext(C.CTX, "Fənn"),
        pgettext(C.CTX, "Növ"),
        pgettext(C.CTX, "Akademik saat"),
    ]
    body = [
        [
            item["date"].strftime("%d.%m.%Y"),
            item["time"].strftime("%H:%M") if item["time"] else "",
            item["group"],
            item["subject"],
            item["kind_label"],
            item["hours"],
        ]
        for item in items
    ]
    return {"title": pgettext(C.CTX, "Dərslər"), "header": header, "rows": body}


def _rates_table(resolved) -> dict:
    card = rate_card(resolved, with_manage=False)
    header = [
        pgettext(C.CTX, "Tədris ili"),
        pgettext(C.CTX, "Vəzifə"),
        pgettext(C.CTX, "Növ"),
        pgettext(C.CTX, "Dərəcə (AZN / saat)"),
        pgettext(C.CTX, "Qeyd"),
        pgettext(C.CTX, "Əlavə edib"),
        pgettext(C.CTX, "Tarix"),
        pgettext(C.CTX, "Dərəcə id"),
    ]
    body = [
        [
            card["year"],
            item["position_label"],
            item["kind_label"],
            item["rate"],
            item["note"],
            item["created_by_name"],
            item["created_at"].strftime("%d.%m.%Y %H:%M") if item["created_at"] else "",
            item["id"],
        ]
        for item in card["active"]
    ]
    return {"title": pgettext(C.CTX, "Dərəcələr"), "header": header, "rows": body}


def used_rate_ids(resolved) -> list[str]:
    """İxracda istifadə olunan aktiv dərəcələrin id-ləri (audit üçün)."""
    return sorted(str(row.pk) for row in (resolved.rate_map or {}).values())


def build_tables(resolved, rows) -> list[dict]:
    tables = [_teachers_table(resolved, rows), _breakdown_table(resolved, rows)]
    # Əhatə: ``persons`` yalnız aktorun görə bildiyi müəllimlərdir — başqa id-nin dərsləri heç vaxt çıxmır.
    if resolved.filters.teacher and int(resolved.filters.teacher) in resolved.persons:
        tables.append(_lessons_table(resolved))
    tables.append(_rates_table(resolved))
    return tables


def xlsx_bytes(tables, *, caption: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    fill = PatternFill("solid", fgColor=_HEADER_FILL)
    font = Font(name="Calibri", color=_HEADER_FONT, bold=True)
    for index, table in enumerate(tables):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = str(table["title"])[:31]
        sheet_append(sheet, [caption])
        sheet_append(sheet, table["header"])
        for cell in sheet[2]:
            cell.fill, cell.font = fill, font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for row in table["rows"]:
            sheet_append(sheet, ["" if value is None else value for value in row])
        sheet.freeze_panes = "A3"
        for column, header in enumerate(table["header"], start=1):
            values = [header, *(row[column - 1] for row in table["rows"][:300] if column - 1 < len(row))]
            width = min(max(len(str(value or "")) for value in values) + 2, 48)
            sheet.column_dimensions[get_column_letter(column)].width = max(width, 6)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_caption(resolved) -> str:
    caption = pgettext(C.CTX, "Mühasibatlıq · %(period)s · keçirilmiş dərs saatı və plan") % {
        "period": _period(resolved)
    }
    return f"{caption} · {disclaimer()}"


__all__ = ["build_tables", "export_caption", "used_rate_ids", "xlsx_bytes"]
