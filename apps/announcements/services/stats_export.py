"""«Elan statistikası» Excel ixracı — iki vərəq: bölgü (cari ölçü) + şəxslər (cari filtrlərlə).

Mətn xanaları ``core.export_safety.sheet_append`` ilə formula-neytrallaşdırılır; əlaqə məlumatı
(telefon, e-poçt, FİN) YOXDUR — yalnız ad, istifadəçi adı, rol, bölmə və vaxtlar.
"""

from __future__ import annotations

import io

from django.utils import timezone
from django.utils.translation import pgettext

from core.export_safety import sheet_append

from ..constants import STATS_EXPORT_LIMIT
from . import stats

_CTX = "announcements.stats"
_HEADER_FILL = "2563EB"
_HEADER_FONT = "FFFFFF"


def _when(value) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else ""


def _dimension_label(dimension) -> str:
    return {
        "faculty": pgettext(_CTX, "Fakültə"),
        "chair": pgettext(_CTX, "Kafedra"),
        "specialty": pgettext(_CTX, "İxtisas"),
        "group": pgettext(_CTX, "Qrup"),
        "role": pgettext(_CTX, "Rol"),
    }.get(dimension, "")


def _breakdown_table(data) -> dict:
    header = [
        _dimension_label(data["dimension"]),
        pgettext(_CTX, "Hədəf"),
        pgettext(_CTX, "Popup görüb"),
        pgettext(_CTX, "Popup görüb, %"),
        pgettext(_CTX, "Oxuyub"),
        pgettext(_CTX, "Oxuyub, %"),
        pgettext(_CTX, "Görməyib"),
        pgettext(_CTX, "Görməyib, %"),
    ]
    rows = [
        [
            item["label"],
            item["total"],
            item["seen"],
            item["seen_pct"],
            item["read"],
            item["read_pct"],
            item["unseen"],
            item["unseen_pct"],
        ]
        for item in [*data["rows"], {**data["totals"], "label": pgettext(_CTX, "Cəmi")}]
    ]
    return {"title": pgettext(_CTX, "Bölgü"), "header": header, "rows": rows}


def _people_table(rows, requires_ack: bool) -> dict:
    header = [
        pgettext(_CTX, "Ad Soyad"),
        pgettext(_CTX, "İstifadəçi adı"),
        pgettext(_CTX, "Rol"),
        pgettext(_CTX, "Bölmə"),
        pgettext(_CTX, "Fakültə"),
        pgettext(_CTX, "Popup görüb"),
        pgettext(_CTX, "Oxuyub"),
    ]
    if requires_ack:
        header.append(pgettext(_CTX, "Təsdiq edib"))
    body = []
    for row in rows:
        line = [
            row["name"],
            row["username"],
            row["family_label"],
            row["unit_label"],
            row["faculty_label"],
            _when(row["ann_seen"]),
            _when(row["ann_read"]),
        ]
        if requires_ack:
            line.append(_when(row["ann_ack"]))
        body.append(line)
    return {"title": pgettext(_CTX, "Şəxslər"), "header": header, "rows": body}


def xlsx_bytes(announcement, *, dimension, family, unit, status, q) -> tuple[bytes, int]:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    data = stats.summary(announcement, dimension=dimension, family=family, unit=unit)
    people = stats.export_rows(announcement, family=family, unit=unit, status=status, q=q, limit=STATS_EXPORT_LIMIT)
    tables = [_breakdown_table(data), _people_table(people, announcement.requires_ack)]
    workbook = Workbook()
    fill = PatternFill("solid", fgColor=_HEADER_FILL)
    font = Font(name="Calibri", color=_HEADER_FONT, bold=True)
    for index, table in enumerate(tables):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = str(table["title"])[:31]
        sheet_append(sheet, table["header"])
        for cell in sheet[1]:
            cell.fill, cell.font = fill, font
        for row in table["rows"]:
            sheet_append(sheet, row)
        sheet.freeze_panes = "A2"
        for column, header in enumerate(table["header"], start=1):
            sample = [header, *(row[column - 1] for row in table["rows"][:300])]
            width = min(max(len(str(value or "")) for value in sample) + 2, 48)
            sheet.column_dimensions[get_column_letter(column)].width = max(width, 8)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), len(people)


__all__ = ["xlsx_bytes"]
