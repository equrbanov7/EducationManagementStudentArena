"""«Faylı müqayisə et» — yüklənən PDF YALNIZ yaddaşda oxunur, heç yerdə saxlanılmır.

* Gövdə ölçüsü multipart parse-dan ƏVVƏL ``CONTENT_LENGTH`` ilə yoxlanılır (limitdən böyük → rədd);
* yükləmə handler-i ``_CappedMemoryUploadHandler`` — Django-nun ``TemporaryFileUploadHandler``-i işə
  düşmür, yəni fayl diskdə müvəqqəti fayl kimi də yaranmır; limit aşılsa parse dayandırılır;
* məzmun imzası (magic bytes) ``%PDF-`` olmalıdır; uzantıya / brauzerin MIME-ına etibar edilmir;
* nəticə yalnız SHA-256 müqayisəsidir — faylın məzmunu oxunmur, log-a yazılmır.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload

FIELD_NAME = "sened"
PDF_MAGIC = b"%PDF-"
#: 2 MB — ASGI gövdəni əvvəlcə ``SpooledTemporaryFile``-a oxuyur (2.5 MB-dan sonra diskə); limit ondan aşağı
#: qalır ki, fayl yaddaşda qalsın. Transkript PDF-ləri 2 MB-dan xeyli kiçikdir. nginx ``/yoxla/`` üçün 3m.
DEFAULT_MAX_MB = 2
#: Multipart sərhədləri, başlıqlar və CSRF sahəsi üçün ehtiyat.
_ENVELOPE_BYTES = 64 * 1024

RESULT_MATCH = "match"
RESULT_MISMATCH = "mismatch"
RESULT_NO_FILE = "no_file"
RESULT_TOO_LARGE = "too_large"
RESULT_NOT_PDF = "not_pdf"
RESULT_NO_REFERENCE = "no_reference"


def max_bytes() -> int:
    try:
        mb = int(getattr(settings, "DOCUMENT_VERIFY_UPLOAD_MAX_MB", DEFAULT_MAX_MB) or DEFAULT_MAX_MB)
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_MB
    return max(1, min(mb, 2)) * 1024 * 1024  # qlobal gövdə limiti 5 MB-dır (core.upload_limits)


def body_too_large(request) -> bool:
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        return True
    return length > max_bytes() + _ENVELOPE_BYTES


class _CappedMemoryUploadHandler(MemoryFileUploadHandler):
    """Həmişə yaddaşda saxlayır (disk yox), limit aşılanda yükləməni dayandırır."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = True
        self._received = 0

    def receive_data_chunk(self, raw_data, start):
        self._received += len(raw_data)
        if self._received > max_bytes():
            if self.request is not None:
                self.request.doc_verify_upload_too_large = True
            raise StopUpload(connection_reset=False)
        return super().receive_data_chunk(raw_data, start)


def install_memory_handler(request) -> None:
    """``request.POST``/``FILES`` oxunmamışdan ƏVVƏL çağırılmalıdır (view ``csrf_exempt`` + daxili ``csrf_protect``)."""
    if hasattr(request, "_files"):  # gövdə artıq oxunub (məs. view-as middleware) — handler qoyula bilməz
        return
    request.upload_handlers = [_CappedMemoryUploadHandler(request)]


def compare(uploaded, expected_sha256: str) -> str:
    """Yüklənmiş fayl ↔ saxlanmış həş → nəticə açarı (``RESULT_*``)."""
    if not expected_sha256:
        return RESULT_NO_REFERENCE
    if uploaded is None:
        return RESULT_NO_FILE
    size = getattr(uploaded, "size", 0) or 0
    if size <= 0:
        return RESULT_NO_FILE
    if size > max_bytes():
        return RESULT_TOO_LARGE
    uploaded.seek(0)
    if uploaded.read(len(PDF_MAGIC)) != PDF_MAGIC:
        return RESULT_NOT_PDF
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():  # `chunks()` özü əvvələ qayıdır (seek(0)) — bütün baytlar həşlənir
        digest.update(chunk)
    return RESULT_MATCH if digest.hexdigest() == expected_sha256 else RESULT_MISMATCH


__all__ = [
    "FIELD_NAME",
    "RESULT_MATCH",
    "RESULT_MISMATCH",
    "RESULT_NOT_PDF",
    "RESULT_NO_FILE",
    "RESULT_NO_REFERENCE",
    "RESULT_TOO_LARGE",
    "body_too_large",
    "compare",
    "install_memory_handler",
    "max_bytes",
]
