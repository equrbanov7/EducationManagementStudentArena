"""Native text-i boş PDF səhifələri üçün deterministic Tesseract OCR fallback."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.conf import settings

import fitz

logger = logging.getLogger(__name__)

_DEFAULT_DPI = 300
_MIN_DPI = 300
_DEFAULT_MAX_PAGES = 100
_HARD_MAX_PAGES = 100
_DEFAULT_LANGUAGE = "aze"
_VISUAL_DPI = 72
_VISUAL_WHITE_THRESHOLD = 245
_VISUAL_MIN_INK_PIXELS = 8


@dataclass(frozen=True, slots=True)
class PageTextResult:
    """Səhifə mətni və emal olunmamış vizual məzmun diaqnostikası."""

    rawdict: dict[str, Any]
    unprocessed_reason: str | None = None


def page_rawdict(page: fitz.Page, page_index: int) -> dict[str, Any]:
    """Backward-compatible rawdict wrapper."""

    return page_text_result(page, page_index).rawdict


def page_text_result(page: fitz.Page, page_index: int) -> PageTextResult:
    """
    Native rawdict qaytarır; yalnız o boşdursa page-level full OCR sınayır.

    Boş səhifə problem sayılmır. Vizual məzmunu olan səhifə OCR
    söndürülməsi/limiti/runtime/xətası səbəbi ilə oxunmasa səbəb üst parserə
    ötürülür ki, qarışıq native+scan sənəd qismən qəbul edilməsin.
    """

    native = page.get_text("rawdict", sort=True)
    if _rawdict_has_text(native):
        return PageTextResult(native)
    if not _page_has_visual_content(page):
        return PageTextResult(native)
    if not _enabled():
        return PageTextResult(native, "OCR söndürülüb")
    if page_index >= _max_pages():
        return PageTextResult(native, f"OCR səhifə limiti keçilib (limit={_max_pages()})")
    if not ocr_runtime_available():
        return PageTextResult(native, "Tesseract OCR runtime mövcud deyil")

    attempted = False
    for language in _languages():
        try:
            attempted = True
            textpage = page.get_textpage_ocr(
                flags=fitz.TEXTFLAGS_RAWDICT,
                language=language,
                dpi=_dpi(),
                full=True,
            )
            raw = page.get_text("rawdict", textpage=textpage, sort=True)
            if _rawdict_has_text(raw):
                return PageTextResult(raw)
        except Exception as exc:  # Tesseract/language/runtime xətası fail-closed
            logger.info(
                "PDF layout OCR alınmadı (page=%s, lang=%s): %s",
                page_index + 1,
                language,
                exc,
            )
    detail = "OCR nəticə vermədi" if attempted else "OCR başladılmadı"
    return PageTextResult(native, detail)


@lru_cache(maxsize=1)
def ocr_runtime_available() -> bool:
    """PyMuPDF-in istifadə edə bildiyi Tesseract runtime-ını konservativ yoxlayır."""

    if shutil.which("tesseract") is None:
        return False
    try:
        return bool(fitz.get_tessdata())
    except Exception:
        return False


def _rawdict_has_text(raw: dict[str, Any]) -> bool:
    return any(
        str(char.get("c") or "").strip()
        for block in raw.get("blocks", ())
        if block.get("type") == 0
        for line in block.get("lines", ())
        for span in line.get("spans", ())
        for char in span.get("chars", ())
    )


def _page_has_visual_content(page: fitz.Page) -> bool:
    """Native mətni olmayan ağ səhifəni scan/formula səhifəsindən ayırır."""

    try:
        pixmap = page.get_pixmap(dpi=_VISUAL_DPI, colorspace=fitz.csGRAY, alpha=False, annots=False)
    except Exception:
        # Render auditinin özü alınmırsa səhifəni blank hesab etmək təhlükəlidir.
        return True
    ink = sum(value < _VISUAL_WHITE_THRESHOLD for value in pixmap.samples)
    minimum = max(_VISUAL_MIN_INK_PIXELS, round(pixmap.width * pixmap.height * 0.00005))
    return ink >= minimum


def _enabled() -> bool:
    return bool(getattr(settings, "EXAM_PDF_OCR_ENABLED", True))


def _dpi() -> int:
    try:
        configured = int(getattr(settings, "EXAM_PDF_OCR_DPI", _DEFAULT_DPI))
    except (TypeError, ValueError):
        configured = _DEFAULT_DPI
    return max(_MIN_DPI, configured)


def _max_pages() -> int:
    try:
        configured = int(getattr(settings, "EXAM_PDF_OCR_MAX_PAGES", _DEFAULT_MAX_PAGES))
    except (TypeError, ValueError):
        configured = _DEFAULT_MAX_PAGES
    return min(_HARD_MAX_PAGES, max(0, configured))


def _languages() -> tuple[str, ...]:
    configured = str(getattr(settings, "EXAM_PDF_OCR_LANG", _DEFAULT_LANGUAGE) or "").strip()
    languages = [configured or _DEFAULT_LANGUAGE, "eng"]
    return tuple(dict.fromkeys(languages))
