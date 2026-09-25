"""Göndəriş fayllarından mətn çıxarılması — kiçik, MƏHDUD, təhlükəsiz ekstraktor.

İmtahan modulunun daxili çıxarıcısı public deyil, ona görə burada öz sadə
çıxarıcımız var. Heç bir fayl İCRA olunmur; hər formatın ölçü/səhifə/üzv sayı
limiti var, xəta faylı «atlanmış» edir (yoxlama dayanmır):

* mətn/kod faylları — birbaşa oxunur (UTF-8, xətalı bayt əvəzlənir);
* ``.ipynb`` — yalnız hüceyrə mənbələri (çıxışlar yox);
* PDF — ``pypdf`` (``strict=False``), ən çox ``MAX_PDF_PAGES`` səhifə;
  şifrəli PDF atlanır;
* DOCX/PPTX/ODT/ODP — ZIP içindən yalnız mətn XML-i, regex ilə (XML parser
  YOXDUR → XXE/entity bombası mümkün deyil); üzv ölçüsü və sayı məhduddur;
* şəkil, arxiv, köhnə OLE ofis faylları — mətn çıxarılmır, yalnız SHA-256
  (eyni fayl) yoxlaması işləyir.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
import zipfile

logger = logging.getLogger(__name__)

#: Bu ölçüdən böyük faylın mətni çıxarılmır (yalnız heş müqayisəsi).
MAX_EXTRACT_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 60
MAX_TEXT_CHARS = 300_000
_MAX_ZIP_MEMBERS = 2_000
_MAX_XML_BYTES = 20 * 1024 * 1024

TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".py",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".cs",
        ".go",
        ".rs",
        ".kt",
        ".swift",
        ".sql",
        ".r",
        ".m",
        ".json",
        ".yaml",
        ".yml",
        ".tex",
        ".rtf",
    }
)
OOXML_EXTENSIONS = frozenset({".docx", ".pptx", ".odt", ".odp"})

SKIP_TOO_LARGE = "too_large"
SKIP_UNSUPPORTED = "unsupported"
SKIP_ENCRYPTED = "encrypted"
SKIP_UNREADABLE = "unreadable"

_DOCX_TEXT = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")
_PPTX_TEXT = re.compile(r"<a:t(?:\s[^>]*)?>([^<]*)</a:t>")
_ODF_TAG = re.compile(r"<[^>]+>")
_SLIDE_NAME = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def _read_bytes(field_file, limit: int) -> bytes:
    field_file.open("rb")
    try:
        return field_file.read(limit + 1)
    finally:
        field_file.close()


def _decode(raw: bytes) -> str:
    """UTF-16 yalnız BOM ilə tanınır (BOM-suz cüt uzunluqlu bayt dəsti də «UTF-16» kimi açılardı)."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8-sig", errors="replace")


def _notebook_text(raw: bytes) -> str:
    try:
        data = json.loads(_decode(raw))
    except (ValueError, TypeError):
        return ""
    cells = data.get("cells") if isinstance(data, dict) else None
    parts = []
    for cell in cells or []:
        source = cell.get("source") if isinstance(cell, dict) else None
        if isinstance(source, list):
            parts.append("".join(str(item) for item in source))
        elif isinstance(source, str):
            parts.append(source)
    return "\n".join(parts)


def _pdf_text(raw: bytes) -> tuple[str, str | None]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw), strict=False)
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "", SKIP_ENCRYPTED
        except Exception:
            return "", SKIP_ENCRYPTED
    parts, total = [], 0
    for index, page in enumerate(reader.pages):
        if index >= MAX_PDF_PAGES or total >= MAX_TEXT_CHARS:
            break
        try:
            text = page.extract_text() or ""
        except Exception:  # bir səhifə sınıq ola bilər — qalanları oxunur
            text = ""
        parts.append(text)
        total += len(text)
    return "\n".join(parts), None


def _zip_member(archive, name) -> str:
    info = archive.getinfo(name)
    if info.file_size > _MAX_XML_BYTES:
        return ""
    with archive.open(info) as handle:
        return handle.read(_MAX_XML_BYTES).decode("utf-8", errors="replace")


def _office_text(raw: bytes, extension: str) -> tuple[str, str | None]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) > _MAX_ZIP_MEMBERS:
            return "", SKIP_UNREADABLE
        if extension == ".docx":
            xml = _zip_member(archive, "word/document.xml") if "word/document.xml" in names else ""
            return html.unescape(" ".join(_DOCX_TEXT.findall(xml))), None
        if extension == ".pptx":
            slides = sorted(
                (int(match.group(1)), name) for name in names if (match := _SLIDE_NAME.match(name)) is not None
            )
            parts = [" ".join(_PPTX_TEXT.findall(_zip_member(archive, name))) for _index, name in slides]
            return html.unescape("\n".join(parts)), None
        xml = _zip_member(archive, "content.xml") if "content.xml" in names else ""
        return html.unescape(_ODF_TAG.sub(" ", xml)), None


def extract_text(field_file, *, extension: str, size: int) -> tuple[str, str | None]:
    """``(mətn, atlanma_səbəbi)`` — mətn çıxarılmayanda səbəb kodu (``too_large`` / ``unsupported`` …)."""
    extension = (extension or "").lower()
    if size and size > MAX_EXTRACT_BYTES:
        return "", SKIP_TOO_LARGE
    if extension not in TEXT_EXTENSIONS | OOXML_EXTENSIONS | {".pdf", ".ipynb"}:
        return "", SKIP_UNSUPPORTED
    try:
        raw = _read_bytes(field_file, MAX_EXTRACT_BYTES)
        if len(raw) > MAX_EXTRACT_BYTES:
            return "", SKIP_TOO_LARGE
        if extension == ".ipynb":
            return _notebook_text(raw)[:MAX_TEXT_CHARS], None
        if extension in TEXT_EXTENSIONS:
            return _decode(raw)[:MAX_TEXT_CHARS], None
        if extension == ".pdf":
            text, reason = _pdf_text(raw)
            return text[:MAX_TEXT_CHARS], reason
        text, reason = _office_text(raw, extension)
        return text[:MAX_TEXT_CHARS], reason
    except Exception:  # sınıq/qəsdən pozulmuş fayl — yoxlama dayanmır
        logger.info("subject_folder: mətn çıxarılmadı (%s)", extension, exc_info=True)
        return "", SKIP_UNREADABLE


__all__ = [
    "MAX_EXTRACT_BYTES",
    "MAX_PDF_PAGES",
    "MAX_TEXT_CHARS",
    "SKIP_ENCRYPTED",
    "SKIP_TOO_LARGE",
    "SKIP_UNREADABLE",
    "SKIP_UNSUPPORTED",
    "extract_text",
]
