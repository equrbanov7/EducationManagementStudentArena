"""Təhlükəsizlik auditi 2026-10-07 — `.xlsx` idxallarında açılma (decompression) bombası.

`openpyxl.load_workbook(read_only=True)` vərəqi axınla oxuyur, amma
`sharedStrings.xml`-i TAM yaddaşa yığır. Tələbə/müəllim qəbul idxalı (5 MB) və
dərs yükü tapşırıq idxalı (10 MB) paketin AÇILMIŞ ölçüsünə baxmırdı — eyni
təkrarlanan XML ~1000 dəfə sıxılır, yəni 5 MB-lıq fayl ~5 GB açılıb sinxron veb
worker-i OOM edə bilirdi. İmtahan balı idxalında bu qoruma artıq var idi
(`registrar/exam_score_import_safety.validate_workbook`).

Testlər ucuzdur: paketə istinad olunmayan, sıfırlarla dolu bir hissə əlavə edilir —
elan olunan açılmış ölçü limiti keçir, real yaddaş ayrılmır (parser-ə çatmır).
"""

from __future__ import annotations

import io
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from openpyxl import Workbook

from core.upload_ooxml import validate_ooxml_expansion

MB = 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(rows, *, sheet_title=None, padding_bytes=0) -> bytes:
    book = Workbook()
    sheet = book.active
    if sheet_title:
        sheet.title = sheet_title
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    if padding_bytes:
        with zipfile.ZipFile(stream, "a", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("customXml/item1.xml", b"\0" * padding_bytes)
    return stream.getvalue()


class ExpansionHelperTest(SimpleTestCase):
    def test_rejects_package_over_expanded_budget(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_ooxml_expansion(_xlsx([["a"]], padding_bytes=3 * MB), max_expanded_bytes=2 * MB)
        self.assertEqual(ctx.exception.code, "expanded_too_large")

    def test_accepts_normal_package_and_restores_position(self):
        stream = io.BytesIO(_xlsx([["a", "b"], [1, 2]]))
        stream.seek(5)
        validate_ooxml_expansion(stream, max_expanded_bytes=2 * MB)
        self.assertEqual(stream.tell(), 5)

    def test_non_zip_is_reported_as_invalid_archive(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_ooxml_expansion(b"not a zip", max_expanded_bytes=MB)
        self.assertEqual(ctx.exception.code, "invalid_archive")


class StudentIntakeExpansionTest(SimpleTestCase):
    def _upload(self, payload):
        return SimpleUploadedFile("qebul.xlsx", payload, content_type=XLSX)

    def test_student_intake_rejects_expansion_bomb_before_parsing(self):
        from apps.accounts.services.intake import IntakeFileError, read_rows
        from apps.accounts.services.intake.spec import header_row

        payload = _xlsx([header_row()], padding_bytes=60 * MB)
        self.assertLess(len(payload), 5 * MB)
        with self.assertRaises(IntakeFileError) as ctx:
            read_rows(self._upload(payload))
        self.assertEqual(ctx.exception.code, "intake_file_too_large")

    def test_teacher_intake_rejects_expansion_bomb_before_parsing(self):
        from apps.accounts.services.intake import IntakeFileError
        from apps.accounts.services.intake.teachers import read_rows

        payload = _xlsx([["Ad", "Soyad"]], padding_bytes=60 * MB)
        with self.assertRaises(IntakeFileError) as ctx:
            read_rows(self._upload(payload))
        self.assertEqual(ctx.exception.code, "intake_file_too_large")

    def test_corrupt_xlsx_keeps_unreadable_error(self):
        from apps.accounts.services.intake import IntakeFileError, read_rows

        with self.assertRaises(IntakeFileError) as ctx:
            read_rows(self._upload(b"PK\x03\x04 broken"))
        self.assertEqual(ctx.exception.code, "intake_file_unreadable")


class WorkloadImportExpansionTest(SimpleTestCase):
    HEADER = ["Semestr", "Qruplar", "Fənn", "İxtisas", "Mühazirə cəmi", "Seminar cəmi", "Cəmi", "Kredit"]

    def test_workload_import_rejects_expansion_bomb_before_parsing(self):
        from apps.workload.services.imports import ImportFileError, parse_workbook

        payload = _xlsx([self.HEADER], padding_bytes=120 * MB)
        self.assertLess(len(payload), 10 * MB)
        with self.assertRaises(ImportFileError) as ctx:
            parse_workbook(SimpleUploadedFile("tapsiriq.xlsx", payload, content_type=XLSX))
        self.assertEqual(ctx.exception.code, "workload.file_too_big")

    def test_workload_import_still_parses_normal_file(self):
        from apps.workload.services.imports import parse_workbook

        payload = _xlsx([self.HEADER, ["PAYIZ", "101", "Riyaziyyat", "", 30, 15, 45, 6]])
        records = parse_workbook(SimpleUploadedFile("tapsiriq.xlsx", payload, content_type=XLSX))
        self.assertEqual(len(records), 1)
