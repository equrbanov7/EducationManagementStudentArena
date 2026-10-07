"""Təhlükəsizlik auditi 2026-10-07 — sual importunda PDF/şəkil «bomb»-ları (DoS).

* ``pdf_layout`` render büdcəsi (``validate_document_budget``) nəhəng MediaBox-lu
  səhifəni rədd edirdi, amma ``prepare_question_upload`` vizual axın alınmayanda
  köhnə mətn çıxarışına düşür: ``_ocr_pdf_text`` HƏMİN səhifəni ≥300 DPI-də
  büdcəsiz OCR edirdi (14400 pt → 60000² piksel ≈ 10 GB pixmap, sinxron veb sorğuda).
* ``_ocr_image_text`` şəkli Pillow-un ~178 MP default tavanına qədər açırdı.
* ``pdf_images`` gömülü şəkli ``extract_image`` ilə TAM açırdı — 50 MP limiti
  açılmadan SONRA yoxlanırdı; büdcə də səhifədəki şəkil obyektlərinə baxmırdı.
"""

from __future__ import annotations

import io
from unittest import mock

from django.test import SimpleTestCase, override_settings

import fitz
from PIL import Image

from apps.exams.services.parsing.extraction import ocr
from apps.exams.services.parsing.pdf_images import _read_placements
from apps.exams.services.pdf_layout.limits import validate_document_budget


def _pdf(*, pages=1, width=595, height=842) -> bytes:
    document = fitz.open()
    for _ in range(pages):
        document.new_page(width=width, height=height)
    data = document.tobytes()
    document.close()
    return data


def _pdf_with_declared_image(width: int, height: int) -> bytes:
    """A4 səhifə + şəkil obyekti; ``/Width``/``/Height`` açılmadan dəyişdirilir (yaddaş ayrılmır)."""
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(50, 100, 150, 200), pixmap=fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 2, 2), False))
    xref = page.get_images(full=True)[0][0]
    document.xref_set_key(xref, "Width", str(width))
    document.xref_set_key(xref, "Height", str(height))
    data = document.tobytes()
    document.close()
    return data


def _ocr_calls(data: bytes) -> list:
    calls = []

    def fake_ocr(page, *args, **kwargs):
        calls.append(page.rect)
        raise RuntimeError("tesseract yoxdur (test)")

    with mock.patch.object(fitz.Page, "get_textpage_ocr", fake_ocr, create=True):
        ocr._ocr_pdf_text(io.BytesIO(data))
    return calls


@override_settings(EXAM_PDF_OCR_ENABLED=True, EXAM_PDF_OCR_DPI=300, EXAM_PDF_OCR_MAX_PAGES=100)
class LegacyPdfOcrBudgetTest(SimpleTestCase):
    def test_oversized_page_is_not_rendered_for_ocr(self):
        self.assertEqual(_ocr_calls(_pdf(width=14_400, height=14_400)), [])

    def test_normal_page_is_still_ocrd(self):
        self.assertTrue(_ocr_calls(_pdf()))

    def test_long_scan_is_truncated_not_rejected(self):
        # 100-dən çox səhifə büdcə XƏTASI deyil — OCR əvvəlki kimi ilk 100 səhifədə kəsilir.
        self.assertTrue(_ocr_calls(_pdf(pages=101, width=72, height=72)))

    def test_configured_page_cap_cannot_exceed_hard_limit(self):
        with override_settings(EXAM_PDF_OCR_MAX_PAGES=10_000):
            calls = _ocr_calls(_pdf(pages=101, width=72, height=72))
        # Hər səhifə üçün ən çox 2 dil sınağı (aze → eng); 101-ci səhifə OCR olunmur.
        self.assertLessEqual(len(calls), 2 * ocr.OCR_HARD_MAX_PAGES)


@override_settings(EXAM_PDF_OCR_ENABLED=True)
class ImageOcrPixelBudgetTest(SimpleTestCase):
    def test_huge_declared_image_is_not_decoded(self):
        buffer = io.BytesIO()
        Image.new("1", (8_000, 7_000)).save(buffer, format="PNG")  # 56 MP, ~10 KB
        buffer.seek(0)
        with mock.patch.object(ocr, "_ocr_pdf_text", return_value="mətn") as pdf_ocr:
            self.assertEqual(ocr._ocr_image_text(buffer), "")
        pdf_ocr.assert_not_called()

    def test_normal_image_reaches_ocr(self):
        buffer = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
        buffer.seek(0)
        with mock.patch.object(ocr, "_ocr_pdf_text", return_value="mətn") as pdf_ocr:
            self.assertEqual(ocr._ocr_image_text(buffer), "mətn")
        pdf_ocr.assert_called_once()


class EmbeddedImageBudgetTest(SimpleTestCase):
    def test_budget_rejects_page_with_oversized_image_object(self):
        document = fitz.open(stream=_pdf_with_declared_image(40_000, 40_000), filetype="pdf")
        self.addCleanup(document.close)
        with self.assertRaisesRegex(ValueError, "şəkil"):
            validate_document_budget(document)

    def test_budget_accepts_normal_image(self):
        document = fitz.open(stream=_pdf_with_declared_image(2_000, 1_500), filetype="pdf")
        self.addCleanup(document.close)
        validate_document_budget(document)

    def test_pdf_image_extraction_skips_oversized_object_before_decoding(self):
        document = fitz.open(stream=_pdf_with_declared_image(40_000, 40_000), filetype="pdf")
        self.addCleanup(document.close)
        placements, skipped = _read_placements(document)
        self.assertEqual(placements, [])
        self.assertEqual(skipped, 1)

    def test_pdf_image_extraction_keeps_normal_object(self):
        document = fitz.open(stream=_pdf_with_declared_image(800, 600), filetype="pdf")
        self.addCleanup(document.close)
        placements, _skipped = _read_placements(document)
        self.assertEqual(len(placements), 1)
