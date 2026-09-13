"""Bound spreadsheet expansion and keep identifiers inert in exported files."""

import io
import zipfile

from core.export_safety import neutralise_cell
from core.upload_security import validate_zip_archive

MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_COLUMNS = 64


def validate_workbook(payload):
    validate_zip_archive(io.BytesIO(payload), max_file_count=128, max_extracted_size_bytes=MAX_EXPANDED_BYTES)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > MAX_EXPANDED_BYTES:
            raise ValueError("expanded workbook exceeds limit")


def export_text(value):
    """Neutralize formulas in CSV/Excel while retaining importable identifiers.

    2026-09-13 audit F-07: qayda artıq shared kernel-dədir
    (``core.export_safety.neutralise_cell``) — burada yalnız ``str`` imzası saxlanılır.
    """
    return neutralise_cell(str(value) if value is not None else "")
