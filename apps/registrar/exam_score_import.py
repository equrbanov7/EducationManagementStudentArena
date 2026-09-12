"""Yazılı imtahan ballarının FAYLDAN (XLSX / CSV) köçürülməsi — İmtahan Mərkəzi.

Sahibin tələbi (2026-09-12): «tələbələrin balları sistemə yüklənsin». Axın:

1. **Şablon** — seçilmiş açılışın siyahısı ilə DOLDURULMUŞ fayl endirilir
   (Tələbə № · FİN · Ad Soyad · Qrup · Cari bal · Bal); operator yalnız «Bal»
   sütununu doldurur.
2. **Quru icra** — fayl oxunur, hər sətir siyahıya uyğunlaşdırılır və
   yoxlanılır (naməlum tələbə, dublikat, diapazon, qeydiyyatsız, dəyişiklik =
   səbəb tələb edir). HEÇ NƏ YAZILMIR.
3. **Tətbiq** — EYNİ plan qurucusu, sonra sətirlər YALNIZ
   ``exam_score_entry.save_roster_scores`` → ``record_exam_score`` ilə yazılır
   (tək yazı yolu; hər sətir üçün bir ``ExamScoreEntry``, partiya üçün bir
   ``ExamScoreSheet`` xülasəsi).

Fayl serverdə SAXLANILMIR — tətbiq eyni faylı yenidən göndərir. ``openpyxl``
``requirements/base.txt``-dədir (3.1.5); yoxdursa CSV yolu qalır.

MODUL SƏRHƏDİ: ``apps.accounts.services.intake`` oxuyucusu TƏKRAR YAZILMIR,
çünki registrar ``accounts``-u import edə bilməz (``scripts/module_deps.py``).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from . import exam_score_entry as service
from .exam_score_import_safety import MAX_COLUMNS, export_text, validate_workbook

_CTX = "registrar.exam_score_import"

#: Yüklənən faylın yuxarı həddi — bir qrup siyahısı üçün bol-bol kifayətdir.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
#: Bir faylda emal olunan maksimum sətir (qrup ≤ 100 tələbə; ehtiyat tavan).
MAX_ROWS = 1000
#: Qəbul olunan uzantılar.
ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".csv")
#: XLSX şablonunun vərəq adı.
SHEET_NAME = "Ballar"

#: Sətir vəziyyətləri (quru icra + tətbiq eyni açarları işlədir).
STATUS_NEW = "new"  # cari bal yoxdur → sərbəst yazılacaq
STATUS_CHANGE = "change"  # cari bal var və fərqlidir → səbəb + qeyd + sənəd
STATUS_UNCHANGED = "unchanged"  # eyni bal → idempotent, toxunulmur
STATUS_SKIP = "skip"  # boş bal → toxunulmur
STATUS_ERROR = "error"  # bloklayan xəta

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

_AZ_TRANSLIT = str.maketrans({"ə": "e", "ı": "i", "ö": "o", "ü": "u", "ğ": "g", "ş": "s", "ç": "c", "İ": "i"})


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
    text = str(raw or "").strip().lower().translate(_AZ_TRANSLIT)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_name(raw) -> str:
    return normalize_header(raw)


def _map_headers(raw_headers) -> dict:
    """Başlıq sətri → ``{sütun indeksi: açar}``; «Bal» və (Tələbə № | FİN | Ad Soyad) məcburidir."""
    mapping: dict = {}
    for position, raw in enumerate(raw_headers):
        token = normalize_header(raw)
        if not token:
            continue
        for key, aliases in _HEADER_ALIASES.items():
            if token in aliases and key not in mapping.values():
                mapping[position] = key
                break
    present = set(mapping.values())
    if "score" not in present or not present & {"key", "fin", "full_name"}:
        raise ImportFileError(
            "import_headers_missing",
            pgettext(_CTX, "Faylın başlıq sətrində «Bal» və «Tələbə №» (və ya FİN / Ad Soyad) sütunları tapılmadı."),
        )
    return mapping


def _blank(values) -> bool:
    return not any(str(value or "").strip() for value in values)


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows_from_values(source, *, mapping) -> list:
    rows: list = []
    for number, raw in source:
        values = list(raw)
        if _blank(values):
            continue
        record = {"key": "", "fin": "", "full_name": "", "score": "", "_row": number}
        for position, key in mapping.items():
            if position < len(values):
                record[key] = _cell_text(values[position])
        rows.append(record)
        if len(rows) > MAX_ROWS:
            raise ImportFileError("import_too_many_rows", pgettext(_CTX, "Faylda sətir limiti aşılıb."))
    return rows


def _suffix(name: str) -> str:
    lowered = str(name or "").strip().lower()
    for suffix in ALLOWED_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return ""


def _read_xlsx(payload: bytes) -> list:
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
            return _read_table(enumerate(sheet.iter_rows(values_only=True), start=1))
        finally:
            workbook.close()
    except ImportFileError:
        raise
    except Exception:
        raise ImportFileError(
            "import_file_unreadable", pgettext(_CTX, "Fayl oxunmadı — zədəli və ya dəstəklənməyən Excel faylıdır.")
        ) from None


def _read_csv(payload: bytes) -> list:
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
            enumerate(csv.reader(io.StringIO(text), delimiter=dialect.delimiter, quotechar='"'), start=1)
        )
    except csv.Error:
        raise ImportFileError("import_file_unreadable", pgettext(_CTX, "CSV faylı oxunmadı.")) from None


def _read_table(numbered_rows) -> list:
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
        if len(source) > MAX_ROWS:
            raise ImportFileError("import_too_many_rows", pgettext(_CTX, "Faylda sətir limiti aşılıb."))
    if mapping is None:
        raise ImportFileError("import_file_empty", pgettext(_CTX, "Fayl boşdur — başlıq sətri tapılmadı."))
    return _rows_from_values(source, mapping=mapping)


def read_rows(uploaded_file) -> list:
    """Yüklənmiş faylı sətir siyahısına çevirir (``_row`` = fayldakı sətir nömrəsi)."""
    if uploaded_file is None:
        raise ImportFileError("import_file_required", pgettext(_CTX, "Fayl seçilməyib."))
    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size > MAX_UPLOAD_BYTES:
        raise ImportFileError("import_file_too_large", pgettext(_CTX, "Fayl çox böyükdür (maksimum 5 MB)."))
    suffix = _suffix(getattr(uploaded_file, "name", ""))
    if not suffix:
        raise ImportFileError(
            "import_file_type_unsupported", pgettext(_CTX, "Yalnız .xlsx və ya .csv faylı qəbul olunur.")
        )
    payload = uploaded_file.read(MAX_UPLOAD_BYTES + 1)
    if not payload:
        raise ImportFileError("import_file_empty", pgettext(_CTX, "Fayl boşdur."))
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ImportFileError("import_file_too_large", pgettext(_CTX, "Fayl çox böyükdür (maksimum 5 MB)."))
    rows = _read_csv(payload) if suffix == ".csv" else _read_xlsx(payload)
    if not rows:
        raise ImportFileError("import_no_rows", pgettext(_CTX, "Faylda tələbə sətri tapılmadı."))
    return rows


# ── Şablon ───────────────────────────────────────────────────────────────────


def template_columns(exam_score_max) -> list:
    """Şablonun sütun başlıqları (oxuyucu bunları tanıyır; sıra sərbəstdir)."""
    return [
        pgettext(_CTX, "Tələbə №"),
        pgettext(_CTX, "FİN"),
        pgettext(_CTX, "Ad Soyad"),
        pgettext(_CTX, "Qrup"),
        pgettext(_CTX, "Cari bal"),
        "%s (0–%s)" % (pgettext(_CTX, "Bal"), int(exam_score_max)),
    ]


def _template_rows(roster) -> list:
    rows = []
    for row in roster["rows"]:
        student = row["student"]
        rows.append(
            [
                student.username,
                getattr(student.profile, "fin", "") or "",
                student.get_full_name() or student.username,
                service.offering_label(roster["offering"]),
                _score_text(row.get("exam_score")),
                "",
            ]
        )
    return rows


def _score_text(value) -> str:
    if value is None:
        return ""
    return str(int(Decimal(value)))


def build_template(*, roster, fmt="xlsx"):
    """``(bytes, content_type, filename)`` — siyahı ilə doldurulmuş şablon."""
    offering = roster["offering"]
    headers = template_columns(roster["exam_score_max"])
    rows = [[export_text(value) for value in row] for row in _template_rows(roster)]
    stem = "imtahan_ballari_%s_%s" % (offering.subject.code or "fenn", service.offering_label(offering))
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem.translate(_AZ_TRANSLIT)).strip("_") or "imtahan_ballari"
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return ("﻿" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", f"{stem}.csv"
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.worksheet.datavalidation import DataValidation
    except Exception:  # pragma: no cover — paket olmayan mühit
        return build_template(roster=roster, fmt="csv")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column, width in zip("ABCDEF", (16, 12, 32, 14, 10, 12)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    if rows:
        validation = DataValidation(
            type="whole",
            operator="between",
            formula1="0",
            formula2=str(int(roster["exam_score_max"])),
            allow_blank=True,
        )
        validation.error = pgettext(_CTX, "Bal 0 ilə maksimum arasında tam ədəd olmalıdır.")
        sheet.add_data_validation(validation)
        validation.add(f"F2:F{len(rows) + 1}")
    output = io.BytesIO()
    workbook.save(output)
    return (
        output.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"{stem}.xlsx",
    )


# ── Quru icra (plan) ─────────────────────────────────────────────────────────


def _roster_index(roster) -> dict:
    """Siyahını üç açarla indekslə: istifadəçi adı / institusional id, FİN, normal ad."""
    by_key, by_fin, by_name = {}, {}, {}

    def add_identifier(index, value, row):
        if value in index and index[value] is not row:
            index[value] = None  # ambiguous aliases must never select a student
        else:
            index[value] = row

    for row in roster["rows"]:
        student = row["student"]
        add_identifier(by_key, student.username.lower(), row)
        add_identifier(by_key, export_text(student.username).lower(), row)
        institutional = getattr(student.profile, "institutional_identifier", None)
        if institutional:
            add_identifier(by_key, str(institutional).strip().lower(), row)
        fin = getattr(student.profile, "fin", "")
        if fin:
            add_identifier(by_fin, fin.strip().upper(), row)
        name = _normalize_name(student.get_full_name())
        if name:
            by_name.setdefault(name, []).append(row)
    return {"key": by_key, "fin": by_fin, "name": by_name}


def _resolve_student(record, index):
    """``(roster_row | None, xəta kodu, xəbərdarlıq)`` — fayl sətrini siyahıya uyğunlaşdır."""
    key = (record.get("key") or "").strip().lower()
    fin = (record.get("fin") or "").strip().upper()
    by_key = index["key"].get(key) if key else None
    by_fin = index["fin"].get(fin) if fin else None
    if key and fin and (by_key is None or by_fin is None or by_key is not by_fin):
        return None, "mismatch", ""
    if by_key is not None:
        return by_key, "", ""
    if by_fin is not None:
        return by_fin, "", ""
    if key or fin:
        return None, "unknown", ""
    name = _normalize_name(record.get("full_name"))
    candidates = index["name"].get(name, []) if name else []
    if len(candidates) == 1:
        return candidates[0], "", pgettext(_CTX, "ada görə uyğunlaşdırıldı")
    if len(candidates) > 1:
        return None, "ambiguous", ""
    return None, "unknown", ""


_ERROR_MESSAGES = {
    "mismatch": lambda: pgettext(_CTX, "Tələbə № və FİN fərqli tələbələrə aiddir."),
    "unknown": lambda: pgettext(_CTX, "Tələbə bu qrupun siyahısında tapılmadı (qeydiyyatı yoxdur)."),
    "ambiguous": lambda: pgettext(_CTX, "Eyni adlı bir neçə tələbə var — Tələbə № və ya FİN yazın."),
    "duplicate": lambda: pgettext(_CTX, "Bu tələbə faylda təkrarlanır."),
}


def build_plan(*, roster, rows) -> list:
    """Quru icra: hər fayl sətri üçün vəziyyət + mesaj. HEÇ NƏ YAZMIR.

    ``roster`` — ``exam_score_entry.roster_for_offering`` nəticəsi (cari ballar
    oradan gəlir, əlavə sorğu yoxdur).
    """
    index = _roster_index(roster)
    cap = roster["exam_score_max"]
    seen: set = set()
    plan = []
    for record in rows:
        item = {
            "row": record["_row"],
            "key": record.get("key", ""),
            "fin": record.get("fin", ""),
            "full_name": record.get("full_name", ""),
            "raw_score": record.get("score", ""),
            "enrollment_id": "",
            "student": "",
            "username": "",
            "current": None,
            "score": None,
            "status": STATUS_ERROR,
            "message": "",
            "warning": "",
        }
        plan.append(item)
        roster_row, code, warning = _resolve_student(record, index)
        if roster_row is None:
            item["message"] = _ERROR_MESSAGES[code]()
            continue
        student = roster_row["student"]
        item.update(
            enrollment_id=str(roster_row["enrollment"].id),
            student=student.get_full_name() or student.username,
            username=student.username,
            current=_score_text(roster_row.get("exam_score")) or None,
            warning=warning,
        )
        if item["enrollment_id"] in seen:
            item["message"] = _ERROR_MESSAGES["duplicate"]()
            continue
        seen.add(item["enrollment_id"])
        raw = str(record.get("score") or "").strip().replace(",", ".")
        try:
            cleaned = service._clean_score(raw, cap)
        except ValidationError as exc:
            item["message"] = " ".join(exc.messages)
            continue
        if cleaned is None:
            item["status"] = STATUS_SKIP
            item["message"] = pgettext(_CTX, "Bal boşdur — toxunulmur.")
            continue
        item["score"] = str(int(cleaned))
        current = roster_row.get("exam_score")
        if current is None:
            item["status"] = STATUS_NEW
        elif Decimal(current) == cleaned:
            item["status"] = STATUS_UNCHANGED
            item["message"] = pgettext(_CTX, "Eyni bal artıq yazılıb.")
        else:
            item["status"] = STATUS_CHANGE
            item["message"] = pgettext(_CTX, "Yazılmış bal dəyişir — səbəb, qeyd və sənəd tələb olunur.")
    return plan


def summarize(plan, *, roster=None) -> dict:
    """Vəziyyət sayğacları (+ faylda OLMAYAN siyahı tələbələri — «missing»)."""
    counts = {STATUS_NEW: 0, STATUS_CHANGE: 0, STATUS_UNCHANGED: 0, STATUS_SKIP: 0, STATUS_ERROR: 0}
    for item in plan:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    summary = {"total": len(plan), **counts}
    summary["writes"] = counts[STATUS_NEW] + counts[STATUS_CHANGE]
    if roster is not None:
        matched = {item["enrollment_id"] for item in plan if item["enrollment_id"]}
        summary["missing"] = sum(1 for row in roster["rows"] if str(row["enrollment"].id) not in matched)
    return summary


def needs_justification(plan) -> bool:
    return any(item["status"] == STATUS_CHANGE for item in plan)


def rows_for_service(plan, *, reason="", note="") -> list:
    """Plandan YALNIZ yazılacaq sətirləri servis formatına çevir."""
    return [
        {"enrollment_id": item["enrollment_id"], "score": item["score"], "reason": reason, "note": note}
        for item in plan
        if item["status"] in (STATUS_NEW, STATUS_CHANGE)
    ]


def apply_plan(*, offering, plan, by_user, request=None, sheet=None, reason="", note=""):
    """Planı tətbiq et — yazı YALNIZ servis qatından keçir (``save_roster_scores``).

    Nəticə: ``save_roster_scores`` lüğəti + hər plan sətrinin son vəziyyəti
    (``written`` / ``failed`` işarəsi ilə).
    """
    result = service.save_roster_scores(
        offering=offering,
        rows=rows_for_service(plan, reason=reason, note=note),
        by_user=by_user,
        request=request,
        sheet=sheet,
    )
    failed = result.get("failed_by_enrollment") or {}
    for item in plan:
        if item["status"] not in (STATUS_NEW, STATUS_CHANGE):
            continue
        problem = failed.get(item["enrollment_id"])
        if problem:
            item["status"] = STATUS_ERROR
            item["message"] = problem
        elif item["enrollment_id"] in result["written_ids"]:
            item["message"] = pgettext(_CTX, "Yazıldı.")
            item["written"] = True
        else:
            item["status"] = STATUS_UNCHANGED
            item["message"] = pgettext(_CTX, "Eyni bal artıq yazılıb.")
    result["total"] = len(plan)
    result["failed"] = sum(item["status"] == STATUS_ERROR for item in plan)
    result["skipped"] = len(plan) - result["written"] - result["failed"]
    return result


def enrollment_ids_for(plan) -> set:
    """Plandakı uyğunlaşmış qeydiyyatlar (testlər / yoxlama üçün)."""
    return {item["enrollment_id"] for item in plan if item["enrollment_id"]}


__all__ = [
    "ALLOWED_SUFFIXES",
    "MAX_ROWS",
    "MAX_UPLOAD_BYTES",
    "STATUS_CHANGE",
    "STATUS_ERROR",
    "STATUS_NEW",
    "STATUS_SKIP",
    "STATUS_UNCHANGED",
    "ImportFileError",
    "apply_plan",
    "build_plan",
    "build_template",
    "needs_justification",
    "read_rows",
    "rows_for_service",
    "summarize",
    "template_columns",
]
