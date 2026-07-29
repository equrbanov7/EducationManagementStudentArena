"""Native answer annotasiyalarını formula-overlap hallarında tək option-a bağlayır."""

from __future__ import annotations

from typing import Any, Sequence

from .manifest import Option, PageRect

_MIN_OVERLAP_AREA = 0.5
_CLUSTER_GAP = 16.0


def correct_labels(
    options: Sequence[Option],
    annotations: Sequence[Any],
) -> tuple[str, ...]:
    """
    Yaxın annotation fraqmentlərini bir cavab markı kimi qruplaşdırır.

    Hündür matrisin son sətri növbəti option label-i ilə üst-üstə düşəndə
    content overlap-i olan ən erkən option seçilir. Beləliklə eyni vizual
    cavab markı iki variant kimi sayılmır, aralı marklar isə multi-answer qala
    bilir.
    """

    relevant = [
        annotation
        for annotation in annotations
        if any(_overlap(annotation, option, include_anchor=True) for option in options)
    ]
    labels: set[str] = set()
    for cluster in _clusters(relevant):
        content_candidates = [
            option
            for option in options
            if sum(_overlap(annotation, option, include_anchor=False) for annotation in cluster) >= _MIN_OVERLAP_AREA
        ]
        if content_candidates:
            labels.add(content_candidates[0].label)
            continue
        anchor_scores = [
            (
                sum(_anchor_overlap(annotation, option) for annotation in cluster),
                option,
            )
            for option in options
        ]
        score, selected = max(anchor_scores, key=lambda item: item[0], default=(0.0, None))
        if selected is not None and score >= _MIN_OVERLAP_AREA:
            labels.add(selected.label)
    return tuple(option.label for option in options if option.label in labels)


def _clusters(annotations: Sequence[Any]) -> tuple[tuple[Any, ...], ...]:
    remaining = list(annotations)
    result: list[tuple[Any, ...]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        while True:
            joined = [annotation for annotation in remaining if any(_near(annotation, current) for current in cluster)]
            if not joined:
                break
            cluster.extend(joined)
            remaining = [annotation for annotation in remaining if annotation not in joined]
        result.append(tuple(cluster))
    return tuple(result)


def _near(first: Any, second: Any) -> bool:
    if first.page_index != second.page_index:
        return False
    return any(
        _axis_gap(a.x0, a.x1, b.x0, b.x1) <= _CLUSTER_GAP and _axis_gap(a.y0, a.y1, b.y0, b.y1) <= _CLUSTER_GAP
        for a in first.rects
        for b in second.rects
    )


def _axis_gap(first_start: float, first_end: float, second_start: float, second_end: float) -> float:
    return max(0.0, max(first_start, second_start) - min(first_end, second_end))


def _overlap(annotation: Any, option: Option, *, include_anchor: bool) -> float:
    boxes = list(option.segment.text_boxes)
    if include_anchor:
        anchor = option.segment.anchor
        boxes.insert(0, PageRect(anchor.page_index, anchor.rect))
    return sum(
        max(
            (region.intersection_area(box.rect) for box in boxes if box.page_index == annotation.page_index),
            default=0.0,
        )
        for region in annotation.rects
    )


def _anchor_overlap(annotation: Any, option: Option) -> float:
    anchor = option.segment.anchor
    if anchor.page_index != annotation.page_index:
        return 0.0
    return sum(region.intersection_area(anchor.rect) for region in annotation.rects)
