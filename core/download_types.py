"""Yüklənmiş faylın endirmə cavabı — ``Content-Type`` UZANTIDAN, ağ siyahı ilə.

Audit 2026-09-28 SF-3 (``apps.subject_folder``) və 2026-10-07 təhlükəsizlik
auditi (elan / müraciət qoşmaları): endirmədə ``Content-Type`` brauzerin
yükləmə zamanı BƏYAN ETDİYİ dəyərdən (``UploadedFile.content_type``) götürülürdü.
Həmin dəyər tam klientin nəzarətindədir — ``text/html``/``image/svg+xml``
bəyanı ilə yüklənmiş PDF/PNG bizim origin-dən aktiv sənəd tipi ilə verilirdi.

Burada tip yalnız fayl adının uzantısından, AÇIQ ağ siyahıdan çıxarılır;
siyahıda olmayan hər uzantı (HTML/SVG/XML/JS də daxil) →
``application/octet-stream``. ``mimetypes``-ə (sistemin ``mime.types``-ı
mühitdən-mühitə fərqlidir) etibar edilmir. Cavab həmişə ``attachment`` +
``nosniff`` + ``private, no-store`` ilə gedir.
"""

from __future__ import annotations

import os

from django.http import FileResponse, Http404

OCTET_STREAM = "application/octet-stream"

#: Endirmədə verilə bilən tiplər — uzantı → MIME. Yalnız brauzerdə skript
#: icra etməyən (passiv) formatlar; yenisini əlavə edərkən bu şərti yoxlayın.
SAFE_DOWNLOAD_TYPES: dict[str, str] = {
    # Sənədlər
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".rtf": "application/rtf",
    # Şəkillər (SVG QƏSDƏN yoxdur — skript daşıyır)
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    # Arxivlər
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
    # Media
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    # Mətn / data
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".json": "application/json",
}


def content_type_for_name(name: str) -> str:
    """Fayl adının uzantısına görə endirmə ``Content-Type``-ı (ağ siyahı, yoxdursa octet-stream)."""
    extension = os.path.splitext(str(name or ""))[1].lower()
    return SAFE_DOWNLOAD_TYPES.get(extension, OCTET_STREAM)


def attachment_file_response(field_file, *, filename: str) -> FileResponse:
    """Saxlanmış faylı ƏLAVƏ kimi verir; tip ``filename``-in uzantısından (klient bəyanı nəzərə alınmır)."""
    if not field_file:
        raise Http404
    try:
        handle = field_file.open("rb")
    except (OSError, ValueError) as exc:  # pragma: no cover — itmiş fayl
        raise Http404 from exc
    name = filename or "fayl"
    response = FileResponse(handle, as_attachment=True, filename=name)
    response["Content-Type"] = content_type_for_name(name)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["OCTET_STREAM", "SAFE_DOWNLOAD_TYPES", "attachment_file_response", "content_type_for_name"]
