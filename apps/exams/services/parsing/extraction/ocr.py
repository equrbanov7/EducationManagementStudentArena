"""extraction paketi — ocr."""

import io
import os
import re

from django.conf import settings

from apps.exams.constants import OPTION_RE, QUESTION_RE

from ._deps import fitz
from .constants import (
    logger,
)
from .highlight import (
    _build_yellow_mask,
    _line_words_have_yellow,
)
from .normalize import (
    normalize_pdf_extracted_text,
)


def _ensure_tessdata_prefix() -> None:
    """
    PyMuPDF OCR requires TESSDATA_PREFIX even when the tesseract CLI can find
    languages by itself. Debian/Ubuntu packages keep traineddata here.
    """
    if os.getenv("TESSDATA_PREFIX"):
        return

    candidates = (
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
    )
    for path in candidates:
        if os.path.exists(os.path.join(path, "eng.traineddata")):
            os.environ["TESSDATA_PREFIX"] = path
            return


def _ocr_pdf_text(uploaded_file) -> str:
    """
    Skan edilmiş PDF-dən OCR ilə mətn çıxarır (PyMuPDF daxili Tesseract) və
    şəkilə "baked" sarı highlight ilə işarələnmiş düz cavabı aşkar edib mövcud
    "*" markerini həmin variant sətrinə əlavə edir. Beləliklə skan PDF-də belə
    highlight→düz cavab işləyir (annotation olmasa da).

    Konfiqurasiya (settings):
      - EXAM_PDF_OCR_ENABLED            (default True)
      - EXAM_PDF_OCR_LANG               (default "aze") — Tesseract dili; işləməsə "eng"
      - EXAM_PDF_OCR_DPI                (default 300)
      - EXAM_PDF_OCR_MAX_PAGES          (default 100) — request timeout-dan qoruyan limit
      - EXAM_PDF_OCR_HIGHLIGHT          (default True) — sarı→düz cavab aşkarı
      - EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO(default 0.10) — sətrin sarı örtük həddi

    Tam müdafiəlidir: fitz/Tesseract yoxdursa və ya xəta olarsa boş sətir qaytarır.
    """
    if fitz is None or not getattr(settings, "EXAM_PDF_OCR_ENABLED", True):
        return ""

    _ensure_tessdata_prefix()

    lang = getattr(settings, "EXAM_PDF_OCR_LANG", "aze")
    detect_highlight = getattr(settings, "EXAM_PDF_OCR_HIGHLIGHT", True)
    try:
        dpi = max(300, int(getattr(settings, "EXAM_PDF_OCR_DPI", 300)))
        max_pages = int(getattr(settings, "EXAM_PDF_OCR_MAX_PAGES", 100))
        min_ratio = float(getattr(settings, "EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO", 0.10))
    except (TypeError, ValueError):
        dpi, max_pages, min_ratio = 300, 100, 0.10

    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return ""

    # Konfiqurasiya olunmuş dil, sonra "eng" fallback. İlk işləyən dili "kilidləyirik".
    languages_to_try = [lang] + (["eng"] if lang != "eng" else [])
    active_lang = None
    zoom = dpi / 72.0
    parts: list[str] = []
    try:
        from PIL import Image
    except Exception:
        Image = None
        detect_highlight = False

    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for index, page in enumerate(doc):
                if index >= max_pages:
                    logger.info("PDF OCR truncated at %d pages (doc has %d).", max_pages, doc.page_count)
                    break

                # OCR textpage (mətn + söz qutuları). İlk işləyən dili tap.
                textpage = None
                for candidate in ([active_lang] if active_lang else languages_to_try):
                    try:
                        textpage = page.get_textpage_ocr(full=True, language=candidate, dpi=dpi)
                        active_lang = candidate
                        break
                    except Exception:
                        continue
                if textpage is None:
                    continue

                page_text = _ocr_page_text_with_highlights(
                    page, textpage, zoom, detect_highlight, min_ratio, Image, dpi
                )
                if page_text.strip():
                    parts.append(page_text.strip())
    except Exception as exc:
        logger.warning("PDF OCR failed: %s", exc)
        return ""

    return normalize_pdf_extracted_text("\n\n".join(parts))


