"""Müqavilə faylının yoxlanması — PDF / JPG / PNG, ≤ 10 MB, məzmun imzası (magic bytes), təsadüfi ad.

``core.upload_security.validate_uploaded_file`` uzantını, MIME-ı, ölçünü və imzanı yoxlayır (markup/script
rədd edilir, şəkil Pillow ilə açılır); ``randomize_uploaded_filename`` adı ``uuid4`` ilə əvəz edir — orijinal ad
yalnız ``EmploymentContract.file_name``-də (HR siyahısında) qalır. Fayl qorunan mediadadır
(``media.check_file_access``).
"""

from __future__ import annotations

import os

from django.core.exceptions import ValidationError

from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ..constants import FILE_EXTENSIONS, FILE_MAX_MB, FILE_MIME_TYPES
from .errors import ContractError


def clean_upload(uploaded):
    """``(fayl, orijinal_ad)`` qaytarır; fayl yoxdursa ``(None, "")``. Yararsızdırsa ``ContractError``."""
    if not uploaded:
        return None, ""
    original = os.path.basename(str(getattr(uploaded, "name", "") or ""))[:255]
    try:
        validate_uploaded_file(
            uploaded,
            allowed_extensions=FILE_EXTENSIONS,
            max_size_mb=FILE_MAX_MB,
            allowed_mime_types=FILE_MIME_TYPES,
            allowed_mime_prefixes=(),
        )
    except ValidationError as exc:
        raise ContractError("file_invalid", "; ".join(exc.messages), field="file")
    randomize_uploaded_filename(uploaded)
    return uploaded, original


__all__ = ["clean_upload"]
