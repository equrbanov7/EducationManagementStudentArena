"""Manifest segmentlərini təhlükəsiz, annotations-sız PNG kimi render edir."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Mapping, Sequence

import fitz
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .limits import validate_document_budget
from .manifest import Anchor, PageRect, Rect, Segment, SegmentSlice
from .yellow import neutralize_baked_yellow

MIN_DPI = 216
_WHITE_THRESHOLD = 250
_OVERLAP_MAX_HEIGHT = 180
_OVERLAP_MIN_HEIGHT = 12
_OVERLAP_X_SHIFT = 4
_OVERLAP_MIN_INK = 100
_OVERLAP_CONTAINMENT = 0.90
_OVERLAP_IOU = 0.80
_ANNOTATION_MIN_OVERLAP = 0.5
_ANNOTATION_CLUSTER_GAP = 16.0

logger = logging.getLogger(__name__)


def render_segment_png(
    data: bytes,
    segment: Segment,
    *,
    dpi: int = MIN_DPI,
    padding: int = 12,
) -> bytes:
    """Typed segment üçün backward-compatible tək-item wrapper."""

    return render_segments(data, [segment], dpi=dpi, padding=padding)[0]


def render_segment(
    data: bytes,
    segment: Segment | Mapping[str, object],
    *,
    dpi: int = MIN_DPI,
    padding: int = 12,
) -> bytes:
    """Public tək-item wrapper; batch işlərində :func:`render_segments` işlədin."""

    return render_segments(data, [segment], dpi=dpi, padding=padding)[0]


def render_segments(
    data: bytes,
    segments: Sequence[Segment | Mapping[str, object]],
    *,
    dpi: int = MIN_DPI,
    padding: int = 12,
) -> list[bytes]:
    """
    Bütün segmentləri PDF-i yalnız bir dəfə açaraq PNG siyahısına çevirir.

    Cavab Highlight-ları və sarı ``subject=Highlight`` Ink gizlədilir.
    Cavabla əlaqəsiz Ink, FreeText və shape annotasiyaları saxlanılır.
    """

    if dpi < MIN_DPI:
        raise ValueError(f"Render DPI ən azı {MIN_DPI} olmalıdır")
    if padding < 0:
        raise ValueError("Padding mənfi ola bilməz")
    typed = [item if isinstance(item, Segment) else _segment_from_dict(item) for item in segments]
    if any(not segment.slices for segment in typed):
        raise ValueError("Segmentin render dilimi yoxdur")
    if not typed:
        return []

    scale = dpi / 72.0
    with fitz.open(stream=data, filetype="pdf") as document:
        validate_document_budget(document)
        return [_render_typed_segment(document, segment, scale, padding) for segment in typed]


def _render_typed_segment(
    document: fitz.Document,
    segment: Segment,
    scale: float,
    padding: int,
) -> bytes:
    rendered: list[Image.Image] = []
    for fragment in segment.slices:
        if fragment.page_index < 0 or fragment.page_index >= document.page_count:
            raise ValueError(f"Səhifə indeksi PDF xaricindədir: {fragment.page_index}")
        rendered_fragment = _render_fragment(
            document[fragment.page_index],
            fragment,
            segment,
            scale,
        )
        trimmed = _trim_vertical(rendered_fragment)
        if trimmed is not None:
            rendered.append(trimmed)

    if not rendered:
        rendered = [Image.new("RGB", (1, 1), "white")]
    rendered = _deduplicate_adjacent(rendered)
    stitched = _stitch_vertically(rendered)
    trimmed = _trim_all(stitched) or Image.new("RGB", (1, 1), "white")
    output = Image.new("RGB", (trimmed.width + 2 * padding, trimmed.height + 2 * padding), "white")
    output.paste(trimmed, (padding, padding))
    buffer = BytesIO()
    output.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_fragment(
    page: fitz.Page,
    fragment: SegmentSlice,
    segment: Segment,
    scale: float,
) -> Image.Image:
    clip = fitz.Rect(*_coords(fragment.clip))
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        clip=clip,
        alpha=False,
        annots=False,
    )
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image = _overlay_unrelated_annotations(
        image,
        page,
        fragment,
        segment,
        scale,
        pixmap.x,
        pixmap.y,
    )
    image = neutralize_baked_yellow(image, fragment, segment, scale)
    if fragment.masks:
        draw = ImageDraw.Draw(image)
        for mask in fragment.masks:
            intersection = _intersection(mask, fragment.clip)
            if intersection is None:
                continue
            draw.rectangle(
                (
                    round((intersection.x0 - fragment.clip.x0) * scale),
                    round((intersection.y0 - fragment.clip.y0) * scale),
                    round((intersection.x1 - fragment.clip.x0) * scale),
                    round((intersection.y1 - fragment.clip.y0) * scale),
                ),
                fill="white",
            )
    return image


def _overlay_unrelated_annotations(
    image: Image.Image,
    page: fitz.Page,
    fragment: SegmentSlice,
    segment: Segment,
    scale: float,
    base_x: int,
    base_y: int,
) -> Image.Image:
    canvas = image.convert("RGBA")
    clip = fitz.Rect(*_coords(fragment.clip))
    annotations = list(page.annots() or ())
    hidden_xrefs = _answer_annotation_xrefs(annotations, segment)
    for annotation in annotations:
        if annotation.rect.intersects(clip) is False:
            continue
        if annotation.xref in hidden_xrefs:
            continue
        try:
            pixmap = annotation.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=True,
            )
            overlay = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)
            _alpha_composite_clipped(
                canvas,
                overlay,
                pixmap.x - base_x,
                pixmap.y - base_y,
            )
        except Exception as exc:
            logger.info(
                "PDF annotasiyası render olunmadı (page=%s, xref=%s): %s",
                page.number + 1,
                annotation.xref,
                exc,
            )
    return canvas.convert("RGB")


def _answer_annotation_xrefs(
    annotations: Sequence[fitz.Annot],
    segment: Segment,
) -> set[int]:
    hidden = {annotation.xref for annotation in annotations if _is_answer_annotation(annotation, segment)}
    while True:
        joined = {
            annotation.xref
            for annotation in annotations
            if annotation.xref not in hidden
            and _is_answer_mark(annotation)
            and any(_annotations_near(annotation, current) for current in annotations if current.xref in hidden)
        }
        if not joined:
            return hidden
        hidden.update(joined)


def _alpha_composite_clipped(
    canvas: Image.Image,
    overlay: Image.Image,
    left: int,
    top: int,
) -> None:
    destination_x = max(0, left)
    destination_y = max(0, top)
    source_x = max(0, -left)
    source_y = max(0, -top)
    width = min(overlay.width - source_x, canvas.width - destination_x)
    height = min(overlay.height - source_y, canvas.height - destination_y)
    if width <= 0 or height <= 0:
        return
    cropped = overlay.crop((source_x, source_y, source_x + width, source_y + height))
    canvas.alpha_composite(cropped, (destination_x, destination_y))


def _is_answer_annotation(annotation: fitz.Annot, segment: Segment) -> bool:
    if segment.anchor.label not in {"A", "B", "C", "D", "E"}:
        return False
    if not _is_answer_mark(annotation):
        return False
    boxes = [box.rect for box in _segment_boxes(segment) if box.page_index == annotation.parent.number]
    return any(
        region.intersection_area(box) >= _ANNOTATION_MIN_OVERLAP
        for region in _annotation_regions(annotation)
        for box in boxes
    )


def _is_answer_mark(annotation: fitz.Annot) -> bool:
    annotation_type = annotation.type[0]
    if annotation_type == fitz.PDF_ANNOT_HIGHLIGHT:
        return True
    if annotation_type == fitz.PDF_ANNOT_INK:
        subject = str(annotation.info.get("subject") or "").strip().casefold()
        stroke = annotation.colors.get("stroke") or ()
        return subject == "highlight" and _is_yellow_stroke(stroke)
    return False


def _annotations_near(first: fitz.Annot, second: fitz.Annot) -> bool:
    return (
        _axis_gap(first.rect.x0, first.rect.x1, second.rect.x0, second.rect.x1) <= _ANNOTATION_CLUSTER_GAP
        and _axis_gap(first.rect.y0, first.rect.y1, second.rect.y0, second.rect.y1) <= _ANNOTATION_CLUSTER_GAP
    )


def _axis_gap(first_start: float, first_end: float, second_start: float, second_end: float) -> float:
    return max(0.0, max(first_start, second_start) - min(first_end, second_end))


def _annotation_regions(annotation: fitz.Annot) -> tuple[Rect, ...]:
    vertices = annotation.vertices or ()
    if annotation.type[0] == fitz.PDF_ANNOT_HIGHLIGHT and vertices:
        quads = [
            vertices[offset : offset + 4]
            for offset in range(0, len(vertices), 4)
            if len(vertices[offset : offset + 4]) == 4
        ]
        if quads:
            return tuple(
                Rect(
                    min(_point_x(point) for point in quad),
                    min(_point_y(point) for point in quad),
                    max(_point_x(point) for point in quad),
                    max(_point_y(point) for point in quad),
                )
                for quad in quads
            )
    return (Rect(*[float(value) for value in annotation.rect]),)


def _segment_boxes(segment: Segment) -> tuple[PageRect, ...]:
    anchor = segment.anchor
    return (PageRect(anchor.page_index, anchor.rect), *segment.text_boxes)


def _point_x(point: fitz.Point | Sequence[float]) -> float:
    return float(point.x) if hasattr(point, "x") else float(point[0])


def _point_y(point: fitz.Point | Sequence[float]) -> float:
    return float(point.y) if hasattr(point, "y") else float(point[1])


def _is_yellow_stroke(stroke: Sequence[float]) -> bool:
    return len(stroke) >= 3 and stroke[0] >= 0.7 and stroke[1] >= 0.6 and stroke[2] <= 0.5


def _trim_vertical(image: Image.Image) -> Image.Image | None:
    bbox = _content_bbox(image)
    if bbox is None:
        return None
    return image.crop((0, bbox[1], image.width, bbox[3]))


def _trim_all(image: Image.Image) -> Image.Image | None:
    bbox = _content_bbox(image)
    return image.crop(bbox) if bbox else None


def _content_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    grayscale = image.convert("L")
    ink = grayscale.point(lambda value: 255 if value < _WHITE_THRESHOLD else 0)
    return ink.getbbox()


def _stitch_vertically(images: list[Image.Image]) -> Image.Image:
    width = max(image.width for image in images)
    height = sum(image.height for image in images)
    output = Image.new("RGB", (width, height), "white")
    y = 0
    for image in images:
        output.paste(image, (0, y))
        y += image.height
    return output


def _deduplicate_adjacent(images: list[Image.Image]) -> list[Image.Image]:
    if len(images) < 2:
        return images
    result = [images[0]]
    for current in images[1:]:
        overlap = _near_duplicate_overlap(result[-1], current)
        if not overlap:
            result.append(current)
            continue
        if current.height <= overlap * 3:
            continue
        remainder = _trim_vertical(current.crop((0, overlap, current.width, current.height)))
        if remainder is not None:
            result.append(remainder)
    return result


def _near_duplicate_overlap(previous: Image.Image, current: Image.Image) -> int:
    if previous.width != current.width:
        return 0
    previous_mask = _ink_mask(previous)
    current_mask = _ink_mask(current)
    max_height = min(_OVERLAP_MAX_HEIGHT, previous.height, current.height)
    best: tuple[float, int] = (0.0, 0)
    for height in range(_OVERLAP_MIN_HEIGHT, max_height + 1):
        previous_band = previous_mask.crop((0, previous.height - height, previous.width, previous.height))
        current_band = current_mask.crop((0, 0, current.width, height))
        for shift in range(-_OVERLAP_X_SHIFT, _OVERLAP_X_SHIFT + 1):
            first, second = _shifted_pair(previous_band, current_band, shift)
            first_ink = _ink_count(first)
            second_ink = _ink_count(second)
            if min(first_ink, second_ink) < _OVERLAP_MIN_INK:
                continue
            intersection = _ink_count(ImageChops.multiply(first, second))
            union = _ink_count(ImageChops.lighter(first, second))
            containment = intersection / min(first_ink, second_ink)
            iou = intersection / union if union else 0.0
            if containment >= _OVERLAP_CONTAINMENT and iou >= _OVERLAP_IOU:
                score = containment + iou
                if score > best[0]:
                    best = (score, height)
    return best[1]


def _ink_mask(image: Image.Image) -> Image.Image:
    grayscale = image.convert("L")
    binary = grayscale.point(lambda value: 255 if value < _WHITE_THRESHOLD else 0)
    return binary.filter(ImageFilter.MaxFilter(3))


def _shifted_pair(first: Image.Image, second: Image.Image, shift: int) -> tuple[Image.Image, Image.Image]:
    if shift >= 0:
        return (
            first.crop((shift, 0, first.width, first.height)),
            second.crop((0, 0, second.width - shift, second.height)),
        )
    return (
        first.crop((0, 0, first.width + shift, first.height)),
        second.crop((-shift, 0, second.width, second.height)),
    )


def _ink_count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def _intersection(first: Rect, second: Rect) -> Rect | None:
    x0 = max(first.x0, second.x0)
    y0 = max(first.y0, second.y0)
    x1 = min(first.x1, second.x1)
    y1 = min(first.y1, second.y1)
    return Rect(x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def _coords(rect: Rect) -> tuple[float, float, float, float]:
    return rect.x0, rect.y0, rect.x1, rect.y1


def _segment_from_dict(value: Mapping[str, object]) -> Segment:
    raw_slices = value.get("slices")
    if not isinstance(raw_slices, list):
        raise ValueError("Segment slices siyahısı saxlamır")
    slices: list[SegmentSlice] = []
    for raw_slice in raw_slices:
        if not isinstance(raw_slice, Mapping):
            raise ValueError("Segment slice obyekti yanlışdır")
        page_index = raw_slice.get("page_index")
        clip = raw_slice.get("clip")
        masks = raw_slice.get("masks", [])
        if not isinstance(page_index, int) or not _is_coords(clip) or not isinstance(masks, list):
            raise ValueError("Segment slice koordinatları yanlışdır")
        if not all(_is_coords(mask) for mask in masks):
            raise ValueError("Segment mask koordinatları yanlışdır")
        slices.append(
            SegmentSlice(
                page_index=page_index,
                clip=Rect(*[float(number) for number in clip]),
                masks=tuple(Rect(*[float(number) for number in mask]) for mask in masks),
            )
        )
    anchor = _anchor_from_dict(value.get("anchor"))
    text_boxes = _page_rects_from_dict(value.get("text_boxes", []))
    return Segment(str(value.get("text") or ""), anchor, tuple(slices), text_boxes)


def _anchor_from_dict(value: object) -> Anchor:
    if not isinstance(value, Mapping):
        return Anchor("", 0, Rect(0, 0, 0, 0), Rect(0, 0, 0, 0))
    label = value.get("label")
    page_index = value.get("page_index")
    rect = value.get("rect")
    line_rect = value.get("line_rect")
    if (
        not isinstance(label, str)
        or not isinstance(page_index, int)
        or not _is_coords(rect)
        or not _is_coords(line_rect)
    ):
        raise ValueError("Segment anchor koordinatları yanlışdır")
    return Anchor(
        label,
        page_index,
        Rect(*[float(number) for number in rect]),
        Rect(*[float(number) for number in line_rect]),
    )


def _page_rects_from_dict(value: object) -> tuple[PageRect, ...]:
    if not isinstance(value, list):
        raise ValueError("Segment text_boxes siyahısı yanlışdır")
    boxes: list[PageRect] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("Segment text box obyekti yanlışdır")
        page_index = item.get("page_index")
        rect = item.get("rect")
        if not isinstance(page_index, int) or not _is_coords(rect):
            raise ValueError("Segment text box koordinatları yanlışdır")
        boxes.append(
            PageRect(
                page_index,
                Rect(*[float(number) for number in rect]),
            )
        )
    return tuple(boxes)


def _is_coords(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 4
        and all(isinstance(number, (int, float)) for number in value)
    )
