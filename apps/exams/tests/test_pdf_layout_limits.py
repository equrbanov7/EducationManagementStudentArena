from unittest.mock import patch

from django.test import SimpleTestCase

import fitz

from apps.exams.services.pdf_layout import extract_pdf_layout, render_segments
from apps.exams.services.pdf_layout.limits import validate_document_budget


def _pdf_bytes(*, pages=1, width=595, height=842):
    document = fitz.open()
    for _ in range(pages):
        document.new_page(width=width, height=height)
    data = document.tobytes()
    document.close()
    return data


class PdfLayoutBudgetTests(SimpleTestCase):
    def test_rejects_more_than_one_hundred_pages_before_extraction(self):
        data = _pdf_bytes(pages=101, width=72, height=72)

        with self.assertRaisesRegex(ValueError, "səhifə sayı"):
            extract_pdf_layout(data)

    def test_rejects_oversized_page_before_render_allocation(self):
        data = _pdf_bytes(width=5_000, height=5_000)
        document = fitz.open(stream=data, filetype="pdf")
        self.addCleanup(document.close)

        with self.assertRaisesRegex(ValueError, "render ölçüsünü"):
            validate_document_budget(document)

    def test_render_entrypoint_also_enforces_budget(self):
        data = _pdf_bytes(width=5_000, height=5_000)
        segment = {
            "kind": "stem",
            "label": None,
            "text": "visual",
            "text_rects": [],
            "slices": [
                {
                    "page_index": 0,
                    "clip": [0, 0, 100, 100],
                    "masks": [],
                    "overlays": [],
                }
            ],
        }

        with patch("apps.exams.services.pdf_layout.rendering._render_typed_segment") as render:
            with self.assertRaisesRegex(ValueError, "render ölçüsünü"):
                render_segments(data, [segment])

        render.assert_not_called()
