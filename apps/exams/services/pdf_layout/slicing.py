"""Anchor row Voronoi sərhədlərindən page fragment dilimləri qurur."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .manifest import Rect, SegmentSlice

_SAME_ROW_TOLERANCE = 2.5
_ROW_MASK_MARGIN = 1.5
_LABEL_MASK_MARGIN = 2.0
_CONTINUATION_MARGIN = 4.0
_CONTENT_JOIN_GAP = 2.0
_CONTENT_PAD = 0.4
_SPILL_MASK_PAD = 2.0
_PRESERVE_PAD = 0.5
_NEIGHBOR_CENTER_GAP = 30.0


@dataclass(frozen=True, slots=True)
class _Row:
    page_index: int
    anchors: tuple[Any, ...]
    global_center: float


@dataclass(frozen=True, slots=True)
class _Bounds:
    top: float
    bottom: float
    row_index: int


@dataclass(frozen=True, slots=True)
class SlicePlan:
    page_rects: tuple[Rect, ...]
    page_offsets: tuple[float, ...]
    anchor_bounds: dict[int, _Bounds]

    def segment_slices(
        self,
        start: Any,
        end: Any | None,
        text_boxes: Sequence[Any] = (),
        exclude_boxes: Sequence[Any] = (),
    ) -> tuple[SegmentSlice, ...]:
        bounds = self.anchor_bounds[id(start)]
        interval_top, interval_bottom = bounds.top, bounds.bottom
        interval_top, interval_bottom = self._expand_start_page_content(
            start.line.page_index,
            interval_top,
            interval_bottom,
            text_boxes,
        )
        if getattr(start, "is_postfix", False):
            interval_bottom = self._include_postfix_content(
                start.line.page_index,
                interval_bottom,
                text_boxes,
            )
        neighbor_bottom = self._lower_neighbor_boundary(text_boxes, exclude_boxes)
        if neighbor_bottom is not None:
            interval_bottom = min(interval_bottom, neighbor_bottom)
        for box in text_boxes:
            if box.page_index == start.line.page_index:
                continue
            page_top = self.page_offsets[box.page_index]
            page_rect = self.page_rects[box.page_index]
            box_top = page_top + box.rect.y0 - page_rect.y0
            box_bottom = page_top + box.rect.y1 - page_rect.y0
            interval_top = min(interval_top, box_top - _CONTINUATION_MARGIN)
            interval_bottom = max(interval_bottom, box_bottom + _CONTINUATION_MARGIN)

        slices: list[SegmentSlice] = []
        for page_index, page_rect in enumerate(self.page_rects):
            page_top = self.page_offsets[page_index]
            page_bottom = page_top + page_rect.height
            overlap_top = max(interval_top, page_top)
            overlap_bottom = min(interval_bottom, page_bottom)
            if overlap_bottom <= overlap_top:
                continue

            top = page_rect.y0 + overlap_top - page_top
            bottom = page_rect.y0 + overlap_bottom - page_top
            masks: list[Rect] = []
            if page_index == start.line.page_index:
                masks.append(
                    Rect(
                        page_rect.x0,
                        max(top, start.line.rect.y0 - _ROW_MASK_MARGIN),
                        min(page_rect.x1, start.rect.x1 + _LABEL_MASK_MARGIN),
                        min(bottom, start.line.rect.y1 + _ROW_MASK_MARGIN),
                    )
                )
            if (
                end is not None
                and id(end) in self.anchor_bounds
                and self.anchor_bounds[id(end)].row_index == bounds.row_index
                and page_index == end.line.page_index
            ):
                masks.append(
                    Rect(
                        max(page_rect.x0, end.rect.x0 - _LABEL_MASK_MARGIN),
                        max(top, end.line.rect.y0 - _ROW_MASK_MARGIN),
                        page_rect.x1,
                        min(bottom, end.line.rect.y1 + _ROW_MASK_MARGIN),
                    )
                )
            elif end is not None and page_index == end.line.page_index and bottom > end.line.rect.y0:
                # Hündür düstur əvvəlki segmentin midpoint sərhədini keçəndə
                # crop böyüyür. Növbəti row-un anchor/inline mətnini bu böyümə
                # daxilində ağart ki, məsələn A variantı stem-ə sızmasın.
                #
                # Label əvvəlki məzmunun sonunda yerləşirsə (``formula D)``),
                # həmin məzmun cari varianta aiddir. Bu halda bütün sətri yox,
                # yalnız postfix label və ondan sonrakı hissəni maskalamaq
                # lazımdır.
                is_postfix_end = bool(getattr(end, "is_postfix", False))
                mask_x0 = end.rect.x0 - _LABEL_MASK_MARGIN if is_postfix_end else end.line.rect.x0 - _LABEL_MASK_MARGIN
                mask_x1 = page_rect.x1 if is_postfix_end else end.line.rect.x1 + _LABEL_MASK_MARGIN
                masks.append(
                    Rect(
                        max(page_rect.x0, mask_x0),
                        max(top, end.line.rect.y0 - _ROW_MASK_MARGIN),
                        min(page_rect.x1, mask_x1),
                        min(bottom, end.line.rect.y1 + _ROW_MASK_MARGIN),
                    )
                )
            for box in exclude_boxes:
                if box.page_index != page_index:
                    continue
                excluded = Rect(
                    max(page_rect.x0, box.rect.x0 - _SPILL_MASK_PAD),
                    max(top, box.rect.y0 - _SPILL_MASK_PAD),
                    min(page_rect.x1, box.rect.x1 + _SPILL_MASK_PAD),
                    min(bottom, box.rect.y1 + _SPILL_MASK_PAD),
                )
                preserved = [
                    Rect(
                        item.rect.x0 - _PRESERVE_PAD,
                        item.rect.y0 - _PRESERVE_PAD,
                        item.rect.x1 + _PRESERVE_PAD,
                        item.rect.y1 + _PRESERVE_PAD,
                    )
                    for item in text_boxes
                    if item.page_index == page_index
                ]
                masks.extend(_subtract_many(excluded, preserved))
            slices.append(
                SegmentSlice(
                    page_index=page_index,
                    clip=Rect(page_rect.x0, top, page_rect.x1, bottom),
                    masks=tuple(mask for mask in masks if mask.width > 0 and mask.height > 0),
                )
            )
        return tuple(slices)

    def _lower_neighbor_boundary(
        self,
        text_boxes: Sequence[Any],
        exclude_boxes: Sequence[Any],
    ) -> float | None:
        boundaries: list[float] = []
        for excluded in exclude_boxes:
            excluded_rect = self._global_rect(excluded)
            excluded_center = _center_y(excluded_rect)
            candidates = [
                self._global_rect(current)
                for current in text_boxes
                if _center_y(self._global_rect(current)) < excluded_center
                and _horizontal_rect_overlap(self._global_rect(current), excluded_rect)
            ]
            if not candidates:
                continue
            current = max(candidates, key=_center_y)
            gap = excluded_center - _center_y(current)
            if gap <= _NEIGHBOR_CENTER_GAP:
                boundaries.append((_center_y(current) + excluded_center) / 2)
        return min(boundaries) if boundaries else None

    def _global_rect(self, box: Any) -> Rect:
        page = self.page_rects[box.page_index]
        offset = self.page_offsets[box.page_index] - page.y0
        return Rect(
            box.rect.x0,
            box.rect.y0 + offset,
            box.rect.x1,
            box.rect.y1 + offset,
        )

    def _expand_start_page_content(
        self,
        page_index: int,
        top: float,
        bottom: float,
        text_boxes: Sequence[Any],
    ) -> tuple[float, float]:
        page_top = self.page_offsets[page_index]
        page_rect = self.page_rects[page_index]
        boxes = [
            (
                box.rect.x0,
                page_top + box.rect.y0 - page_rect.y0,
                box.rect.x1,
                page_top + box.rect.y1 - page_rect.y0,
            )
            for box in text_boxes
            if box.page_index == page_index
        ]
        expanded_top = _connected_edge(top, boxes, upward=True)
        expanded_bottom = _connected_edge(bottom, boxes, upward=False)
        return expanded_top, expanded_bottom

    def _include_postfix_content(
        self,
        page_index: int,
        bottom: float,
        text_boxes: Sequence[Any],
    ) -> float:
        """Postfix label-dən sonrakı fiziki sətiri midpoint crop-a daxil et."""

        page_top = self.page_offsets[page_index]
        page_rect = self.page_rects[page_index]
        owned_bottoms = [
            page_top + box.rect.y1 - page_rect.y0 + _CONTENT_PAD for box in text_boxes if box.page_index == page_index
        ]
        return max([bottom, *owned_bottoms])


def build_slice_plan(anchors: Sequence[Any], page_rects: Sequence[Rect]) -> SlicePlan:
    """Hər distinct anchor row-a qonşu row mərkəzlərinin midpoint sərhədini verir."""

    rects = tuple(page_rects)
    offsets = _page_offsets(rects)
    rows: list[list[Any]] = []
    for anchor in sorted(anchors, key=lambda item: item.position):
        if rows and _same_row(rows[-1][0], anchor):
            rows[-1].append(anchor)
        else:
            rows.append([anchor])

    typed_rows = [
        _Row(
            page_index=row[0].line.page_index,
            anchors=tuple(row),
            global_center=offsets[row[0].line.page_index]
            + sum(_center_y(anchor.rect) for anchor in row) / len(row)
            - rects[row[0].line.page_index].y0,
        )
        for row in rows
    ]
    document_bottom = sum(rect.height for rect in rects)
    anchor_bounds: dict[int, _Bounds] = {}
    for index, row in enumerate(typed_rows):
        top = 0.0 if index == 0 else (typed_rows[index - 1].global_center + row.global_center) / 2
        bottom = (
            document_bottom
            if index + 1 == len(typed_rows)
            else (row.global_center + typed_rows[index + 1].global_center) / 2
        )
        for anchor in row.anchors:
            anchor_bounds[id(anchor)] = _Bounds(top, bottom, index)
    return SlicePlan(rects, offsets, anchor_bounds)


def _page_offsets(page_rects: Sequence[Rect]) -> tuple[float, ...]:
    offsets: list[float] = []
    current = 0.0
    for rect in page_rects:
        offsets.append(current)
        current += rect.height
    return tuple(offsets)


def _same_row(first: Any, second: Any) -> bool:
    return first.line.page_index == second.line.page_index and abs(_center_y(first.rect) - _center_y(second.rect)) <= (
        _SAME_ROW_TOLERANCE
    )


def _center_y(rect: Rect) -> float:
    return (rect.y0 + rect.y1) / 2


def _horizontal_rect_overlap(first: Rect, second: Rect) -> bool:
    return min(first.x1, second.x1) > max(first.x0, second.x0)


def _connected_edge(
    edge: float,
    boxes: Sequence[tuple[float, float, float, float]],
    *,
    upward: bool,
) -> float:
    active = [box for box in boxes if box[1] < edge < box[3]]
    if not active:
        return edge
    expanded = min(box[1] for box in active) if upward else max(box[3] for box in active)
    while True:
        joined = [
            box
            for box in boxes
            if _horizontally_overlaps(box, active)
            and (
                expanded - _CONTENT_JOIN_GAP <= box[3] < edge
                if upward
                else edge < box[1] <= expanded + _CONTENT_JOIN_GAP
            )
        ]
        if not joined:
            break
        active.extend(joined)
        candidate = min(box[1] for box in joined) if upward else max(box[3] for box in joined)
        if candidate == expanded:
            break
        expanded = candidate
    return expanded - _CONTENT_PAD if upward else expanded + _CONTENT_PAD


def _horizontally_overlaps(
    candidate: tuple[float, float, float, float],
    active: Sequence[tuple[float, float, float, float]],
) -> bool:
    return any(min(candidate[2], item[2]) > max(candidate[0], item[0]) for item in active)


def _subtract_many(rect: Rect, cutters: Sequence[Rect]) -> list[Rect]:
    pieces = [rect] if rect.width > 0 and rect.height > 0 else []
    for cutter in cutters:
        pieces = [piece for current in pieces for piece in _subtract(current, cutter)]
    return pieces


def _subtract(rect: Rect, cutter: Rect) -> tuple[Rect, ...]:
    x0 = max(rect.x0, cutter.x0)
    y0 = max(rect.y0, cutter.y0)
    x1 = min(rect.x1, cutter.x1)
    y1 = min(rect.y1, cutter.y1)
    if x1 <= x0 or y1 <= y0:
        return (rect,)
    pieces = (
        Rect(rect.x0, rect.y0, rect.x1, y0),
        Rect(rect.x0, y1, rect.x1, rect.y1),
        Rect(rect.x0, y0, x0, y1),
        Rect(x1, y0, rect.x1, y1),
    )
    return tuple(piece for piece in pieces if piece.width > 0 and piece.height > 0)
