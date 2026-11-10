"""«Cədvəl formasında bax» → «Excel kimi yüklə»: müəllim cədvəlinin .xlsx faylı (sahib 2026-11-11).

İki vərəq: «İcmal» (ekrandakı cədvəl + cəmlər) və «Dərslər» (bütün dərslər təfərrüatı ilə). Hər xana
``core.export_safety`` ilə yazılır (mövzu / qrup adı istifadəçi mətnidir — formula inyeksiyası neytrallaşdırılır).
"""

from __future__ import annotations

import datetime as _dt
from io import BytesIO

from django.utils.translation import pgettext

from core.export_safety import sheet_append

_CTX = "registrar.lessons_log"

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _widths(sheet, widths) -> None:
    from openpyxl.utils import get_column_letter

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _bold(sheet, row_index) -> None:
    from openpyxl.styles import Font

    for cell in sheet[row_index]:
        cell.font = Font(bold=True)


def build_xlsx(*, teacher_name: str, window: dict, table: dict, details: list) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")

    def header(sheet, row_index):
        for cell in sheet[row_index]:
            cell.font, cell.fill = header_font, header_fill

    workbook = Workbook()
    summary = workbook.active
    summary.title = pgettext(_CTX, "İcmal")[:31]
    sheet_append(summary, [pgettext(_CTX, "Müəllim"), teacher_name])
    sheet_append(
        summary,
        [
            pgettext(_CTX, "Dövr"),
            "%s — %s" % (window["start"].strftime("%d.%m.%Y"), window["end"].strftime("%d.%m.%Y")),
        ],
    )
    sheet_append(summary, [])
    sheet_append(
        summary,
        [
            "№",
            pgettext(_CTX, "Qrup"),
            pgettext(_CTX, "Fənn"),
            pgettext(_CTX, "Dərs növü"),
            pgettext(_CTX, "Bölmə"),
            pgettext(_CTX, "Keçilmiş saat"),
            pgettext(_CTX, "Dərs sayı"),
            pgettext(_CTX, "Yekun"),
        ],
    )
    header(summary, summary.max_row)
    summary.freeze_panes = summary.cell(row=summary.max_row + 1, column=1)
    for index, row in enumerate(table["rows"], start=1):
        sheet_append(
            summary,
            [
                index,
                row["groups"],
                row["subject"],
                row["kind_label"],
                row["sector_label"],
                row["hours"],
                row["lessons"],
                row["text"],
            ],
        )
    totals = table["totals"]
    sheet_append(summary, [])
    sheet_append(summary, ["", pgettext(_CTX, "Cəmi"), "", "", "", totals["hours"], totals["lessons"], totals["text"]])
    _bold(summary, summary.max_row)
    for title, items in (
        (pgettext(_CTX, "Dərs növü üzrə"), totals["by_kind"]),
        (pgettext(_CTX, "Bölmə üzrə"), totals["by_sector"]),
    ):
        if not items:
            continue
        sheet_append(summary, [])
        sheet_append(summary, ["", title])
        _bold(summary, summary.max_row)
        for item in items:
            sheet_append(summary, ["", item["label"], "", "", "", item["hours"], item["lessons"], item["text"]])
    _widths(summary, (6, 34, 40, 18, 24, 14, 12, 22))

    lessons = workbook.create_sheet(pgettext(_CTX, "Dərslər")[:31])
    sheet_append(
        lessons,
        [
            "№",
            pgettext(_CTX, "Tarix"),
            pgettext(_CTX, "Həftənin günü"),
            pgettext(_CTX, "Saat"),
            pgettext(_CTX, "Qrup"),
            pgettext(_CTX, "Fənn"),
            pgettext(_CTX, "Dərs növü"),
            pgettext(_CTX, "Akademik saat"),
            pgettext(_CTX, "Mövzu"),
            pgettext(_CTX, "Otaq"),
            pgettext(_CTX, "İştirak"),
            pgettext(_CTX, "Qeyd olunan"),
        ],
    )
    header(lessons, 1)
    lessons.freeze_panes = "A2"
    for index, item in enumerate(details, start=1):
        sheet_append(
            lessons,
            [
                index,
                _dt.date.fromisoformat(item["date"]),
                item["weekday"],
                item["time"],
                item["groups"],
                item["subject"],
                item["kind_label"],
                item["hours"],
                item["topic"],
                item["room"],
                item["present"] if item["marked"] else None,
                item["marked"] if item["marked"] else None,
            ],
        )
        lessons.cell(row=index + 1, column=2).number_format = "DD.MM.YYYY"
    _widths(lessons, (6, 12, 16, 14, 30, 36, 16, 12, 60, 18, 10, 12))

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


__all__ = ["XLSX_CONTENT_TYPE", "build_xlsx"]
