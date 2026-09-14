"""DOCX → sual mətni (düsturlar LaTeX, şəkillər lövbərli) — təhlükəsiz oxuyucu.

W3 2026-09-14. Əvvəl Word faylı «makro/embed riski» ilə tam rədd edilirdi;
sahib istəyir ki, şəkilli və düsturlu suallar Word-dən problemsiz gəlsin.
Dünya praktikası (Moodle Word import, Canvas/QTI): sənəd ZIP kimi yoxlanır,
YALNIZ ``.docx`` (makro-suz) qəbul edilir, ``word/vbaProject.bin`` varsa rədd,
xarici (``TargetMode="External"``) şəkil əlaqələri HEÇ VAXT yüklənmir, şəkillər
Pillow ilə identifikasiya + normallaşdırılır (EXIF silinir, >2000 px kiçildilir).

Çıxış:
  * ``text`` — hər paraqraf bir sətir (cədvəl xanaları da ayrı sətir); ``m:oMath``
    → ``\\(…\\)``, ``m:oMathPara`` → ``\\[…\\]``; şəkil yerində ``[[img:N]]`` markeri
    (parser onu ``media_refs``-ə çıxarır — bax ``parsing/media_markers.py``);
  * ``images`` — normallaşdırılmış PNG/JPEG baytları (N → 1-based sıra);
  * ``warnings`` — atılan/çevrilməyən elementlər (preview-da göstərilir).
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings as _pywarnings
import zipfile
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.exams.services.parsing.omml import M_NS, W_NS, omml_to_latex
from apps.exams.services.pdf_math import remap_symbol_pua
from core.upload_security import validate_zip_archive

_ERR = "exams.service.parsing.error"
_WARN = "exams.service.parsing.docx.warning"

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V_NS = "urn:schemas-microsoft-com:vml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"

MAX_IMAGES = 200
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_SIDE_PX = 2000
MARKER_TEMPLATE = "[[img:{index}]]"
MARKER_RE = re.compile(r"\[\[img:(\d{1,4})\]\]")

_RASTER_FORMATS = {"PNG", "JPEG", "MPO", "GIF", "BMP", "TIFF", "WEBP"}


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


@dataclass
class DocxImage:
    index: int
    data: bytes
    content_type: str
    width: int
    height: int
    sha256: str


@dataclass
class DocxExtract:
    text: str
    images: list[DocxImage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    formula_count: int = 0
    formula_fallbacks: list[str] = field(default_factory=list)


class _Walker:
    """Sənəd gövdəsini sıra ilə gəzib sətirləri və şəkilləri toplayır."""

    def __init__(self, document):
        self.document = document
        self.part = document.part
        self.lines: list[str] = []
        self.images: list[DocxImage] = []
        self.warnings: list[str] = []
        self.formula_count = 0
        self.formula_fallbacks: list[str] = []
        self._by_hash: dict[str, int] = {}
        self._skipped_external = 0
        self._skipped_unsupported = 0

    # -- şəkil ------------------------------------------------------------
    def _image_marker(self, r_id: str | None) -> str:
        if not r_id:
            return ""
        rel = self.part.rels.get(r_id)
        if rel is None:
            return ""
        if getattr(rel, "is_external", False):
            # Xarici URL heç vaxt yüklənmir (SSRF/izləmə riski) — yalnız xəbərdarlıq.
            self._skipped_external += 1
            return ""
        try:
            blob = rel.target_part.blob
        except Exception:  # noqa: BLE001 — pozuq əlaqə → şəkil yoxdur
            self._skipped_unsupported += 1
            return ""
        digest = hashlib.sha256(blob).hexdigest()
        index = self._by_hash.get(digest)
        if index is None:
            if len(self.images) >= MAX_IMAGES:
                self._skipped_unsupported += 1
                return ""
            normalized = normalize_image_bytes(blob)
            if normalized is None:
                self._skipped_unsupported += 1
                return ""
            data, content_type, width, height = normalized
            index = len(self.images) + 1
            self.images.append(DocxImage(index, data, content_type, width, height, digest))
            self._by_hash[digest] = index
        return " " + MARKER_TEMPLATE.format(index=index) + " "

    def _drawing_markers(self, node) -> str:
        out = []
        for blip in node.iter(f"{{{A_NS}}}blip"):
            out.append(self._image_marker(blip.get(f"{{{R_NS}}}embed") or blip.get(f"{{{R_NS}}}link")))
        for imagedata in node.iter(f"{{{V_NS}}}imagedata"):
            out.append(self._image_marker(imagedata.get(f"{{{R_NS}}}id")))
        return "".join(out)

    # -- düstur -----------------------------------------------------------
    def _formula(self, node, display: bool) -> str:
        latex, fallbacks = omml_to_latex(node)
        self.formula_count += 1
        if fallbacks:
            self.formula_fallbacks.append(latex)
            self.warnings.append(
                pgettext(_WARN, "formula_partial").format(nodes=", ".join(sorted(set(fallbacks))), preview=latex[:60])
            )
        if not latex.strip():
            return ""
        return f" \\[{latex}\\] " if display else f" \\({latex}\\) "

    # -- mətn -------------------------------------------------------------
    def _run_text(self, run) -> str:
        parts: list[str] = []
        for child in run:
            tag = child.tag
            if tag == _w("t"):
                parts.append(child.text or "")
            elif tag == _w("tab"):
                parts.append(" ")
            elif tag in (_w("br"), _w("cr")):
                parts.append("\n")
            elif tag == _w("sym"):
                parts.append(_symbol_char(child))
            elif tag in (_w("drawing"), _w("pict"), _w("object")):
                parts.append(self._drawing_markers(child))
                parts.append(self._textbox_lines(child))
            elif tag == f"{{{MC_NS}}}AlternateContent":
                choice = child.find(f"{{{MC_NS}}}Choice")
                parts.append(self._drawing_markers(choice if choice is not None else child))
                parts.append(self._textbox_lines(choice if choice is not None else child))
            # w:delText, w:instrText, w:rPr və s. atılır.
        return "".join(parts)

    def _textbox_lines(self, node) -> str:
        """Mətn qutusu (``w:txbxContent``) paraqrafları ayrıca sətir kimi."""

        chunks = []
        for content in node.iter(_w("txbxContent")):
            for paragraph in content.iter(_w("p")):
                text = self._paragraph_text(paragraph)
                if text.strip():
                    chunks.append("\n" + text)
            break  # mc:Choice + mc:Fallback eyni mətni təkrarlayır — birincisi bəsdir
        return "".join(chunks)

    def _paragraph_text(self, paragraph) -> str:
        parts: list[str] = []
        for child in paragraph:
            tag = child.tag
            if tag == _w("r"):
                parts.append(self._run_text(child))
            elif tag == _m("oMath"):
                parts.append(self._formula(child, display=False))
            elif tag == _m("oMathPara"):
                for math in child.findall(_m("oMath")):
                    parts.append(self._formula(math, display=True))
            elif tag in (_w("hyperlink"), _w("ins"), _w("smartTag"), _w("sdt"), _w("sdtContent"), _w("fldSimple")):
                parts.append(self._paragraph_text(child))
            elif tag == _w("del"):
                continue
            elif tag == _w("pPr"):
                continue
        return "".join(parts)

    def _emit(self, text: str) -> None:
        for line in text.split("\n"):
            cleaned = " ".join(line.split())
            if cleaned:
                self.lines.append(cleaned)

    # -- gövdə ------------------------------------------------------------
    def walk(self, container) -> None:
        for child in container:
            tag = child.tag
            if tag == _w("p"):
                self._emit(self._paragraph_text(child))
            elif tag == _w("tbl"):
                for row in child.iter(_w("tr")):
                    for cell in row.findall(_w("tc")):
                        self.walk(cell)
            elif tag in (_w("sdt"), _w("sdtContent"), _w("ins")):
                self.walk(child)
            # w:sectPr, w:bookmarkStart və s. atılır.

    def finish(self) -> DocxExtract:
        if self._skipped_external:
            self.warnings.append(pgettext(_WARN, "images_external_skipped").format(count=self._skipped_external))
        if self._skipped_unsupported:
            self.warnings.append(pgettext(_WARN, "images_unsupported_skipped").format(count=self._skipped_unsupported))
        return DocxExtract(
            text="\n".join(self.lines),
            images=self.images,
            warnings=self.warnings,
            formula_count=self.formula_count,
            formula_fallbacks=self.formula_fallbacks,
        )


def _symbol_char(node) -> str:
    """``w:sym`` — Symbol şrifti PUA kodunu Unicode-a çevir (``remap_symbol_pua``)."""

    code = (node.get(_w("char")) or "").strip()
    if not code:
        return ""
    try:
        value = int(code, 16)
    except ValueError:
        return ""
    if 0x20 <= value < 0xF000:
        value += 0xF000  # Word bəzən PUA-sız yazır (F0xx əvəzinə xx)
    return remap_symbol_pua(chr(value))


def normalize_image_bytes(blob: bytes) -> tuple[bytes, str, int, int] | None:
    """Şəkli Pillow ilə tanı, EXIF-i sil, böyükdürsə kiçilt; ``None`` = dəstəklənmir.

    Raster olmayan (EMF/WMF/SVG) və ya limitdən böyük şəkillər atılır — çağıran
    xəbərdarlıq yazır. Çıxış PNG (alfa/qrafika) və ya JPEG (foto) baytlarıdır.
    """

    if not blob or len(blob) > MAX_IMAGE_BYTES:
        return None
    try:
        with _pywarnings.catch_warnings():
            _pywarnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(blob)) as probe:
                fmt = (probe.format or "").upper()
                width, height = probe.size
                if fmt not in _RASTER_FORMATS or width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    return None
                probe.load()
                oriented = ImageOps.exif_transpose(probe)
                if max(oriented.size) > MAX_SIDE_PX:
                    oriented.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX), Image.LANCZOS)
                has_alpha = oriented.mode in ("RGBA", "LA", "P") and (
                    oriented.mode != "P" or "transparency" in oriented.info
                )
                buffer = io.BytesIO()
                if fmt in ("JPEG", "MPO") and not has_alpha:
                    oriented.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
                    return buffer.getvalue(), "image/jpeg", oriented.width, oriented.height
                target = oriented.convert("RGBA" if has_alpha else "RGB")
                target.save(buffer, format="PNG", optimize=True)
                return buffer.getvalue(), "image/png", target.width, target.height
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, ValueError):
        return None


def docx_safety_check(data: bytes) -> None:
    """ZIP bombası / makro / yanlış paket strukturu yoxlaması (fail-closed)."""

    if not data.startswith(b"PK\x03\x04"):
        raise ValueError(pgettext(_ERR, "file_signature_mismatch"))
    corrupt = pgettext(_ERR, "file_docx_corrupt")
    try:
        validate_zip_archive(io.BytesIO(data))
    except ValidationError as exc:
        detail = "; ".join(exc.messages) if getattr(exc, "messages", None) else str(exc)
        raise ValueError(f"{corrupt} ({detail})") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError(corrupt) from exc
    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
        raise ValueError(corrupt)
    if any(name.lower().startswith("word/vbaproject") for name in names):
        raise ValueError(pgettext(_ERR, "file_has_macros"))


def read_docx(data: bytes) -> DocxExtract:
    """DOCX baytlarından ``DocxExtract`` qur (mətn + şəkillər + xəbərdarlıqlar)."""

    docx_safety_check(data)
    try:
        import docx as python_docx
    except ImportError as exc:  # pragma: no cover — requirements/base.txt-dədir
        raise ValueError(pgettext(_ERR, "pdf_dependency_missing")) from exc
    try:
        document = python_docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — python-docx müxtəlif istisnalar atır
        raise ValueError(pgettext(_ERR, "file_docx_corrupt")) from exc

    walker = _Walker(document)
    walker.walk(document.element.body)
    return walker.finish()


__all__ = [
    "MARKER_RE",
    "MARKER_TEMPLATE",
    "DocxExtract",
    "DocxImage",
    "docx_safety_check",
    "normalize_image_bytes",
    "read_docx",
]
