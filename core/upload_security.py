"""
Upload security helpers.

Centralized validation for user-uploaded files:
- extension allow/deny checks
- MIME type checks
- file size limits
- random file name generation
"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

DEFAULT_MAX_UPLOAD_SIZE_MB = 25

BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe",
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".phtml",
    ".phar",
    ".com",
    ".bat",
    ".cmd",
    ".msi",
    ".dll",
    ".scr",
    ".html",
    ".htm",
    ".svg",
    ".js",
    ".vbs",
    ".wsf",
    ".ps1",
    ".sh",
}

BLOCKED_MIME_TYPES = {
    "application/x-msdownload",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-httpd-php",
    "text/x-php",
}

DEFAULT_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.rar",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/json",
    "application/xml",
    "application/octet-stream",
    "text/plain",
    "text/csv",
}

DEFAULT_ALLOWED_MIME_PREFIXES = ("image/", "video/", "audio/", "text/")

IMAGE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".gif", ".webp"}


def _normalized_extension(file_name: str) -> str:
    return PurePosixPath((file_name or "").lower()).suffix


def _has_dangerous_stem_extension(file_name: str) -> bool:
    """Return True if any non-final suffix in the filename is a blocked extension.

    This detects double-extension attacks such as ``shell.php.jpg``.
    """
    suffixes = PurePosixPath((file_name or "").lower()).suffixes
    if len(suffixes) <= 1:
        return False
    for ext in suffixes[:-1]:
        if ext in BLOCKED_UPLOAD_EXTENSIONS:
            return True
    return False


def _read_head(uploaded_file, size=16):
    try:
        current_pos = uploaded_file.tell()
    except Exception:
        current_pos = None

    try:
        chunk = uploaded_file.read(size)
    except Exception:
        chunk = b""
    finally:
        if current_pos is not None:
            try:
                uploaded_file.seek(current_pos)
            except Exception:
                pass
    return chunk or b""


def _signature_indicates_blocked_type(uploaded_file) -> bool:
    head = _read_head(uploaded_file, size=16).lstrip()
    if head.startswith(b"MZ"):  # PE/EXE
        return True
    if head.startswith(b"<?php"):  # PHP script
        return True
    return False


def _resolve_mime_type(uploaded_file) -> str:
    content_type = (getattr(uploaded_file, "content_type", "") or "").strip().lower()
    if content_type:
        return content_type
    guessed_type = mimetypes.guess_type(getattr(uploaded_file, "name", "") or "")[0]
    return (guessed_type or "").lower()


def validate_uploaded_file(
    uploaded_file,
    *,
    allowed_extensions=None,
    max_size_mb=None,
    allowed_mime_types=None,
    allowed_mime_prefixes=DEFAULT_ALLOWED_MIME_PREFIXES,
):
    """
    Validate uploaded file using extension, MIME type, and size checks.
    Raises ValidationError on any violation.
    """
    if uploaded_file is None:
        return

    extension = _normalized_extension(getattr(uploaded_file, "name", ""))
    if not extension:
        raise ValidationError(pgettext("upload.security.error", "Fayl uzantısı müəyyən edilə bilmədi."))

    if extension in BLOCKED_UPLOAD_EXTENSIONS:
        raise ValidationError(pgettext("upload.security.error", "Bu fayl tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    if _has_dangerous_stem_extension(getattr(uploaded_file, "name", "")):
        raise ValidationError(pgettext("upload.security.error", "Bu fayl tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    normalized_allowed_extensions = None
    if allowed_extensions:
        normalized_allowed_extensions = {f".{ext.lstrip('.').lower()}" for ext in allowed_extensions}
        if extension not in normalized_allowed_extensions:
            raise ValidationError(pgettext("upload.security.error", "Bu fayl uzantısı dəstəklənmir."))

    if max_size_mb is None:
        max_size_mb = int(getattr(settings, "FILE_UPLOAD_SECURITY_MAX_SIZE_MB", DEFAULT_MAX_UPLOAD_SIZE_MB))

    max_size_bytes = int(max_size_mb) * 1024 * 1024
    if getattr(uploaded_file, "size", 0) > max_size_bytes:
        raise ValidationError(
            pgettext("upload.security.error", "Fayl ölçüsü limiti keçildi (maksimum {max_size_mb} MB).").format(
                max_size_mb=int(max_size_mb)
            )
        )

    mime_type = _resolve_mime_type(uploaded_file)
    if not mime_type:
        raise ValidationError(pgettext("upload.security.error", "Faylın MIME tipi müəyyən edilə bilmədi."))

    if mime_type in BLOCKED_MIME_TYPES:
        raise ValidationError(pgettext("upload.security.error", "Bu MIME tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    if _signature_indicates_blocked_type(uploaded_file):
        raise ValidationError(
            pgettext("upload.security.error", "Fayl məzmunu bloklanan icra olunan/script tipinə uyğundur.")
        )

    allowed_mime_set = set(allowed_mime_types or DEFAULT_ALLOWED_MIME_TYPES)
    has_allowed_prefix = any(mime_type.startswith(prefix) for prefix in (allowed_mime_prefixes or ()))
    if mime_type not in allowed_mime_set and not has_allowed_prefix:
        raise ValidationError(pgettext("upload.security.error", "Bu MIME tipi dəstəklənmir."))


def randomize_uploaded_filename(uploaded_file):
    """
    Replace original upload file name with a random UUID-based one.
    """
    if uploaded_file is None:
        return uploaded_file

    extension = _normalized_extension(getattr(uploaded_file, "name", ""))
    uploaded_file.name = f"{uuid4().hex}{extension}"
    return uploaded_file


class FileUploadValidator:
    """
    Django model-field validator that runs ``validate_uploaded_file`` on newly
    uploaded files.  Committed ``FieldFile`` objects (already stored on disk)
    are skipped so that loading existing records does not trigger validation.

    Usage::

        file = models.FileField(validators=[FileUploadValidator()])
        file = models.FileField(validators=[FileUploadValidator(
            allowed_extensions={".pdf", ".zip"},
            max_size_mb=10,
        )])
    """

    def __init__(self, *, allowed_extensions=None, max_size_mb=None):
        self.allowed_extensions = allowed_extensions
        self.max_size_mb = max_size_mb

    def __call__(self, value):
        # value is None or a FieldFile for committed objects – skip those
        if not value:
            return
        if getattr(value, "_committed", True):
            return
        validate_uploaded_file(
            value,
            allowed_extensions=self.allowed_extensions,
            max_size_mb=self.max_size_mb,
        )

    def __eq__(self, other):
        return (
            isinstance(other, FileUploadValidator)
            and self.allowed_extensions == other.allowed_extensions
            and self.max_size_mb == other.max_size_mb
        )

    def deconstruct(self):
        return (
            "core.upload_security.FileUploadValidator",
            [],
            {k: v for k, v in (("allowed_extensions", self.allowed_extensions), ("max_size_mb", self.max_size_mb)) if v is not None},
        )
