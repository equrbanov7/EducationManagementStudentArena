"""Tələbə idxalı — SÜTUN MÜQAVİLƏSİ və şablon faylının qurulması.

Sütun açarları (``KEY``) kodun daxili adlarıdır; başlıqlar (``header``) isə
istifadəçinin gördüyü AZ mətndir. Fayl oxunanda başlıq sətri normallaşdırılıb
(kiçik hərf + boşluqsuz) açarlara xəritələnir, ona görə sütunların SIRASI
sərbəstdir və istifadəçi öz Excel-ini yenidən düzməli olmur.

Şablon `openpyxl` ilə `.xlsx` kimi verilir (paket `requirements/base.txt`-dədir);
paket yoxdursa CSV-yə düşür — hər iki halda EYNİ başlıqlar yazılır.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass

from django.utils.translation import pgettext

_CTX = "student_intake"

#: Şablonun vərəq adı (idxal oxuyucusu bu vərəqi üstün tutur).
SHEET_NAME = "Tələbələr"


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    hint: str
    required: bool = False


def columns() -> tuple[Column, ...]:
    """Şablon sütunları — sıra istifadəçiyə göstərilən sıradır."""

    return (
        Column("fin", pgettext(_CTX, "FİN"), pgettext(_CTX, "7 simvol, A-Z0-9 (məcburi)"), required=True),
        Column("first_name", pgettext(_CTX, "Ad"), pgettext(_CTX, "Məcburi"), required=True),
        Column("last_name", pgettext(_CTX, "Soyad"), pgettext(_CTX, "Məcburi"), required=True),
        Column("patronymic", pgettext(_CTX, "Ata adı"), pgettext(_CTX, "Boş qala bilər")),
        Column("birth_date", pgettext(_CTX, "Doğum tarixi"), pgettext(_CTX, "gg.aa.iiii və ya iiii-aa-gg")),
        Column("gender", pgettext(_CTX, "Cins"), pgettext(_CTX, "kişi / qadın")),
        Column("email", pgettext(_CTX, "E-poçt"), pgettext(_CTX, "Boşdursa placeholder yazılır")),
        Column("phone", pgettext(_CTX, "Telefon"), pgettext(_CTX, "Boş qala bilər")),
        Column("student_code", pgettext(_CTX, "Tələbə kodu"), pgettext(_CTX, "İstifadəçi adı bundan qurulur")),
        Column("faculty", pgettext(_CTX, "Fakültə"), pgettext(_CTX, "Adı və ya kodu (yoxlama üçün)")),
        Column("speciality", pgettext(_CTX, "İxtisas"), pgettext(_CTX, "Adı və ya kodu (yoxlama üçün)")),
        Column("group", pgettext(_CTX, "Qrup"), pgettext(_CTX, "Adı və ya kodu (məcburi)"), required=True),
        Column("admission_year", pgettext(_CTX, "Qəbul ili"), pgettext(_CTX, "Məsələn 2025 (məcburi)"), required=True),
        Column("course", pgettext(_CTX, "Kurs"), pgettext(_CTX, "1–6 (yalnız yoxlama)")),
        Column("language_sector", pgettext(_CTX, "Dil bölməsi"), pgettext(_CTX, "az / en / ru (yalnız yoxlama)")),
        Column("degree_level", pgettext(_CTX, "Təhsil səviyyəsi"), pgettext(_CTX, "bakalavr / magistr (yoxlama)")),
    )


def header_row() -> list:
    return [column.header for column in columns()]


def hint_row() -> list:
    return [column.hint for column in columns()]


def normalize_header(value: object) -> str:
    """Başlıq xanasını müqayisə açarına çevirir (NFKC + kiçik hərf + boşluqsuz)."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


def header_index() -> dict:
    """Normallaşdırılmış başlıq → sütun açarı.

    Həm AZ başlıq, həm də daxili açar qəbul edilir ki, skriptlə hazırlanmış
    (ingiliscə başlıqlı) fayl da oxunsun.
    """

    index: dict = {}
    for column in columns():
        index[normalize_header(column.header)] = column.key
        index[normalize_header(column.key)] = column.key
    # Tez-tez rast gəlinən sinonimlər.
    index[normalize_header("fin kod")] = "fin"
    index[normalize_header("fin kodu")] = "fin"
    index[normalize_header("ata adi")] = "patronymic"
    index[normalize_header("epocт")] = "email"
    index[normalize_header("e-mail")] = "email"
    index[normalize_header("mail")] = "email"
    index[normalize_header("telefon nomresi")] = "phone"
    index[normalize_header("telebe kodu")] = "student_code"
    index[normalize_header("qebul ili")] = "admission_year"
    index[normalize_header("dil bolmesi")] = "language_sector"
    index[normalize_header("tehsil seviyyesi")] = "degree_level"
    return index


def build_template() -> tuple[bytes, str, str]:
    """Şablon faylı → ``(məzmun, content_type, fayl adı)``.

    `openpyxl` varsa `.xlsx`, yoxdursa CSV (BOM ilə — Excel AZ hərflərini düzgün
    açsın deyə).
    """

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except Exception:  # pragma: no cover — paket olmayan mühit
        return _build_csv_template()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(header_row())
    sheet.append(hint_row())
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for cell in sheet[2]:
        cell.font = Font(italic=True, size=9)
    for position, column in enumerate(columns(), start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=position).column_letter].width = max(
            14, min(28, len(column.header) + 6)
        )
    sheet.freeze_panes = "A3"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return (
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "telebe_idxal_sablonu.xlsx",
    )


def _build_csv_template() -> tuple[bytes, str, str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header_row())
    writer.writerow(hint_row())
    return (
        buffer.getvalue().encode("utf-8-sig"),
        "text/csv; charset=utf-8",
        "telebe_idxal_sablonu.csv",
    )


__all__ = [
    "SHEET_NAME",
    "Column",
    "build_template",
    "columns",
    "header_index",
    "header_row",
    "hint_row",
    "normalize_header",
]
