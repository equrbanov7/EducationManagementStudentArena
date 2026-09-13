"""Yazılı imtahan balı idxalı — FAYL OXUYUCUSU (XLSX / CSV → sətir lüğətləri).

2026-09-14 (W2 `w2paper`): ``exam_score_import``-dan (modul-ölçü büdcəsi,
SOFT_CAP=600) buraya köçürülüb; ``exam_score_import`` eyni adları re-eksport
edir. Əlavə: «S1», «S2», … (və ya «Sual 1», «Q1») sual sütunları ``q<n>``
açarı ilə tanınır — sətrin ``questions`` lüğətinə düşür (``{n: mətn}``); «Bal»
sütunu artıq MƏCBURİ DEYİL, S-sütunları varsa kifayətdir.

Fayl serverdə SAXLANILMIR. ``openpyxl`` ``requirements/base.txt``-dədir; yoxdursa
CSV yolu qalır. Modul sərhədi: registrar ``accounts``-u import edə bilməz.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata

from django.utils.translation import pgettext

from . import exam_score_questions as questions
from .exam_score_import_safety import MAX_COLUMNS, validate_workbook

_CTX = "registrar.exam_score_import"

#: Yüklənən faylın yuxarı həddi — bir qrup siyahısı üçün bol-bol kifayətdir.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
#: Bir faylda emal olunan maksimum sətir (qrup ≤ 100 tələbə; ehtiyat tavan).
MAX_ROWS = 1000
#: Qəbul olunan uzantılar.
ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".csv")
#: XLSX şablonunun vərəq adı.
SHEET_NAME = "Ballar"


#: Normallaşdırılmış başlıq → açar. Sütun sırası sərbəstdir.
_HEADER_ALIASES = {
    "key": {
        "telebe",
        "telebe no",
        "telebe n",
        "istifadeci adi",
        "username",
        "login",
        "student",
        "student id",
        "student no",
        "kod",
    },
    "fin": {"fin", "fin kod", "fin kodu"},
    "full_name": {"ad soyad", "adsoyad", "ad soyad ata adi", "telebe adi", "full name", "name", "ad"},
    "score": {"bal", "imtahan bali", "score", "exam score", "netice", "yeni bal", "imtahan"},
}

#: Sual sütunu başlığı — «S1», «S 1», «Sual 1», «Q1», «Question 1» (normallaşdırılmış).
_QUESTION_HEADER_RE = re.compile(r"^(?:s|sual|q|question)\s?(\d{1,2})$")

AZ_TRANSLIT = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c", "İ": "i"})


class ImportFileError(Exception):
    """Faylın ÖZÜ oxunmadı — sətir-səviyyəli xətadan fərqli (bütün fayl rədd olunur)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self):
        return self.code


# ── Başlıq və mətn normallaşdırması ──────────────────────────────────────────


def normalize_header(raw) -> str:
    """«Tələbə №» → «telebe», «Bal (0–50)» → «bal»: kiçik hərf, AZ translit, mötərizəsiz."""
    text = str(raw or "").strip().lower().translate(AZ_TRANSLIT)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(raw) -> str:
    return normalize_header(raw)


def _map_headers(raw_headers) -> dict:
    """Başlıq sətri → ``{sütun indeksi: açar}``; («Bal» | S1..Sn) və (Tələbə № | FİN | Ad Soyad) məcburidir.

    2026-09-14 (W2 `w2paper`): «S1», «S2», … sual sütunları ``q1``, ``q2``, …
    açarları ilə tanınır (ən çox 10). Faylda həm «Bal», həm S-sütunları ola
    bilər — sətirdə hər hansı S xanası doludursa sual rejimi üstündür.
    """
    mapping: dict = {}
    for position, raw in enumerate(raw_headers):
        token = normalize_header(raw)
        if not token:
            continue
        match = _QUESTION_HEADER_RE.match(token)
        if match and 1 <= int(match.group(1)) <= questions.QUESTION_COUNT_MAX:
            key = f"q{int(match.group(1))}"
            if key not in mapping.values():
                mapping[position] = key
            continue
        for key, aliases in _HEADER_ALIASES.items():
            if token in aliases and key not in mapping.values():
                mapping[position] = key
                break
    present = set(mapping.values())
    has_questions = any(key.startswith("q") for key in present)
    if ("score" not in present and not has_questions) or not present & {"key", "fin", "full_name"}:
        raise ImportFileError(
            "import_headers_missing",
            pgettext(_CTX, "Faylın başlıq sətrində «Bal» və «Tələbə №» (və ya FİN / Ad Soyad) sütunları tapılmadı."),
        )
    return mapping


def question_count_in(mapping) -> int:
    """Başlıqda tapılan ən böyük S-nömrəsi (sual sütunu yoxdursa 0)."""
    numbers = [int(key[1:]) for key in mapping.values() if key.startswith("q")]
    return max(numbers) if numbers else 0


