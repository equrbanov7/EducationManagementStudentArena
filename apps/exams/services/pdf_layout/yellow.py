"""Flattened sarı cavab işarələrini geometriya daxilində təhlükəsiz aşkarlayır."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Sequence

import fitz
from PIL import Image

from .manifest import Option, PageRect, Rect, Segment, SegmentSlice

_DETECTION_SCALE = 2.0
_DETECTION_PAD = 2.0
_NEUTRALIZE_PAD = 4.0
_MIN_YELLOW_PIXELS = 24
_STRONG_RATIO = 0.10
_WEAK_RATIO = 0.02
_PAGE_CACHE_SIZE = 3


@dataclass(frozen=True, slots=True)
class BakedAnswerEvidence:
    labels: tuple[str, ...]
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class _Raster:
    image: Image.Image
    origin_x: int
    origin_y: int
    scale: float


class BakedAnswerDetector:
    """PDF səhifə rasterlərini lazy cache edib variant qutularını ölçür."""

    def __init__(self, document: fitz.Document):
        self.document = document
        self._pages: OrderedDict[int, _Raster] = OrderedDict()

    def detect(self, options: Sequence[Option]) -> BakedAnswerEvidence:
        scores = [(option.label, *self._option_score(option)) for option in options]
        strong = [label for label, yellow, ratio in scores if yellow >= _MIN_YELLOW_PIXELS and ratio >= _STRONG_RATIO]
        weak = [
            label
            for label, yellow, ratio in scores
            if label not in strong and yellow >= _MIN_YELLOW_PIXELS and ratio >= _WEAK_RATIO
        ]
        if weak:
            return BakedAnswerEvidence((), ambiguous=True)
        return BakedAnswerEvidence(tuple(strong))

    def _option_score(self, option: Option) -> tuple[int, float]:
        yellow = 0
        area = 0
        pages = {box.page_index for box in _segment_boxes(option.segment)}
        for page_index in pages:
            raster = self._page(page_index)
            regions = _regions(option.segment, page_index, _DETECTION_PAD)
            page_yellow, page_area = _score_regions(raster, regions)
            yellow += page_yellow
            area += page_area
        return yellow, yellow / area if area else 0.0

    def _page(self, page_index: int) -> _Raster:
        cached = self._pages.get(page_index)
        if cached is not None:
            self._pages.move_to_end(page_index)
            return cached
        pixmap = self.document[page_index].get_pixmap(
            matrix=fitz.Matrix(_DETECTION_SCALE, _DETECTION_SCALE),
            colorspace=fitz.csRGB,
            alpha=False,
            annots=False,
        )
        raster = _Raster(
            image=Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples),
            origin_x=pixmap.x,
            origin_y=pixmap.y,
            scale=_DETECTION_SCALE,
        )
        self._pages[page_index] = raster
        while len(self._pages) > _PAGE_CACHE_SIZE:
            self._pages.popitem(last=False)
        return raster


def neutralize_baked_yellow(
    image: Image.Image,
    fragment: SegmentSlice,
    segment: Segment,
    scale: float,
) -> Image.Image:
    """Güclü baked cavab fonunu ağardır, qara mətn piksellərinə toxunmur."""

    if segment.anchor.label not in {"A", "B", "C", "D", "E"}:
        return image
    regions = _regions(segment, fragment.page_index, _NEUTRALIZE_PAD)
    if not regions:
        return image
    raster = _Raster(
        image=image,
        origin_x=round(fragment.clip.x0 * scale),
        origin_y=round(fragment.clip.y0 * scale),
        scale=scale,
    )
    yellow, area = _score_regions(raster, regions)
    if yellow < _MIN_YELLOW_PIXELS or not area or yellow / area < _STRONG_RATIO:
        return image

    cleaned = image.copy()
    pixels = cleaned.load()
    seed_bounds = _pixel_bounds(raster, regions)
    for component in _yellow_components(cleaned):
        if any(_inside_any(x, y, seed_bounds) for x, y in component):
            for x, y in component:
                pixels[x, y] = (255, 255, 255)
    return cleaned


def _score_regions(raster: _Raster, regions: Sequence[Rect]) -> tuple[int, int]:
    yellow = 0
    area = 0
    pixels = raster.image.load()
    for bounds in _pixel_bounds(raster, regions):
        region_area = max(0, bounds[2] - bounds[0]) * max(0, bounds[3] - bounds[1])
        area += region_area
        yellow += sum(
            _is_yellow(pixels[x, y]) for y in range(bounds[1], bounds[3]) for x in range(bounds[0], bounds[2])
        )
    return yellow, area


def _pixel_bounds(raster: _Raster, regions: Sequence[Rect]) -> tuple[tuple[int, int, int, int], ...]:
    bounds: list[tuple[int, int, int, int]] = []
    for rect in regions:
        x0 = max(0, int(rect.x0 * raster.scale) - raster.origin_x)
        y0 = max(0, int(rect.y0 * raster.scale) - raster.origin_y)
        x1 = min(raster.image.width, round(rect.x1 * raster.scale) - raster.origin_x)
        y1 = min(raster.image.height, round(rect.y1 * raster.scale) - raster.origin_y)
        if x1 > x0 and y1 > y0:
            bounds.append((x0, y0, x1, y1))
    return tuple(bounds)


def _regions(segment: Segment, page_index: int, padding: float) -> tuple[Rect, ...]:
    boxes = [box.rect for box in _segment_boxes(segment) if box.page_index == page_index]
    rows: list[list[Rect]] = []
    for box in sorted(boxes, key=lambda item: (item.y0, item.x0)):
        matching = next((row for row in rows if any(_same_line(box, item) for item in row)), None)
        if matching is None:
            rows.append([box])
        else:
            matching.append(box)
    return tuple(
        Rect(
            min(box.x0 for box in row) - padding,
            min(box.y0 for box in row) - padding,
            max(box.x1 for box in row) + padding,
            max(box.y1 for box in row) + padding,
        )
        for row in rows
    )


def _segment_boxes(segment: Segment) -> tuple[PageRect, ...]:
    anchor = segment.anchor
    row_boxes = tuple(
        box
        for box in segment.text_boxes
        if box.page_index == anchor.page_index and box.rect.intersection_area(anchor.line_rect) > 0
    )
    return (PageRect(anchor.page_index, anchor.rect), *row_boxes)


def _same_line(first: Rect, second: Rect) -> bool:
    overlap = min(first.y1, second.y1) - max(first.y0, second.y0)
    return overlap > 0 or abs((first.y0 + first.y1) - (second.y0 + second.y1)) <= 5.0


def _is_yellow(value: Sequence[int]) -> bool:
    red, green, blue = value[:3]
    return red >= 160 and green >= 140 and blue + 25 <= min(red, green) and abs(red - green) <= 100


def _yellow_components(image: Image.Image) -> tuple[tuple[tuple[int, int], ...], ...]:
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    components: list[tuple[tuple[int, int], ...]] = []
    for y in range(height):
        for x in range(width):
            offset = y * width + x
            if visited[offset] or not _is_yellow(pixels[x, y]):
                continue
            visited[offset] = 1
            stack = [(x, y)]
            component: list[tuple[int, int]] = []
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        neighbor_offset = neighbor_y * width + neighbor_x
                        if visited[neighbor_offset] or not _is_yellow(pixels[neighbor_x, neighbor_y]):
                            continue
                        visited[neighbor_offset] = 1
                        stack.append((neighbor_x, neighbor_y))
            components.append(tuple(component))
    return tuple(components)


def _inside_any(
    x: int,
    y: int,
    bounds: Sequence[tuple[int, int, int, int]],
) -> bool:
    return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in bounds)