def _ocr_image_text(uploaded_file) -> str:
    """
    PNG/JPG faylını OCR üçün tək səhifəlik image-only PDF kimi emal edir.
    Bu, ayrıca Tesseract wrapper-i əlavə etmədən skan-PDF üçün yazılmış
    highlight→düz cavab məntiqindən birbaşa şəkil fayllarında da istifadə edir.
    """
    if fitz is None or not getattr(settings, "EXAM_PDF_OCR_ENABLED", True):
        return ""

    try:
        from PIL import Image
    except Exception:
        return ""

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
        uploaded_file.seek(0)
    except Exception as exc:
        logger.warning("Image OCR open failed for upload %s: %s", getattr(uploaded_file, "name", ""), exc)
        return ""

    try:
        dpi = max(300, int(getattr(settings, "EXAM_PDF_OCR_DPI", 300)))
    except (TypeError, ValueError):
        dpi = 300

    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        return ""

    png_buffer = io.BytesIO()
    image.save(png_buffer, format="PNG")
    page_width = max(1, width * 72 / dpi)
    page_height = max(1, height * 72 / dpi)

    doc = fitz.open()
    try:
        page = doc.new_page(width=page_width, height=page_height)
        page.insert_image(page.rect, stream=png_buffer.getvalue())
        pdf_buffer = io.BytesIO(doc.tobytes())
    finally:
        doc.close()

    return _ocr_pdf_text(pdf_buffer)


def _ocr_page_text_with_highlights(page, textpage, zoom, detect_highlight, min_ratio, Image, dpi) -> str:
    """
    Bir səhifə üçün OCR mətnini sətir-sətir qurur. Sarı highlight aşkarı aktivdirsə,
    variant sətrinin söz-qutusu sarı ilə örtülübsə əvvəlinə "*" əlavə edir.
    """
    words = page.get_text("words", textpage=textpage) or []
    if not words:
        # Fallback: highlight aşkarı mümkün deyilsə düz mətn.
        return page.get_text(textpage=textpage) or ""

    mask = None
    if detect_highlight and Image is not None:
        try:
            pix = page.get_pixmap(dpi=dpi)
            rgb = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            mask = _build_yellow_mask(rgb)
        except Exception:
            mask = None

    mask_w, mask_h = mask.size if mask is not None else (0, 0)

    # Sözləri oxu sırasına görə (block, line) sətrlərə qrupla.
    from collections import OrderedDict

    grouped: "OrderedDict[tuple, list]" = OrderedDict()
    for word in words:
        # word = (x0, y0, x1, y1, text, block_no, line_no, word_no)
        grouped.setdefault((word[5], word[6]), []).append(word)

    lines_out: list[str] = []
    current_option_index = None
    for line_words in grouped.values():
        text = " ".join(w[4] for w in line_words).strip()
        if not text:
            continue

        line_has_yellow = _line_words_have_yellow(mask, line_words, zoom, min_ratio, mask_w, mask_h)
        match = OPTION_RE.match(text)

        if mask is not None:
            if match and not match.group(1):  # variant sətri, hələ ulduzsuz
                if line_has_yellow:
                    text = "*" + text
            elif line_has_yellow and current_option_index is not None:
                existing = lines_out[current_option_index]
                if OPTION_RE.match(existing) and not existing.lstrip().startswith("*"):
                    lines_out[current_option_index] = re.sub(r"^(\s*)", r"\1*", existing, count=1)

        if match:
            current_option_index = len(lines_out)
        elif QUESTION_RE.match(text):
            current_option_index = None

        lines_out.append(text)

    return "\n".join(lines_out)
