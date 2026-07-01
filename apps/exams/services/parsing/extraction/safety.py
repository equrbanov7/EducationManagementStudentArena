"""extraction paketi — safety."""

from django.utils.translation import pgettext

from .constants import (
    FILE_SIGNATURES,
)


def _ensure_within_size_limit(uploaded_file, limit: int) -> None:
    if uploaded_file.size and uploaded_file.size > limit:
        raise ValueError(pgettext("exams.service.parsing.error", "file_too_large"))


def _peek_magic_bytes(uploaded_file, length: int = 8) -> bytes:
    """Faylın əvvəlindən magic bytes oxu, sonra cursor-u geri qaytar."""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    head = uploaded_file.read(length) or b""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return head


def _verify_magic_bytes(head: bytes, expected_key: str) -> bool:
    signatures = FILE_SIGNATURES.get(expected_key, [])
    return any(head.startswith(sig) for sig in signatures)


def _pdf_safety_check(uploaded_file) -> None:
    """
    PDF-də OpenAction/JavaScript/embedded file kimi aktiv kontentin olub-olmadığını yoxlayırıq.
    Tam sanitize etmirik — sadəcə şübhəli pattern olarsa rədd edirik.
    """
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    # PDF-in ilk hissəsindən şübhəli açar sözləri axtarırıq (tam fayla baxmaq baha olardı).
    sample = uploaded_file.read(256 * 1024) or b""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    suspicious_markers = (
        b"/JS",
        b"/JavaScript",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/AA",  # additional actions
    )
    if any(marker in sample for marker in suspicious_markers):
        raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_active_content"))
