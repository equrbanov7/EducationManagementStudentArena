"""Visual-first sual mənbələri üçün parse-dan əvvəl upload yoxlamaları."""

from __future__ import annotations

import os

from django.utils.translation import pgettext

from apps.exams.services.parsing.extraction.constants import MAX_UPLOAD_BYTES
from apps.exams.services.parsing.extraction.safety import (
    _ensure_within_size_limit,
    _pdf_safety_check,
    _peek_magic_bytes,
    _verify_magic_bytes,
)

_IMAGE_SIGNATURES = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}


def validate_visual_upload(uploaded_file) -> None:
    """Ölçü, uzantı/magic-byte və PDF aktiv kontent guard-larını tətbiq et."""

    filename = str(getattr(uploaded_file, "name", "") or "").lower()
    extension = os.path.splitext(filename)[1]
    _ensure_within_size_limit(uploaded_file, MAX_UPLOAD_BYTES)

    if extension == ".pdf":
        if not _verify_magic_bytes(_peek_magic_bytes(uploaded_file, 8), "pdf"):
            raise ValueError(pgettext("exams.service.parsing.error", "file_signature_mismatch"))
        _pdf_safety_check(uploaded_file)
        return

    signature = _IMAGE_SIGNATURES.get(extension)
    if signature is None:
        raise ValueError(pgettext("exams.service.parsing.error", "unsupported_file_type"))
    if not _verify_magic_bytes(_peek_magic_bytes(uploaded_file, 12), signature):
        raise ValueError(pgettext("exams.service.parsing.error", "file_signature_mismatch"))


__all__ = ["validate_visual_upload"]
