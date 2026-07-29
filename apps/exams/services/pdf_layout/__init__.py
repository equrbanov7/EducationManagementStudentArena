"""Geometry-first PDF MCQ layout çıxarışı və təhlükəsiz segment renderi."""

from .extraction import analyze_pdf, extract_pdf_layout, manifest_to_mcq_text
from .manifest import (
    Anchor,
    Confidence,
    LayoutConfidenceError,
    Manifest,
    Option,
    PageRect,
    Question,
    Rect,
    Segment,
    SegmentSlice,
)
from .rendering import MIN_DPI, render_segment, render_segment_png, render_segments

__all__ = [
    "Anchor",
    "Confidence",
    "LayoutConfidenceError",
    "MIN_DPI",
    "Manifest",
    "Option",
    "PageRect",
    "Question",
    "Rect",
    "Segment",
    "SegmentSlice",
    "analyze_pdf",
    "extract_pdf_layout",
    "manifest_to_mcq_text",
    "render_segment",
    "render_segment_png",
    "render_segments",
]
