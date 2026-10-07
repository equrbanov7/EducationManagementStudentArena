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


def validate_document_budget(document: fitz.Document, *, dpi: int = _BUDGET_DPI, page_limit: int | None = None) -> None:
    """
    Kiçik byte ölçülü, amma nəhəng MediaBox/xref daşıyan PDF bomb-larını rədd et.

    Büdcə faktiki raster yaratmadan 300-DPI ekvivalentinə hesablanır. Beləliklə
    OCR və source-render mərhələləri allocation etməzdən əvvəl fail-closed olur.

    ``dpi`` — çağıran daha yüksək DPI ilə render edirsə (köhnə OCR yolu
    ``EXAM_PDF_OCR_DPI``), büdcə həmin DPI ilə hesablanır (heç vaxt 300-dən aşağı).
    ``page_limit`` — çağıran yalnız ilk N səhifəni render edirsə (OCR kəsilməsi),
    səhifə sayı xəta deyil; büdcə ilk ``min(N, 100)`` səhifəyə tətbiq olunur.
    """

    dpi = max(_BUDGET_DPI, int(dpi or _BUDGET_DPI))
    if document.page_count < 1:
        raise ValueError("PDF-də səhifə yoxdur")
    if page_limit is None and document.page_count > _MAX_PAGES:
        raise ValueError(f"PDF səhifə sayı təhlükəsiz limiti keçir ({_MAX_PAGES})")
    try:
        xref_length = int(document.xref_length())
    except (AttributeError, TypeError, ValueError):
        xref_length = 0
    if xref_length > _MAX_XREF_OBJECTS:
        raise ValueError("PDF obyekt sayı təhlükəsiz limiti keçir")

    checked_pages = document.page_count
    if page_limit is not None:
        checked_pages = min(checked_pages, max(0, int(page_limit)), _MAX_PAGES)
    total_pixels = 0
    image_pixels = 0
    seen_images: set[int] = set()
    for page_index in range(checked_pages):
        page = document[page_index]
        rect = page.rect
        values = (rect.width, rect.height)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError(f"PDF səhifə ölçüsü yanlışdır (səhifə {page_index + 1})")
        width = math.ceil(rect.width * dpi / 72)
        height = math.ceil(rect.height * dpi / 72)
        pixels = width * height
        if max(width, height) > _MAX_PIXEL_DIMENSION or pixels > _MAX_PAGE_PIXELS:
            raise ValueError(f"PDF səhifəsi təhlükəsiz render ölçüsünü keçir (səhifə {page_index + 1})")
        total_pixels += pixels
        if total_pixels > _MAX_TOTAL_PIXELS:
            raise ValueError("PDF-in ümumi render ölçüsü təhlükəsiz limiti keçir")
        image_pixels += _page_image_pixels(page, page_index, seen_images)
        if image_pixels > _MAX_TOTAL_PIXELS:
            raise ValueError("PDF şəkillərinin ümumi ölçüsü təhlükəsiz limiti keçir")


#: Adaptiv OCR render-in aşağı DPI həddi (bundan aşağı Tesseract faydalı mətn vermir).
_MIN_ADAPTIVE_DPI = 72


def validate_embedded_budget(document: fitz.Document, *, page_limit: int | None = None) -> None:
    """Səhifə ölçüsündən ASILI OLMAYAN bomba yoxlamaları: xref sayı + elan olunan şəkil pikselləri.

    Köhnə OCR yolu (adaptiv DPI) üçündür: piksel ölçülü MediaBox-lu skan (məs. DPI metadatası
    olmayan «şəkil → PDF» çevirmələri, 2480×3508 pt) rədd edilmir — DPI səhifəyə görə azaldılır
    (``adaptive_render_dpi``), nəhəng MediaBox isə beləcə zərərsiz olur.
    """

    try:
        xref_length = int(document.xref_length())
    except (AttributeError, TypeError, ValueError):
        xref_length = 0
    if xref_length > _MAX_XREF_OBJECTS:
        raise ValueError("PDF obyekt sayı təhlükəsiz limiti keçir")
    checked_pages = document.page_count
    if page_limit is not None:
        checked_pages = min(checked_pages, max(0, int(page_limit)), _MAX_PAGES)
    image_pixels = 0
    seen_images: set[int] = set()
    for page_index in range(checked_pages):
        image_pixels += _page_image_pixels(document[page_index], page_index, seen_images)
        if image_pixels > _MAX_TOTAL_PIXELS:
            raise ValueError("PDF şəkillərinin ümumi ölçüsü təhlükəsiz limiti keçir")


def adaptive_render_dpi(page, dpi: int) -> int | None:
    """Səhifəni ``dpi``-də render etmək büdcəni keçirsə, keçməyən ən böyük DPI; yararsız səhifə → None."""

    rect = page.rect
    width_in, height_in = rect.width / 72, rect.height / 72
    if not all(math.isfinite(value) and value > 0 for value in (width_in, height_in)):
        return None
    by_pixels = math.sqrt(_MAX_PAGE_PIXELS / (width_in * height_in))
    by_dimension = _MAX_PIXEL_DIMENSION / max(width_in, height_in)
    safe = int(min(float(dpi), by_pixels, by_dimension))
    return safe if safe >= _MIN_ADAPTIVE_DPI else None


def render_pixels(page, dpi: int) -> int:
    rect = page.rect
    return math.ceil(rect.width * dpi / 72) * math.ceil(rect.height * dpi / 72)


def _page_image_pixels(page, page_index: int, seen: set[int]) -> int:
    """Səhifədəki şəkil obyektlərinin ELAN etdiyi piksel sahəsi (açmadan).

    Təhlükəsizlik auditi 2026-10-07: normal ölçülü səhifə 1 MB-lıq Flate axını ilə
    40000×40000 piksellik şəkil daşıya bilər — render/``extract_image`` onu TAM açır.
    Səhifə büdcəsi kimi, tək şəkil də 50 MP-dən böyük ola bilməz; eyni obyekt
    (``xref``) bir neçə səhifədə təkrarlanırsa ümumi cəmə BİR dəfə düşür.
    """

    total = 0
    try:
        images = page.get_images(full=True)
    except Exception:  # noqa: BLE001 — pozuq resurs lüğəti: render özü xəta verəcək
        return 0
    for image in images:
        try:
            xref, width, height = int(image[0]), int(image[2]), int(image[3])
        except (IndexError, TypeError, ValueError):
            continue
        if xref in seen:
            continue
        seen.add(xref)
        pixels = max(0, width) * max(0, height)
        if pixels > _MAX_PAGE_PIXELS:
            raise ValueError(f"PDF-dəki şəkil təhlükəsiz ölçünü keçir (səhifə {page_index + 1})")
        total += pixels
    return total


__all__ = ["validate_document_budget"]
