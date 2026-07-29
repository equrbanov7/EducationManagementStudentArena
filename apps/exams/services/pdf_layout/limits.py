"""Untrusted PDF-lər üçün decoded/render resurs büdcələri."""

from __future__ import annotations

import math

import fitz

_BUDGET_DPI = 300
_MAX_PAGES = 100
_MAX_XREF_OBJECTS = 200_000
_MAX_PAGE_PIXELS = 50_000_000
_MAX_TOTAL_PIXELS = 1_000_000_000
_MAX_PIXEL_DIMENSION = 20_000


def validate_document_budget(document: fitz.Document) -> None:
    """
    Kiçik byte ölçülü, amma nəhəng MediaBox/xref daşıyan PDF bomb-larını rədd et.

    Büdcə faktiki raster yaratmadan 300-DPI ekvivalentinə hesablanır. Beləliklə
    OCR və source-render mərhələləri allocation etməzdən əvvəl fail-closed olur.
    """

    if document.page_count < 1:
        raise ValueError("PDF-də səhifə yoxdur")
    if document.page_count > _MAX_PAGES:
        raise ValueError(f"PDF səhifə sayı təhlükəsiz limiti keçir ({_MAX_PAGES})")
    try:
        xref_length = int(document.xref_length())
    except (AttributeError, TypeError, ValueError):
        xref_length = 0
    if xref_length > _MAX_XREF_OBJECTS:
        raise ValueError("PDF obyekt sayı təhlükəsiz limiti keçir")

    total_pixels = 0
    for page_index, page in enumerate(document):
        rect = page.rect
        values = (rect.width, rect.height)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError(f"PDF səhifə ölçüsü yanlışdır (səhifə {page_index + 1})")
        width = math.ceil(rect.width * _BUDGET_DPI / 72)
        height = math.ceil(rect.height * _BUDGET_DPI / 72)
        pixels = width * height
        if max(width, height) > _MAX_PIXEL_DIMENSION or pixels > _MAX_PAGE_PIXELS:
            raise ValueError(f"PDF səhifəsi təhlükəsiz render ölçüsünü keçir (səhifə {page_index + 1})")
        total_pixels += pixels
        if total_pixels > _MAX_TOTAL_PIXELS:
            raise ValueError("PDF-in ümumi render ölçüsü təhlükəsiz limiti keçir")


__all__ = ["validate_document_budget"]
