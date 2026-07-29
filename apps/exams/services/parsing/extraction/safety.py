"""extraction paketi — safety."""

from collections.abc import Mapping

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
    # Uzun raw marker-lər compressed stream-də təsadüfi uyğunlaşma riski
    # yaratmır; qısa /JS və /AA isə aşağıdakı PDF object-tree auditində baxılır.
    raw_markers = (
        b"/JavaScript",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/RichMedia",
    )
    carry = b""
    overlap = max(map(len, raw_markers)) - 1
    try:
        while True:
            chunk = uploaded_file.read(64 * 1024) or b""
            if not chunk:
                break
            sample = carry + chunk
            if any(marker in sample for marker in raw_markers):
                raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_active_content"))
            carry = sample[-overlap:]
        uploaded_file.seek(0)
        from pypdf import PdfReader

        try:
            reader = PdfReader(uploaded_file, strict=False)
        except Exception as exc:
            raise ValueError(pgettext("exams.service.parsing.error", "file_corrupt")) from exc
        if reader.is_encrypted:
            raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_encrypted"))
        try:
            has_active_content = _pdf_reader_has_active_content(reader)
        except Exception as exc:
            # Natamam/cyclic object-tree-ni təhlükəsiz sənəd kimi qəbul etmə.
            raise ValueError(pgettext("exams.service.parsing.error", "file_corrupt")) from exc
        if has_active_content:
            raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_active_content"))
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass


def _resolve(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _dangerous_action(value) -> bool:
    dangerous_types = {
        "/EmbeddedFile",
        "/ImportData",
        "/JavaScript",
        "/Launch",
        "/Movie",
        "/RichMedia",
        "/Sound",
        "/SubmitForm",
    }
    pending = [value]
    seen: set[int] = set()
    inspected = 0
    while pending:
        current = _resolve(pending.pop())
        if not isinstance(current, Mapping) or id(current) in seen:
            continue
        seen.add(id(current))
        inspected += 1
        if inspected > 50_000:
            return True
        if "/JS" in current or str(current.get("/S", "")) in dangerous_types:
            return True
        following = _resolve(current.get("/Next"))
        if isinstance(following, list):
            pending.extend(following)
        elif following is not None:
            pending.append(following)
    return False


def _field_tree_has_actions(fields) -> bool:
    pending = list(_resolve(fields) or ())
    inspected = 0
    while pending:
        value = _resolve(pending.pop())
        inspected += 1
        if inspected > 50_000:
            return True
        if not isinstance(value, Mapping):
            continue
        if "/AA" in value or _dangerous_action(value.get("/A")):
            return True
        pending.extend(_resolve(value.get("/Kids")) or ())
    return False


def _pdf_reader_has_active_content(reader) -> bool:
    """Catalog, page, annotation və AcroForm action-larını bounded audit et."""

    catalog = _resolve(reader.trailer.get("/Root"))
    if not isinstance(catalog, Mapping):
        return True
    if "/OpenAction" in catalog or "/AA" in catalog:
        return True
    names = _resolve(catalog.get("/Names"))
    if isinstance(names, Mapping) and ({"/JavaScript", "/EmbeddedFiles"} & set(names)):
        return True
    acroform = _resolve(catalog.get("/AcroForm"))
    if isinstance(acroform, Mapping):
        if "/AA" in acroform or _field_tree_has_actions(acroform.get("/Fields")):
            return True

    dangerous_subtypes = {"/FileAttachment", "/Movie", "/RichMedia", "/Screen", "/Sound"}
    for page in reader.pages:
        if "/AA" in page:
            return True
        for reference in _resolve(page.get("/Annots")) or ():
            annotation = _resolve(reference)
            if not isinstance(annotation, Mapping):
                continue
            if str(annotation.get("/Subtype", "")) in dangerous_subtypes:
                return True
            if "/AA" in annotation or _dangerous_action(annotation.get("/A")):
                return True
    return False
