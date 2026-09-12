"""Bound spreadsheet expansion and keep identifiers inert in exported files."""

import io
import zipfile

from core.upload_security import validate_zip_archive

MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_COLUMNS = 64


def validate_workbook(payload):
    validate_zip_archive(io.BytesIO(payload), max_file_count=128, max_extracted_size_bytes=MAX_EXPANDED_BYTES)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > MAX_EXPANDED_BYTES:
            raise ValueError("expanded workbook exceeds limit")


def export_text(value):
    """Neutralize formulas in CSV/Excel while retaining importable identifiers."""
    text = str(value) if value is not None else ""
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text