def _blank(values) -> bool:
    return not any(str(value or "").strip() for value in values)


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows_from_values(source, *, mapping, max_rows=MAX_ROWS) -> list:
    rows: list = []
    for number, raw in source:
        values = list(raw)
        if _blank(values):
            continue
        record = {"key": "", "fin": "", "full_name": "", "score": "", "_row": number, "questions": {}}
        for position, key in mapping.items():
            if position >= len(values):
                continue
            if key.startswith("q"):
                record["questions"][int(key[1:])] = _cell_text(values[position])
            else:
                record[key] = _cell_text(values[position])
        rows.append(record)
        if len(rows) > max_rows:
            raise ImportFileError("import_too_many_rows", pgettext(_CTX, "Faylda sətir limiti aşılıb."))
    return rows


def _suffix(name: str) -> str:
    lowered = str(name or "").strip().lower()
    for suffix in ALLOWED_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return ""


def _read_xlsx(payload: bytes, *, max_rows=MAX_ROWS) -> list:
    try:
        from openpyxl import load_workbook
    except Exception:  # pragma: no cover — paket olmayan mühit
        raise ImportFileError(
            "import_xlsx_unsupported",
            pgettext(_CTX, "Bu serverdə .xlsx oxunmur — faylı CSV kimi yadda saxlayıb yenidən yükləyin."),
        ) from None
    try:
        validate_workbook(payload)
        workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
        try:
            sheet = workbook[SHEET_NAME] if SHEET_NAME in workbook.sheetnames else workbook[workbook.sheetnames[0]]
            if sheet.max_column and sheet.max_column > MAX_COLUMNS:
                raise ValueError("too many columns")
            return _read_table(enumerate(sheet.iter_rows(values_only=True), start=1), max_rows=max_rows)
        finally:
            workbook.close()
    except ImportFileError:
        raise
    except Exception:
        raise ImportFileError(
            "import_file_unreadable", pgettext(_CTX, "Fayl oxunmadı — zədəli və ya dəstəklənməyən Excel faylıdır.")
        ) from None


def _read_csv(payload: bytes, *, max_rows=MAX_ROWS) -> list:
    for encoding in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover — latin-1 həmişə açır
        raise ImportFileError("import_file_unreadable", pgettext(_CTX, "Fayl oxunmadı — kodlaşdırma tanınmadı."))
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        return _read_table(
            enumerate(csv.reader(io.StringIO(text), delimiter=dialect.delimiter, quotechar='"'), start=1),
            max_rows=max_rows,
        )
    except csv.Error:
        raise ImportFileError("import_file_unreadable", pgettext(_CTX, "CSV faylı oxunmadı.")) from None


def _read_table(numbered_rows, *, max_rows=MAX_ROWS) -> list:
    mapping = None
    source: list = []
    for number, values in numbered_rows:
        values = list(values)
        if len(values) > MAX_COLUMNS:
            raise ImportFileError("import_too_many_columns", pgettext(_CTX, "Faylda sütun limiti aşılıb."))
        if mapping is None:
            if _blank(values):
                continue
            mapping = _map_headers(values)
            continue
        if _blank(values):
            continue
        source.append((number, values))
        if len(source) > max_rows:
            raise ImportFileError("import_too_many_rows", pgettext(_CTX, "Faylda sətir limiti aşılıb."))
    if mapping is None:
        raise ImportFileError("import_file_empty", pgettext(_CTX, "Fayl boşdur — başlıq sətri tapılmadı."))
    return _rows_from_values(source, mapping=mapping, max_rows=max_rows)


def read_rows(uploaded_file, *, max_rows=None, max_upload_bytes=None) -> list:
    """Yüklənmiş faylı sətir siyahısına çevirir (``_row`` = fayldakı sətir nömrəsi).

    Limitlər parametrlə keçir ki, ``exam_score_import`` öz sabitlərini ötürsün
    (testlər ``importer.MAX_ROWS``-u patch edir).
    """
    max_rows = MAX_ROWS if max_rows is None else int(max_rows)
    max_upload_bytes = MAX_UPLOAD_BYTES if max_upload_bytes is None else int(max_upload_bytes)
    if uploaded_file is None:
        raise ImportFileError("import_file_required", pgettext(_CTX, "Fayl seçilməyib."))
    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size > max_upload_bytes:
        raise ImportFileError("import_file_too_large", pgettext(_CTX, "Fayl çox böyükdür (maksimum 5 MB)."))
    suffix = _suffix(getattr(uploaded_file, "name", ""))
    if not suffix:
        raise ImportFileError(
            "import_file_type_unsupported", pgettext(_CTX, "Yalnız .xlsx və ya .csv faylı qəbul olunur.")
        )
    payload = uploaded_file.read(max_upload_bytes + 1)
    if not payload:
        raise ImportFileError("import_file_empty", pgettext(_CTX, "Fayl boşdur."))
    if len(payload) > max_upload_bytes:
        raise ImportFileError("import_file_too_large", pgettext(_CTX, "Fayl çox böyükdür (maksimum 5 MB)."))
    rows = _read_csv(payload, max_rows=max_rows) if suffix == ".csv" else _read_xlsx(payload, max_rows=max_rows)
    if not rows:
        raise ImportFileError("import_no_rows", pgettext(_CTX, "Faylda tələbə sətri tapılmadı."))
    return rows


__all__ = [
    "ALLOWED_SUFFIXES",
    "AZ_TRANSLIT",
    "MAX_ROWS",
    "MAX_UPLOAD_BYTES",
    "SHEET_NAME",
    "ImportFileError",
    "normalize_header",
    "normalize_name",
    "question_count_in",
    "read_rows",
]
