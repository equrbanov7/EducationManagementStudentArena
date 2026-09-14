"""PDF mətn-fallback yolunda gömülü raster şəkillərin sual bölgəsinə görə çıxarılması.

W4 2026-09-14 (w3import yarımçıq 6). Vizual-first PDF axını (layout inamlı)
sual/variantı bütöv şəkil kimi kəsir; layout inamsız olanda (`LayoutConfidenceError`)
mətn fallback-ına düşülürdü və sənədin içindəki şəkillər İTİRDİ. Bu modul həmin
fallback üçün PyMuPDF ilə səhifədəki şəkil yerləşimlərini (`page.get_images` +
`page.get_image_rects`) tapır, mətn sətirlərindən sual (`N.`) və variant (`A)`)
lövbərlərini çıxarır və hər şəkli bölgəsinə görə suala (stem) və ya varianta
bağlayır. Nəticə DOCX oxuyucusu ilə EYNİ formadadır: mətnə ``[[img:N]]``
markeri, şəkillər ``normalize_image_bytes`` ilə eyni ölçü/format qapısından
keçmiş ``DocxImage`` obyektləri — sonrası (``media_refs`` → manifest bağlama →
model ``image`` sahəsi) DOCX bundle ilə paylaşılır (``import_media_pdf``).

Bölgə qaydası (tək sütunlu sənəd fərziyyəsi):
  * sual bölgəsi = lövbər sətrinin üstündən növbəti sual lövbərinə qədər
    (səhifə keçidi daxil) — şəkil mərkəzi hansı bölgəyə düşürsə o sualındır;
  * bölgə daxilində şəkilin ÜSTÜ hansı variant sətrinin üstündən aşağıdadırsa
    həmin varianta, əks halda (variantlardan yuxarı başlayırsa) stem-ə bağlanır;
  * ilk sualdan əvvəlki (başlıq/loqo) və səhifənin ≥ 80 %-ni örtən (skan fonu)
    şəkillər atılır; dublikat obyekt (eyni xref) bir dəfə saxlanılır.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from django.utils.translation import pgettext

from apps.exams.constants import OPTION_RE, QUESTION_RE
from apps.exams.services.parsing.docx_reader import MARKER_TEMPLATE, MAX_IMAGES, DocxImage, normalize_image_bytes
from apps.exams.services.parsing.extraction._deps import fitz

_WARN = "exams.service.parsing.docx.warning"
# Səhifənin bu payından böyük şəkil skan fonu / su nişanı sayılır.
_FULL_PAGE_RATIO = 0.8
# Bu ölçüdən kiçik (pt) yerləşimlər bəzək (bullet, xətt) sayılır.
_MIN_PLACEMENT_PT = 8.0
# Variant sətri ilə eyni xəttdə başlayan şəkil üçün dözüm (pt).
_OPTION_TOP_TOLERANCE_PT = 3.0
_MARKER_RE = re.compile(r"\[\[img:(\d{1,4})\]\]")


@dataclass(frozen=True)
class _Anchor:
    page: int
    y0: float
    kind: str  # "question" | "option"
    key: str  # sual nömrəsi və ya variant etiketi


@dataclass(frozen=True)
class _Placement:
    page: int
    y0: float
    y1: float
    xref: int


@dataclass
class PdfImageExtract:
    text: str
    images: list[DocxImage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # (sual nömrəsi, "stem"|etiket, şəkil indeksi) — test/diaqnostika üçün.
    placements: list[tuple[str, str, int]] = field(default_factory=list)


def pdf_has_raster_images(data: bytes) -> bool:
    """Ucuz ön-yoxlama: sənəddə ən azı bir şəkil obyekti yerləşdirilibmi."""

    if fitz is None or not data:
        return False
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            return any(page.get_images(full=True) for page in document)
    except Exception:  # noqa: BLE001 — pozuq PDF → mətn yolu öz xətasını verir
        return False


def _read_anchors(document) -> list[_Anchor]:
    anchors: list[_Anchor] = []
    for page_index, page in enumerate(document):
        page_lines: list[tuple[float, float, str]] = []
        try:
            layout = page.get_text("dict")
        except Exception:  # noqa: BLE001
            continue
        for block in layout.get("blocks", ()):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", ()):
                text = "".join(str(span.get("text", "")) for span in line.get("spans", ())).strip()
                if not text:
                    continue
                x0, y0, _x1, _y1 = line["bbox"]
                page_lines.append((round(float(y0), 2), float(x0), text))
        page_lines.sort()
        for y0, _x0, text in page_lines:
            m_q = QUESTION_RE.match(text)
            if m_q:
                anchors.append(_Anchor(page_index, y0, "question", m_q.group(1)))
                continue
            m_o = OPTION_RE.match(text)
            if m_o:
                anchors.append(_Anchor(page_index, y0, "option", m_o.group(2).upper()))
    return anchors


def _read_placements(document) -> tuple[list[_Placement], int]:
    placements: list[_Placement] = []
    skipped = 0
    for page_index, page in enumerate(document):
        page_area = float(page.rect.width * page.rect.height) or 1.0
        # Eyni obyekt səhifədə bir neçə dəfə yerləşdirilibsə `get_images` onu hər
        # yerləşim üçün təkrar sadalayır — xref bir dəfə emal olunur, rect-lər tam gəlir.
        seen_xrefs: set[int] = set()
        for image in page.get_images(full=True):
            xref = int(image[0])
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                rects = page.get_image_rects(xref)
            except Exception:  # noqa: BLE001
                rects = []
            for rect in rects:
                width = float(rect.x1 - rect.x0)
                height = float(rect.y1 - rect.y0)
                if width < _MIN_PLACEMENT_PT or height < _MIN_PLACEMENT_PT:
                    continue
                if width * height >= page_area * _FULL_PAGE_RATIO:
                    skipped += 1
                    continue
                placements.append(_Placement(page_index, float(rect.y0), float(rect.y1), xref))
    placements.sort(key=lambda item: (item.page, item.y0))
    return placements, skipped


def _image_bytes(document, xref: int) -> bytes | None:
    """Obyektin xam baytları (JPEG/PNG…); tanınmasa Pixmap → PNG."""

    try:
        raw = document.extract_image(xref)
    except Exception:  # noqa: BLE001
        raw = None
    if raw and raw.get("image"):
        return bytes(raw["image"])
    try:
        pixmap = fitz.Pixmap(document, xref)
        if pixmap.n - pixmap.alpha >= 4:
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        return pixmap.tobytes("png")
    except Exception:  # noqa: BLE001
        return None


def _locate(anchors: list[_Anchor], placement: _Placement) -> tuple[str, str] | None:
    """Şəkil yerləşimi → (sual nömrəsi, "stem"|etiket); ilk sualdan əvvəldirsə None."""

    center = (placement.page, (placement.y0 + placement.y1) / 2)
    question_no = None
    slot = "stem"
    for anchor in anchors:
        position = (anchor.page, anchor.y0)
        if anchor.kind == "question":
            if position > center:
                break
            question_no, slot = anchor.key, "stem"
        elif question_no is not None:
            # Variant: şəkilin ÜSTÜ variant sətrinin üstündən aşağıdadırsa ona aiddir.
            if position > center:
                break
            if (anchor.page, anchor.y0 - _OPTION_TOP_TOLERANCE_PT) <= (placement.page, placement.y0):
                slot = anchor.key
    if question_no is None:
        return None
    return question_no, slot


def _insert_marker(lines: list[str], question_no: str, slot: str, index: int, cursor: dict[str, int]) -> bool:
    """Normallaşdırılmış mətndə sual/variant sətrinin sonuna markeri yaz."""

    marker = " " + MARKER_TEMPLATE.format(index=index)
    start = cursor.get(question_no, 0)
    q_line = None
    for line_no in range(start, len(lines)):
        m_q = QUESTION_RE.match(lines[line_no])
        if m_q and m_q.group(1) == question_no:
            q_line = line_no
            break
    if q_line is None:
        return False
    cursor[question_no] = q_line
    if slot != "stem":
        for line_no in range(q_line + 1, len(lines)):
            if QUESTION_RE.match(lines[line_no]):
                break
            m_o = OPTION_RE.match(lines[line_no])
            if m_o and m_o.group(2).upper() == slot:
                lines[line_no] = lines[line_no].rstrip() + marker
                return True
        # Variant sətri mətndə tapılmadı (birləşmiş sətir) → stem-ə bağla.
    lines[q_line] = lines[q_line].rstrip() + marker
    return True


def extract_pdf_question_images(data: bytes, text: str) -> PdfImageExtract:
    """PDF baytları + çıxarılmış (normallaşdırılmış) mətn → markerli mətn + şəkillər."""

    result = PdfImageExtract(text=text or "")
    if fitz is None or not data or not (text or "").strip():
        return result
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001
        return result
    with document:
        anchors = _read_anchors(document)
        placements, skipped_full_page = _read_placements(document)
        if not anchors or not placements:
            return result

        lines = text.splitlines()
        cursor: dict[str, int] = {}
        by_xref: dict[int, int] = {}
        by_hash: dict[str, int] = {}
        unsupported = skipped_full_page
        unanchored = 0
        for placement in placements:
            located = _locate(anchors, placement)
            if located is None:
                unanchored += 1
                continue
            index = by_xref.get(placement.xref)
            if index is None:
                if len(result.images) >= MAX_IMAGES:
                    unsupported += 1
                    continue
                blob = _image_bytes(document, placement.xref)
                if not blob:
                    unsupported += 1
                    continue
                digest = hashlib.sha256(blob).hexdigest()
                index = by_hash.get(digest)
                if index is None:
                    normalized = normalize_image_bytes(blob)
                    if normalized is None:
                        unsupported += 1
                        continue
                    payload, content_type, width, height = normalized
                    index = len(result.images) + 1
                    result.images.append(
                        DocxImage(
                            index=index,
                            data=payload,
                            content_type=content_type,
                            width=width,
                            height=height,
                            sha256=hashlib.sha256(payload).hexdigest(),
                        )
                    )
                    by_hash[digest] = index
                by_xref[placement.xref] = index
            question_no, slot = located
            if _insert_marker(lines, question_no, slot, index, cursor):
                result.placements.append((question_no, slot, index))
            else:
                unanchored += 1

    used = {index for _q, _s, index in result.placements}
    if not used:
        result.images = []
        result.placements = []
    else:
        # Heç bir yerə bağlanmayan şəkil bundle-a düşmür (indekslər sıx qalır).
        remap: dict[int, int] = {}
        kept: list[DocxImage] = []
        for image in result.images:
            if image.index in used:
                remap[image.index] = len(kept) + 1
                image.index = len(kept) + 1
                kept.append(image)
        result.images = kept
        result.placements = [(q, s, remap[i]) for q, s, i in result.placements]
        result.text = _MARKER_RE.sub(
            lambda match: MARKER_TEMPLATE.format(index=remap.get(int(match.group(1)), int(match.group(1)))),
            "\n".join(lines),
        )
    if unsupported:
        result.warnings.append(pgettext(_WARN, "images_unsupported_skipped").format(count=unsupported))
    if unanchored:
        result.warnings.append(pgettext(_WARN, "pdf_images_unanchored_skipped").format(count=unanchored))
    return result


__all__ = ["PdfImageExtract", "extract_pdf_question_images", "pdf_has_raster_images"]
