"""Yüklənən faylın yoxlanması, heşlənməsi və təsadüfi adlandırılması.

Hər yükləmə ``core.upload_security`` qapısından keçir (uzantı ağ/qara siyahısı,
ikiqat uzantı, MIME, ölçü, məzmun imzası, şəkil sahələrində Pillow), ZIP
arxivləri əlavə olaraq zip-bomba/yuva yoxlamasından. Sonra SHA-256 hesablanır
(eyni faylın plagiat yoxlaması üçün) və ad UUID ilə əvəzlənir — orijinal ad
yalnız ``original_name`` sahəsinə yazılır.
"""

from __future__ import annotations

import hashlib
import os
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError

from core.upload_security import (
    DEFAULT_ALLOWED_MIME_TYPES,
    randomize_uploaded_filename,
    validate_uploaded_file,
    validate_zip_archive,
)

from ..constants import DEFAULT_MATERIAL_MAX_MB, IMAGE_EXTENSIONS, TEXTUAL_EXTENSIONS
from ..errors import FolderError

_CHUNK = 1024 * 1024
#: Kod/mətn faylları üçün brauzerin adətən göndərdiyi MIME-lar.
_TEXTUAL_EXTRA_MIME = {
    "application/octet-stream",
    "application/x-ipynb+json",
    "application/sql",
    "application/x-sql",
    "application/rtf",
    "application/x-tex",
    "application/x-yaml",
    "application/yaml",
    "text/x-python",
}
_MEDIA_EXTRA_MIME = {"video/mp4", "video/webm", "audio/mpeg"}
_OFFICE_EXTRA_MIME = {
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.spreadsheet",
}


def material_max_mb() -> int:
    """Material faylının limiti — ``settings.SUBJECT_FOLDER_MATERIAL_MAX_MB`` (default 50)."""
    try:
        return max(1, int(getattr(settings, "SUBJECT_FOLDER_MATERIAL_MAX_MB", DEFAULT_MATERIAL_MAX_MB)))
    except (TypeError, ValueError):
        return DEFAULT_MATERIAL_MAX_MB


def extension_of(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


def clean_original_name(name: str) -> str:
    """Göstəriş adı: yalnız son hissə, nəzarət simvolları atılır, ≤255 simvol."""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    return (base or "fayl")[:255]


def _allowed_mimes(extension: str) -> set:
    allowed = set(DEFAULT_ALLOWED_MIME_TYPES) | _MEDIA_EXTRA_MIME | _OFFICE_EXTRA_MIME
    if extension in TEXTUAL_EXTENSIONS:
        allowed |= _TEXTUAL_EXTRA_MIME
    return allowed


def sha256_of(uploaded) -> str:
    """Faylın SHA-256-sı (hissə-hissə oxunur, mövqe əvvələ qaytarılır)."""
    digest = hashlib.sha256()
    try:
        uploaded.seek(0)
    except Exception:  # pragma: no cover — seek dəstəkləməyən axın
        pass
    if hasattr(uploaded, "chunks"):
        for chunk in uploaded.chunks(_CHUNK):
            digest.update(chunk)
    else:  # pragma: no cover — sadə fayl obyekti
        while True:
            chunk = uploaded.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    try:
        uploaded.seek(0)
    except Exception:  # pragma: no cover
        pass
    return digest.hexdigest()


def prepare_upload(uploaded, *, allowed_extensions, max_mb: int, image_only: bool = False) -> dict:
    """Yoxlayır və meta qaytarır; uyğunsuz fayl → ``FolderError('upload.invalid')`` (mətn qapıdan gəlir).

    Nəticə: ``{"original_name", "size", "content_type", "sha256", "extension"}``.
    ⚠️ Çağırışdan sonra ``uploaded.name`` TƏSADÜFİ UUID adıdır.
    """
    if uploaded is None:
        raise FolderError.of("material.file_required")
    original = clean_original_name(getattr(uploaded, "name", ""))
    extension = extension_of(original)
    allowed = set(IMAGE_EXTENSIONS) if image_only else set(allowed_extensions)
    try:
        validate_uploaded_file(
            uploaded,
            allowed_extensions=allowed,
            max_size_mb=max_mb,
            allowed_mime_types=_allowed_mimes(extension),
            verify_image=True if (image_only or extension in IMAGE_EXTENSIONS) else None,
        )
        if extension == ".zip":
            validate_zip_archive(uploaded)
    except ValidationError as exc:
        message = " ".join(str(item) for item in exc.messages) or str(FolderError.of("upload.invalid"))
        raise FolderError("upload.invalid", message, {"name": original}) from exc
    meta = {
        "original_name": original,
        "size": int(getattr(uploaded, "size", 0) or 0),
        "content_type": (getattr(uploaded, "content_type", "") or "application/octet-stream")[:120],
        "sha256": sha256_of(uploaded),
        "extension": extension,
    }
    randomize_uploaded_filename(uploaded)
    return meta


__all__ = ["clean_original_name", "extension_of", "material_max_mb", "prepare_upload", "sha256_of"]
