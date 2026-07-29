"""PDF sual layout-u üçün dəyişməz və JSON-a çevrilə bilən tiplər."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Rect:
    """PDF point koordinatlarında düzbucaqlı."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection_area(self, other: "Rect") -> float:
        width = max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))
        height = max(0.0, min(self.y1, other.y1) - max(self.y0, other.y0))
        return width * height

    def to_list(self) -> list[float]:
        return [round(value, 3) for value in (self.x0, self.y0, self.x1, self.y1)]


@dataclass(frozen=True, slots=True)
class PageRect:
    page_index: int
    rect: Rect

    def to_dict(self) -> dict[str, object]:
        return {"page_index": self.page_index, "rect": self.rect.to_list()}


@dataclass(frozen=True, slots=True)
class Anchor:
    """Sual və ya variant label-inin dəqiq geometriyası."""

    label: str
    page_index: int
    rect: Rect
    line_rect: Rect

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "page_index": self.page_index,
            "rect": self.rect.to_list(),
            "line_rect": self.line_rect.to_list(),
        }


@dataclass(frozen=True, slots=True)
class SegmentSlice:
    """Bir segmentin bir PDF səhifəsində render olunacaq hissəsi."""

    page_index: int
    clip: Rect
    masks: tuple[Rect, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "page_index": self.page_index,
            "clip": self.clip.to_list(),
            "masks": [mask.to_list() for mask in self.masks],
        }


@dataclass(frozen=True, slots=True)
class Segment:
    """Anchor-dan növbəti anchor-a qədər mətn və vizual dilimlər."""

    text: str
    anchor: Anchor
    slices: tuple[SegmentSlice, ...]
    text_boxes: tuple[PageRect, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "anchor": self.anchor.to_dict(),
            "slices": [item.to_dict() for item in self.slices],
            "text_boxes": [item.to_dict() for item in self.text_boxes],
        }


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    segment: Segment

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "segment": self.segment.to_dict()}


@dataclass(frozen=True, slots=True)
class Question:
    ordinal: int
    printed_q_no: int
    stem: Segment
    options: tuple[Option, ...]
    correct_labels: tuple[str, ...]

    def option(self, label: str) -> Option:
        for option in self.options:
            if option.label == label:
                return option
        raise KeyError(label)

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "q_no": self.printed_q_no,
            "stem": self.stem.to_dict(),
            "options": {option.label: option.segment.to_dict() for option in self.options},
            "correct": list(self.correct_labels),
        }


@dataclass(frozen=True, slots=True)
class Confidence:
    """Parserin fail-closed qərarı və audit üçün saylar."""

    is_confident: bool
    question_anchor_count: int
    option_anchor_count: int
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "is_confident": self.is_confident,
            "question_anchor_count": self.question_anchor_count,
            "option_anchor_count": self.option_anchor_count,
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class Manifest:
    page_count: int
    questions: tuple[Question, ...]
    canonical_text: str
    confidence: Confidence

    def iter_segments(self) -> Iterator[Segment]:
        for question in self.questions:
            yield question.stem
            for option in question.options:
                yield option.segment

    def to_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "questions": [question.to_dict() for question in self.questions],
            "canonical_text": self.canonical_text,
            "confidence": self.confidence.to_dict(),
        }


class LayoutConfidenceError(ValueError):
    """Anchor invariantları pozulduqda manifesti qəbul etməyən xəta."""

    def __init__(self, manifest: Manifest):
        self.manifest = manifest.to_dict()
        detail = "; ".join(manifest.confidence.issues) or "naməlum confidence xətası"
        super().__init__(f"PDF layout etibarlı deyil: {detail}")
