"""CSV/XLSX ixraclarında formula neytrallaşdırması (shared kernel).

2026-09-13 təhlükəsizlik auditi, F-07 (P3): heç bir ixrac yazıcısında
``=`` / ``+`` / ``-`` / ``@`` prefiks qorunması yox idi; ``openpyxl`` isə
``"=…"`` sətrini FORMULA (``data_type='f'``) kimi yazır. İstifadəçi mətnli
sütunlar (audit ``reason``, ad/soyad, qrup adı, sual mətni) Excel/LibreOffice-də
açılanda ``=HYPERLINK(...)`` / ``=cmd|...`` kimi ifadələr icra oluna bilər
(CSV injection, OWASP «CSV Injection»).

Bu modul TƏK helper-dir — hər ixrac yazıcısı bunu istifadə edir ki, qayda bir
yerdə dəyişsin. Neytrallaşdırma OWASP tövsiyəsi ilə eynidir: ``= + - @`` və
``\\t`` / ``\\r`` / ``\\n`` ilə başlayan (baş boşluqlar nəzərə alınmadan)
STRING dəyərlərin qabağına tək dırnaq (``'``) qoyulur; ədədlər, tarixlər,
``None`` OLDUĞU KİMİ qalır — cədvəl tipləri (rəqəm sütunları, cəm düsturları)
pozulmur.

``apps/registrar/exam_score_import_safety.export_text`` bu helper-ə həvalə
olunur (idxal şablonu üçün geriyə-uyğun ``str`` imzası saxlanılır).
"""

from __future__ import annotations

import csv
from typing import Any, Iterable

#: Cədvəl proqramlarının formula kimi şərh etdiyi ilk simvollar.
FORMULA_TRIGGERS: tuple[str, ...] = ("=", "+", "-", "@")

#: Sətir başında icra siqnalı verə bilən nəzarət simvolları.
CONTROL_TRIGGERS: tuple[str, ...] = ("\t", "\r", "\n")

#: Neytrallaşdırma prefiksi — Excel/LibreOffice tək dırnaqla başlayan xananı
#: hərfi mətn kimi göstərir.
NEUTRAL_PREFIX = "'"


def is_formula_like(value: Any) -> bool:
    """*value* cədvəl proqramında formula kimi şərh oluna bilərmi (yalnız ``str``)."""
    if not isinstance(value, str) or not value:
        return False
    if value.startswith(CONTROL_TRIGGERS):
        return True
    return value.lstrip().startswith(FORMULA_TRIGGERS)


def neutralise_cell(value: Any) -> Any:
    """Formula-bənzər ``str`` dəyərə ``'`` prefiksi qoy; qalan tipləri dəyişmə."""
    if is_formula_like(value):
        return NEUTRAL_PREFIX + value
    return value


def neutralise_row(row: Iterable[Any]) -> list:
    """Sətirdəki hər xananı :func:`neutralise_cell`-dən keçir."""
    return [neutralise_cell(value) for value in row]


class SafeCsvWriter:
    """``csv.writer`` sarğısı — ``writerow``/``writerows`` xanaları neytrallaşdırır.

    Eyni interfeysi saxlayır ki, mövcud ``writer = csv.writer(...)`` sətri
    :func:`safe_csv_writer` ilə bir-bir əvəzlənsin.
    """

    __slots__ = ("_writer",)

    def __init__(self, writer):
        self._writer = writer

    def writerow(self, row: Iterable[Any]):
        return self._writer.writerow(neutralise_row(row))

    def writerows(self, rows: Iterable[Iterable[Any]]) -> None:
        for row in rows:
            self.writerow(row)

    @property
    def dialect(self):
        return self._writer.dialect


def safe_csv_writer(fileobj, *args, **kwargs) -> SafeCsvWriter:
    """``csv.writer(fileobj, ...)`` ilə eyni imza; nəticə neytrallaşdıran yazıcıdır."""
    return SafeCsvWriter(csv.writer(fileobj, *args, **kwargs))


def sheet_append(sheet, row: Iterable[Any]) -> None:
    """``openpyxl`` ``Worksheet.append`` — xanalar neytrallaşdırılaraq."""
    sheet.append(neutralise_row(row))


def sheet_cell(sheet, *, row: int, column: int, value: Any = None):
    """``openpyxl`` ``Worksheet.cell(row, column, value)`` — dəyər neytrallaşdırılaraq.

    ``value=None`` ötürülərsə (yalnız stil üçün mövcud xanaya müraciət) dəyər
    YAZILMIR — ``Worksheet.cell`` semantikası ilə eynidir.
    """
    if value is None:
        return sheet.cell(row=row, column=column)
    return sheet.cell(row=row, column=column, value=neutralise_cell(value))


__all__ = [
    "CONTROL_TRIGGERS",
    "FORMULA_TRIGGERS",
    "NEUTRAL_PREFIX",
    "SafeCsvWriter",
    "is_formula_like",
    "neutralise_cell",
    "neutralise_row",
    "safe_csv_writer",
    "sheet_append",
    "sheet_cell",
]
