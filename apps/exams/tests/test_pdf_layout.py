"""Geometry-first PDF layout servisinin sintetik characterization testləri."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

import fitz
from PIL import Image, ImageDraw

from apps.exams.services.pdf_layout import (
    LayoutConfidenceError,
    analyze_pdf,
    manifest_to_mcq_text,
    render_segment,
    render_segments,
)
from apps.exams.services.pdf_layout.ocr import _dpi, _languages, _max_pages, ocr_runtime_available, page_rawdict
from apps.exams.services.pdf_layout.rendering import _deduplicate_adjacent

_REAL_SAMPLE = Path("/Users/elvin/Downloads/Hesablama təcrübələri cvb (1).pdf")


def _fixture_pdf() -> bytes:
    document = fitz.open()
    first = document.new_page(width=420, height=240)
    first.insert_text((36, 30), "1. First stem", fontsize=12)
    first.insert_text((36, 65), "A) Alpha", fontsize=12)
    first.insert_text((36, 95), "B) Beta    C) Gamma", fontsize=12)

    gamma_rect = first.search_for("Gamma")[0]
    highlight = first.add_highlight_annot(gamma_rect)
    highlight.update()

    alpha_highlight = first.add_highlight_annot(first.search_for("Alpha")[0])
    alpha_highlight.update()

    # Q1-də primary A/C Highlight-ları tapıldığı üçün Ink fallback nəticəyə
    # ayrıca qarışmamalıdır.
    ignored_ink = first.add_ink_annot([[(52, 66), (86, 66)]])
    ignored_ink.set_colors(stroke=(1, 1, 0))
    ignored_ink.set_border(width=3)
    ignored_ink.set_info(subject="Highlight")
    ignored_ink.update()

    second = document.new_page(width=420, height=270)
    second.insert_text((36, 28), "continued C formula", fontsize=12)
    second.insert_text((36, 58), "D) Delta", fontsize=12)
    second.insert_text((36, 98), "2. Second stem", fontsize=12)
    second.insert_text((36, 128), "A) One", fontsize=12)
    second.insert_text((36, 158), "B) Two", fontsize=12)
    second.insert_text((36, 188), "C) Three", fontsize=12)
    second.insert_text((36, 218), "D) Four", fontsize=12)

    # Real prototipdəki Q152 kimi sarı Ink + subject=Highlight fallback.
    fallback_ink = second.add_ink_annot([[(52, 219), (86, 219)]])
    fallback_ink.set_colors(stroke=(1, 1, 0))
    fallback_ink.set_border(width=3)
    fallback_ink.set_info(subject="Highlight")
    fallback_ink.update()

    data = document.tobytes(garbage=4, deflate=True)
    document.close()
    return data


def _invalid_pdf(*, second_q_no: int | None = None) -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=320)
    page.insert_text((36, 30), "1. Incomplete", fontsize=12)
    for index, label in enumerate(("A", "B", "C"), start=1):
        page.insert_text((36, 30 + index * 30), f"{label}) value", fontsize=12)
    if second_q_no is not None:
        page.insert_text((36, 160), f"{second_q_no}. Out of sequence", fontsize=12)
        for index, label in enumerate(("A", "B", "C", "D"), start=1):
            page.insert_text((36, 160 + index * 30), f"{label}) value", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _contiguous_subset_pdf(start: int = 51, count: int = 2) -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=420)
    y = 30
    for offset in range(count):
        page.insert_text((36, y), f"{start + offset}. Subset question", fontsize=12)
        for index, label in enumerate(("A", "B", "C", "D"), start=1):
            page.insert_text((36, y + index * 28), f"{label}) value", fontsize=12)
        y += 145
    data = document.tobytes()
    document.close()
    return data


def _geometry_noise_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=420)
    page.insert_text((36, 30), "1. Stem", fontsize=12)
    page.insert_text((180, 45), "9.4", fontsize=12)
    page.insert_text((180, 60), "10.4", fontsize=12)
    page.insert_text((180, 75), "11.4", fontsize=12)
    page.insert_text((180, 90), "C) formula token", fontsize=12)
    for index, label in enumerate(("A", "B", "C", "D"), start=1):
        page.insert_text((36, 70 + index * 30), f"{label}) first", fontsize=12)
    page.insert_text((36, 230), "2. Stem", fontsize=12)
    for index, label in enumerate(("A", "B", "C", "D"), start=1):
        page.insert_text((36, 230 + index * 30), f"{label}) second", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _visual_only_option_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=280)
    page.insert_text((36, 30), "1. Formula option", fontsize=12)
    page.insert_text((36, 65), "A) Alpha", fontsize=12)
    page.insert_text((36, 95), "B) Beta", fontsize=12)
    page.insert_text((36, 125), "C)", fontsize=12)
    page.draw_rect(fitz.Rect(70, 112, 130, 142), color=(0, 0, 0))
    page.draw_line((75, 137), (125, 117), color=(0, 0, 0))
    page.insert_text((36, 160), "D) Delta", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _tall_formula_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=520)
    page.insert_text((36, 100), "1. Tall formula", fontsize=12)
    page.insert_text((180, 150), "M", fontsize=40, color=(0, 0, 0))
    page.draw_rect(fitz.Rect(260, 108, 270, 150), color=(0, 0, 0), fill=(0, 0, 0))

    page.insert_text((36, 170), "A) option formula", fontsize=12, color=(0, 0, 1))
    page.insert_text((180, 230), "M", fontsize=55, color=(1, 0, 0))
    page.draw_rect(fitz.Rect(260, 173, 270, 230), color=(1, 0, 0), fill=(1, 0, 0))
    for y, label in ((330, "B"), (400, "C"), (470, "D")):
        page.insert_text((36, y), f"{label}) value", fontsize=12)

    data = document.tobytes(garbage=4, deflate=True)
    document.close()
    return data


def _previous_segment_descender_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=300)
    page.insert_text((36, 30), "1. Stem", fontsize=12)
    # Stem-ə aid uzaq glyph A crop-un midpoint sərhədini keçir.
    page.insert_text((330, 55), "-", fontsize=20)
    for y, label in ((75, "A"), (125, "B"), (175, "C"), (225, "D")):
        page.insert_text((36, y), f"{label}) value", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _image(payload: bytes) -> Image.Image:
    return Image.open(BytesIO(payload)).convert("RGB")


def _red_pixels(image: Image.Image) -> int:
    return sum(1 for red, green, blue in image.getdata() if red > 150 and green < 90 and blue < 90)


def _blue_pixels(image: Image.Image) -> int:
    return sum(1 for red, green, blue in image.getdata() if blue > 150 and red < 90 and green < 90)


def _green_pixels(image: Image.Image) -> int:
    return sum(1 for red, green, blue in image.getdata() if green > 120 and red < 130 and blue < 100)


def _yellow_pixels(image: Image.Image) -> int:
    return sum(
        1 for red, green, blue in image.getdata() if red >= 160 and green >= 140 and blue + 25 <= min(red, green)
    )


def _dark_row_span(image: Image.Image, x0: int, x1: int) -> int:
    rows = [
        y
        for y in range(image.height)
        if any(sum(image.getpixel((x, y))) < 200 for x in range(x0, min(x1, image.width)))
    ]
    return max(rows) - min(rows) + 1


def _ink_row_bands(image: Image.Image) -> list[tuple[int, int]]:
    grayscale = image.convert("L")
    counts = [
        sum(grayscale.getpixel((x, y)) < 180 for x in range(80, grayscale.width)) for y in range(grayscale.height)
    ]
    bands: list[tuple[int, int]] = []
    start = None
    for y, count in enumerate([*counts, 0]):
        if count >= 15 and start is None:
            start = y
        elif count < 15 and start is not None:
            if y - start > 2:
                bands.append((start, y - 1))
            start = None
    return bands


def _insert_ocr_question(page: fitz.Page, q_no: int) -> None:
    page.insert_text((50, 70), f"{q_no}. OCR geometry question", fontsize=20, fontname="helv")
    for index, (label, value) in enumerate(
        (("A", "Alpha"), ("B", "Beta"), ("C", "Gamma"), ("D", "Delta")),
        start=1,
    ):
        page.insert_text((50, 70 + index * 55), f"{label}) {value}", fontsize=20, fontname="helv")


def _image_only_question_pdf(q_no: int = 1) -> bytes:
    native = fitz.open()
    native_page = native.new_page(width=612, height=500)
    _insert_ocr_question(native_page, q_no)
    pixmap = native_page.get_pixmap(dpi=300, alpha=False)

    scanned = fitz.open()
    scanned_page = scanned.new_page(width=612, height=500)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    data = scanned.tobytes(garbage=4, deflate=True)
    scanned.close()
    native.close()
    return data


def _mixed_native_scan_pdf() -> bytes:
    document = fitz.open()
    native_page = document.new_page(width=612, height=500)
    _insert_ocr_question(native_page, 1)

    scanned_source = fitz.open()
    source_page = scanned_source.new_page(width=612, height=500)
    _insert_ocr_question(source_page, 2)
    pixmap = source_page.get_pixmap(dpi=300, alpha=False)
    scanned_page = document.new_page(width=612, height=500)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))

    data = document.tobytes(garbage=4, deflate=True)
    scanned_source.close()
    document.close()
    return data


def _native_question_with_blank_page_pdf() -> bytes:
    native = fitz.open()
    page = native.new_page(width=612, height=500)
    _insert_ocr_question(page, 1)
    native.new_page(width=612, height=500)
    data = native.tobytes(garbage=4, deflate=True)
    native.close()
    return data


def _insert_flattened_question_text(page: fitz.Page, *, render_mode: int = 0) -> None:
    page.insert_text((36, 35), "1. Flattened answer", fontsize=12, render_mode=render_mode)
    for y, label, value in (
        (75, "A", "Alpha"),
        (115, "B", "Beta"),
        (155, "C", "Gamma"),
        (195, "D", "Delta"),
    ):
        page.insert_text(
            (36, y),
            f"{label}) {value}",
            fontsize=12,
            render_mode=render_mode,
        )


def _flattened_highlight_pdf(*, scanned: bool = False, ambiguous: bool = False) -> bytes:
    source = fitz.open()
    page = source.new_page(width=420, height=240)
    page.draw_rect(
        fitz.Rect(30, 98, 175, 120),
        color=None,
        fill=(1, 1, 0),
    )
    if ambiguous:
        page.draw_rect(
            fitz.Rect(69, 61, 76, 69),
            color=None,
            fill=(1, 1, 0),
        )
    _insert_flattened_question_text(page)
    if not scanned:
        data = source.tobytes(garbage=4, deflate=True)
        source.close()
        return data

    pixmap = page.get_pixmap(dpi=216, alpha=False, annots=False)
    searchable_scan = fitz.open()
    scanned_page = searchable_scan.new_page(width=420, height=240)
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
    _insert_flattened_question_text(scanned_page, render_mode=3)
    data = searchable_scan.tobytes(garbage=4, deflate=True)
    searchable_scan.close()
    source.close()
    return data


def _selective_annotations_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=260)
    page.insert_text((36, 35), "1. Preserve notes", fontsize=12)
    for y, label, value in (
        (75, "A", "Alpha"),
        (125, "B", "Beta"),
        (175, "C", "Gamma"),
        (225, "D", "Delta"),
    ):
        page.insert_text((36, y), f"{label}) {value}", fontsize=12)

    unrelated_highlight = page.add_highlight_annot(page.search_for("Preserve notes")[0])
    unrelated_highlight.update()
    answer_highlight = page.add_highlight_annot(page.search_for("Beta")[0])
    answer_highlight.update()
    answer_ink = page.add_ink_annot([[(50, 130), (90, 130)]])
    answer_ink.set_colors(stroke=(1, 1, 0))
    answer_ink.set_border(width=3)
    answer_ink.set_info(subject="Highlight")
    answer_ink.update()

    red_ink = page.add_ink_annot([[(105, 138), (155, 138)]])
    red_ink.set_colors(stroke=(1, 0, 0))
    red_ink.set_border(width=4)
    red_ink.update()
    note = page.add_freetext_annot(
        fitz.Rect(180, 105, 245, 143),
        "NOTE",
        fontsize=11,
        text_color=(0, 0, 1),
    )
    note.update()
    shape = page.add_rect_annot(fitz.Rect(270, 108, 305, 142))
    shape.set_colors(stroke=(0, 1, 0))
    shape.set_border(width=4)
    shape.update()

    data = document.tobytes(garbage=4, deflate=True)
    document.close()
    return data


class PdfLayoutAnalysisTests(SimpleTestCase):
    def test_inline_options_page_split_highlight_and_json_contract(self):
        data = _fixture_pdf()

        manifest = analyze_pdf(data)

        # Manifest birbaşa JSON-a verilə bilməli və inteqrasiya açarlarını
        # dəyişmədən saxlamalıdır.
        json.dumps(manifest)
        self.assertEqual(manifest["page_count"], 2)
        self.assertTrue(manifest["confidence"]["is_confident"])
        self.assertEqual(manifest["confidence"]["question_anchor_count"], 2)
        self.assertEqual(manifest["confidence"]["option_anchor_count"], 8)

        first, second = manifest["questions"]
        self.assertEqual(set(first), {"ordinal", "q_no", "stem", "options", "correct"})
        self.assertEqual((first["ordinal"], first["q_no"]), (1, 1))
        self.assertEqual(first["correct"], ["A", "C"])
        self.assertEqual(second["correct"], ["D"])
        self.assertEqual(first["options"]["B"]["text"], "Beta")
        self.assertEqual(first["options"]["C"]["text"], "Gamma continued C formula")

        c_slices = first["options"]["C"]["slices"]
        self.assertEqual([item["page_index"] for item in c_slices], [0, 1])
        self.assertTrue(all(len(item["clip"]) == 4 for item in c_slices))
        self.assertTrue(c_slices[0]["masks"])

        expected = (
            "1. First stem\n"
            "*A) Alpha\n"
            "B) Beta\n"
            "*C) Gamma continued C formula\n"
            "D) Delta\n\n"
            "2. Second stem\n"
            "A) One\n"
            "B) Two\n"
            "C) Three\n"
            "*D) Four"
        )
        self.assertEqual(manifest_to_mcq_text(manifest), expected)
        self.assertEqual(manifest["canonical_text"], expected)

    def test_renderer_masks_inline_neighbors_stitches_pages_and_hides_annotations(self):
        data = _fixture_pdf()
        manifest = analyze_pdf(data)
        first = manifest["questions"][0]

        beta_png = render_segment(data, first["options"]["B"])
        beta = Image.open(BytesIO(beta_png)).convert("RGB")
        # C label-i və Gamma qonşu segmenti maskalanmasa crop xeyli enli olar.
        self.assertLess(beta.width, 150)
        self.assertGreater(beta.width, 40)

        c_png = render_segment(data, first["options"]["C"])
        c_image = Image.open(BytesIO(c_png)).convert("RGB")
        # Page-0 "Gamma" və page-1 continuation eyni şaquli PNG-dədir.
        self.assertGreater(c_image.height, beta.height + 20)
        self.assertTrue(c_png.startswith(b"\x89PNG\r\n\x1a\n"))

        # annots=False: sarı Highlight və Ink pikselləri çıxışa düşməməlidir.
        yellow_pixels = sum(1 for red, green, blue in c_image.getdata() if red > 180 and green > 150 and blue < 100)
        self.assertEqual(yellow_pixels, 0)

    def test_renderer_rejects_sub_216_dpi(self):
        data = _fixture_pdf()
        segment = analyze_pdf(data)["questions"][0]["stem"]

        with self.assertRaisesRegex(ValueError, "ən azı 216"):
            render_segment(data, segment, dpi=215)

    def test_batch_renderer_matches_single_results_and_opens_pdf_once(self):
        data = _fixture_pdf()
        first = analyze_pdf(data)["questions"][0]
        segments = [first["stem"], first["options"]["B"], first["options"]["C"]]
        expected = [render_segment(data, segment) for segment in segments]

        with patch("apps.exams.services.pdf_layout.rendering.fitz.open", wraps=fitz.open) as open_pdf:
            rendered = render_segments(data, segments)

        self.assertEqual(open_pdf.call_count, 1)
        self.assertEqual(rendered, expected)

    def test_fail_closed_requires_a_through_d_and_contiguous_question_numbers(self):
        with self.assertRaises(LayoutConfidenceError) as missing_option:
            analyze_pdf(_invalid_pdf())
        json.dumps(missing_option.exception.manifest)
        self.assertIn("A-D", " ".join(missing_option.exception.manifest["confidence"]["issues"]))

        with self.assertRaises(LayoutConfidenceError) as bad_sequence:
            analyze_pdf(_invalid_pdf(second_q_no=3))
        issues = " ".join(bad_sequence.exception.manifest["confidence"]["issues"])
        self.assertIn("ardıcıl deyil", issues)

        diagnostic = analyze_pdf(_invalid_pdf(second_q_no=3), fail_closed=False)
        self.assertFalse(diagnostic["confidence"]["is_confident"])

    def test_contiguous_printed_subset_keeps_one_based_ordinals(self):
        manifest = analyze_pdf(_contiguous_subset_pdf(start=51))

        self.assertEqual(
            [(question["ordinal"], question["q_no"]) for question in manifest["questions"]],
            [(1, 51), (2, 52)],
        )
        self.assertTrue(manifest["confidence"]["is_confident"])
        self.assertTrue(manifest["canonical_text"].startswith("51. Subset question"))

    def test_geometry_column_and_option_subsequence_ignore_formula_anchors(self):
        manifest = analyze_pdf(_geometry_noise_pdf())

        self.assertEqual([question["q_no"] for question in manifest["questions"]], [1, 2])
        self.assertEqual(manifest["confidence"]["question_anchor_count"], 2)
        self.assertEqual(manifest["confidence"]["option_anchor_count"], 8)
        self.assertEqual(list(manifest["questions"][0]["options"]), ["A", "B", "C", "D"])

    def test_visual_only_option_gets_parse_safe_accessible_placeholder(self):
        from apps.exams.services.parsing import parse_bulk_mcq

        manifest = analyze_pdf(_visual_only_option_pdf())
        text = manifest["canonical_text"]
        parsed = parse_bulk_mcq(text)

        self.assertIn("C) [Vizual məzmun mənbə şəklindədir]", text)
        self.assertEqual(set(parsed[0]["options"]), {"A", "B", "C", "D"})

    def test_native_and_searchable_scan_flattened_yellow_answer_is_detected_and_cleaned(self):
        for scanned in (False, True):
            with self.subTest(scanned=scanned):
                data = _flattened_highlight_pdf(scanned=scanned)
                question = analyze_pdf(data)["questions"][0]
                rendered = _image(render_segment(data, question["options"]["B"]))

                self.assertEqual(question["correct"], ["B"])
                self.assertLessEqual(_yellow_pixels(rendered), 2)
                self.assertGreater(
                    sum(1 for red, green, blue in rendered.getdata() if max(red, green, blue) < 80),
                    30,
                )

    def test_ambiguous_flattened_yellow_fails_closed_without_defaulting_to_a(self):
        data = _flattened_highlight_pdf(ambiguous=True)

        with self.assertRaises(LayoutConfidenceError) as captured:
            analyze_pdf(data)

        issues = " ".join(captured.exception.manifest["confidence"]["issues"])
        self.assertIn("qeyri-müəyyəndir", issues)
        diagnostic = analyze_pdf(data, fail_closed=False)
        self.assertEqual(diagnostic["questions"][0]["correct"], [])

    def test_renderer_hides_only_answer_marks_and_preserves_unrelated_annotations(self):
        data = _selective_annotations_pdf()
        question = analyze_pdf(data)["questions"][0]

        option_b = _image(render_segment(data, question["options"]["B"]))
        stem = _image(render_segment(data, question["stem"]))

        self.assertEqual(question["correct"], ["B"])
        self.assertLessEqual(_yellow_pixels(option_b), 2)
        self.assertGreater(_red_pixels(option_b), 20)
        self.assertGreater(_blue_pixels(option_b), 5)
        self.assertGreater(_green_pixels(option_b), 20)
        self.assertGreater(_yellow_pixels(stem), 20)

    def test_tall_formula_crossing_midpoint_is_complete_without_next_option_leak(self):
        data = _tall_formula_pdf()
        question = analyze_pdf(data)["questions"][0]

        stem = _image(render_segment(data, question["stem"]))
        option_a = _image(render_segment(data, question["options"]["A"]))

        # Stem-in hündür qlifi midpoint-i keçsə də tam qalır; aşağıdakı qırmızı
        # A variantı isə stem crop-una sızmır.
        self.assertGreater(stem.height, 125)
        self.assertGreaterEqual(_dark_row_span(stem, 400, 550), 85)
        self.assertEqual(_red_pixels(stem), 0)
        self.assertEqual(_blue_pixels(stem), 0)
        self.assertGreater(_red_pixels(option_a), 1_000)
        red_rows = [
            y
            for y in range(option_a.height)
            if any(
                red > 150 and green < 90 and blue < 90
                for red, green, blue in (option_a.getpixel((x, y)) for x in range(option_a.width))
            )
        ]
        self.assertGreater(max(red_rows) - min(red_rows), 150)

    def test_previous_segment_descender_is_masked_from_next_option(self):
        data = _previous_segment_descender_pdf()
        question = analyze_pdf(data)["questions"][0]

        option_a = _image(render_segment(data, question["options"]["A"]))

        self.assertEqual(question["stem"]["text"], "Stem -")
        self.assertEqual(question["options"]["A"]["text"], "value")
        self.assertLess(option_a.width, 150)

    def test_adjacent_near_duplicate_fragment_is_removed_conservatively(self):
        previous = Image.new("RGB", (220, 100), "white")
        current = Image.new("RGB", (220, 50), "white")
        previous_draw = ImageDraw.Draw(previous)
        current_draw = ImageDraw.Draw(current)
        previous_draw.text((12, 10), "unique", fill="black")
        for draw, y_offset in ((previous_draw, 60), (current_draw, 0)):
            draw.rectangle((20, y_offset, 200, y_offset + 39), outline="black", width=2)
            draw.line((30, y_offset + 8, 190, y_offset + 31), fill="black", width=3)
            draw.text((80, y_offset + 12), "4 6 12 16", fill="black")

        deduplicated = _deduplicate_adjacent([previous, current])

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0].size, previous.size)

    @skipUnless(_REAL_SAMPLE.exists(), "Real PDF layout fixture mövcud deyil")
    def test_real_q3_q38_q270_visual_regressions(self):
        data = _REAL_SAMPLE.read_bytes()
        manifest = analyze_pdf(data)
        q3 = manifest["questions"][2]
        q38 = manifest["questions"][37]
        q270 = manifest["questions"][269]

        q3_stem = _image(render_segment(data, q3["stem"]))
        q38_stem = _image(render_segment(data, q38["stem"]))
        q38_options = [_image(render_segment(data, q38["options"][label])) for label in ("A", "B", "C", "D", "E")]
        q270_b = _image(render_segment(data, q270["options"]["B"]))
        q121_d = _image(render_segment(data, manifest["questions"][120]["options"]["D"]))
        q121_e = _image(render_segment(data, manifest["questions"][120]["options"]["E"]))

        self.assertGreaterEqual(q3_stem.height, 165)
        self.assertGreaterEqual(q38_stem.height, 138)
        self.assertLessEqual(q38_stem.height, 150)
        self.assertTrue(all(image.height >= 105 for image in q38_options))
        self.assertLess(q38_options[0].width, 250)
        self.assertLess(q270_b.height, 260)
        self.assertEqual(len(_ink_row_bands(q270_b)), 4)
        self.assertLess(q121_d.height, 130)
        self.assertEqual(len(_ink_row_bands(q121_d)), 2)
        self.assertNotEqual(q121_d.tobytes(), q121_e.tobytes())
        self.assertLessEqual(_yellow_pixels(q121_e), 2)

        expected_answers = {
            68: ["D"],
            112: ["B"],
            117: ["A"],
            121: ["D"],
            127: ["B"],
            274: ["D"],
        }
        self.assertEqual(
            {number: manifest["questions"][number - 1]["correct"] for number in expected_answers},
            expected_answers,
        )
        # PyMuPDF 1.28 rawdict bbox sırası bu split label/body sətirlərini
        # sürüşdürürdü; say yoxlamaları bunu tutmurdu. Pin upgrade-i zamanı
        # canonical option mapping ayrıca qorunmalıdır.
        expected_split_rows = {
            98: {
                "A": "if z == 4 else y1 = x; end",
                "B": "if z 4 − 5 y1 = x; end",
                "C": "if z <= 4 y1 = 5 * x; else y1 = 15 − x; end",
                "D": "if z else y1 = 15; end",
                "E": "if z << 1 else y1 = 15 − x; end",
            },
            111: {
                "A": "if z < 1 y1 = 5; else y1 = 15; end",
                "B": "if z =< 1; else y1 = 15; end",
                "C": "if z <= 4 y1 = 5 * x; else y1 = 15 − x; end",
                "D": "if z == 4 y1 = x; else y1 = x; end",
                "E": "if z == 4 y1 = x; end",
            },
            180: {
                "A": "if z >= 4 y2 = x; else y1 = 15 − x; end",
                "B": "if z = 4 y1 = 5; else y1 = 15; end",
                "C": "if z == 4 y1 = 5 * x^2; else y1 = 15 + x; end",
                "D": "if z > 5 a = 78* 2; end",
                "E": "if z <= 14 y1 = 5 * x; end",
            },
        }
        for number, expected_options in expected_split_rows.items():
            actual = {
                label: " ".join(option["text"].split())
                for label, option in manifest["questions"][number - 1]["options"].items()
            }
            self.assertEqual(actual, expected_options, msg=f"Q{number} option mapping")
        self.assertEqual(manifest["questions"][97]["correct"], ["C"])

        q68_e_image = _image(render_segment(data, manifest["questions"][67]["options"]["E"]))
        self.assertLess(q68_e_image.width, 250)
        self.assertNotIn("sum(x3", manifest["questions"][67]["options"]["E"]["text"])
        self.assertGreater(
            _image(render_segment(data, manifest["questions"][68]["stem"])).width,
            q68_e_image.width * 4,
        )

        all_options = [option for question in manifest["questions"] for option in question["options"].values()]
        self.assertEqual(len(all_options), 1_500)
        self.assertEqual(sum("?" in option["text"] for option in all_options), 1)
        for index, question in enumerate(manifest["questions"][:-1]):
            last = list(question["options"].values())[-1]
            next_stem = manifest["questions"][index + 1]["stem"]
            last_boxes = {(box["page_index"], tuple(box["rect"])) for box in last["text_boxes"]}
            next_boxes = {(box["page_index"], tuple(box["rect"])) for box in next_stem["text_boxes"]}
            self.assertFalse(last_boxes & next_boxes, msg=f"Q{question['q_no']} bleed")

    @override_settings(EXAM_PDF_OCR_ENABLED=True)
    def test_native_text_pages_never_call_ocr_runtime(self):
        with patch("apps.exams.services.pdf_layout.ocr.ocr_runtime_available") as runtime:
            manifest = analyze_pdf(_fixture_pdf())

        runtime.assert_not_called()
        self.assertEqual(len(manifest["questions"]), 2)

    @override_settings(EXAM_PDF_OCR_ENABLED=False)
    def test_mixed_native_scan_fails_closed_when_ocr_is_disabled(self):
        with self.assertRaises(LayoutConfidenceError) as captured:
            analyze_pdf(_mixed_native_scan_pdf())

        issues = " ".join(captured.exception.manifest["confidence"]["issues"])
        self.assertIn("səhifə 2", issues)
        self.assertIn("OCR söndürülüb", issues)

    @override_settings(EXAM_PDF_OCR_ENABLED=True, EXAM_PDF_OCR_MAX_PAGES=100)
    def test_mixed_native_scan_fails_closed_when_ocr_runtime_errors(self):
        with (
            patch(
                "apps.exams.services.pdf_layout.ocr.ocr_runtime_available",
                return_value=True,
            ),
            patch.object(
                fitz.Page,
                "get_textpage_ocr",
                side_effect=RuntimeError("tesseract failed"),
            ),
            self.assertRaises(LayoutConfidenceError) as captured,
        ):
            analyze_pdf(_mixed_native_scan_pdf())

        issues = " ".join(captured.exception.manifest["confidence"]["issues"])
        self.assertIn("OCR nəticə vermədi", issues)

    @override_settings(EXAM_PDF_OCR_ENABLED=True, EXAM_PDF_OCR_MAX_PAGES=1)
    def test_mixed_native_scan_fails_closed_at_ocr_page_limit(self):
        with (
            patch("apps.exams.services.pdf_layout.ocr.ocr_runtime_available") as runtime,
            self.assertRaises(LayoutConfidenceError) as captured,
        ):
            analyze_pdf(_mixed_native_scan_pdf())

        runtime.assert_not_called()
        issues = " ".join(captured.exception.manifest["confidence"]["issues"])
        self.assertIn("səhifə limiti", issues)

    @override_settings(EXAM_PDF_OCR_ENABLED=False)
    def test_native_document_blank_page_is_not_an_ocr_failure(self):
        with patch("apps.exams.services.pdf_layout.ocr.ocr_runtime_available") as runtime:
            manifest = analyze_pdf(_native_question_with_blank_page_pdf())

        runtime.assert_not_called()
        self.assertTrue(manifest["confidence"]["is_confident"])

    @override_settings(
        EXAM_PDF_OCR_ENABLED=True,
        EXAM_PDF_OCR_DPI=150,
        EXAM_PDF_OCR_MAX_PAGES=500,
        EXAM_PDF_OCR_LANG="aze",
    )
    def test_ocr_settings_are_clamped_and_language_falls_back_to_english(self):
        self.assertEqual(_dpi(), 300)
        self.assertEqual(_max_pages(), 100)
        self.assertEqual(_languages(), ("aze", "eng"))

    @override_settings(
        EXAM_PDF_OCR_ENABLED=True,
        EXAM_PDF_OCR_DPI=150,
        EXAM_PDF_OCR_MAX_PAGES=100,
        EXAM_PDF_OCR_LANG="aze",
    )
    def test_ocr_page_falls_back_from_azerbaijani_to_english_rawdict(self):
        class FakePage:
            def __init__(self):
                self.ocr_calls = []

            def get_text(self, _option, *, sort, textpage=None):
                if textpage is None:
                    return {"blocks": []}
                return {
                    "blocks": [
                        {
                            "type": 0,
                            "lines": [{"spans": [{"chars": [{"c": "1", "bbox": (1, 2, 3, 4)}]}]}],
                        }
                    ]
                }

            def get_textpage_ocr(self, **kwargs):
                self.ocr_calls.append(kwargs)
                if kwargs["language"] == "aze":
                    raise RuntimeError("aze traineddata yoxdur")
                return object()

        page = FakePage()
        with patch("apps.exams.services.pdf_layout.ocr.ocr_runtime_available", return_value=True):
            raw = page_rawdict(page, 0)

        self.assertEqual([call["language"] for call in page.ocr_calls], ["aze", "eng"])
        self.assertTrue(all(call["dpi"] == 300 and call["full"] for call in page.ocr_calls))
        self.assertEqual(raw["blocks"][0]["lines"][0]["spans"][0]["chars"][0]["bbox"], (1, 2, 3, 4))

    @override_settings(EXAM_PDF_OCR_ENABLED=False)
    def test_image_only_pdf_stays_fail_closed_when_ocr_is_disabled(self):
        with self.assertRaises(LayoutConfidenceError):
            analyze_pdf(_image_only_question_pdf())

    @skipUnless(ocr_runtime_available(), "Tesseract OCR runtime mövcud deyil")
    @override_settings(
        EXAM_PDF_OCR_ENABLED=True,
        EXAM_PDF_OCR_DPI=300,
        EXAM_PDF_OCR_MAX_PAGES=100,
        EXAM_PDF_OCR_LANG="eng",
    )
    def test_image_only_pdf_uses_ocr_geometry(self):
        manifest = analyze_pdf(_image_only_question_pdf())

        self.assertEqual(len(manifest["questions"]), 1)
        self.assertEqual(list(manifest["questions"][0]["options"]), ["A", "B", "C", "D"])

    @skipUnless(ocr_runtime_available(), "Tesseract OCR runtime mövcud deyil")
    @override_settings(
        EXAM_PDF_OCR_ENABLED=True,
        EXAM_PDF_OCR_DPI=300,
        EXAM_PDF_OCR_MAX_PAGES=100,
        EXAM_PDF_OCR_LANG="eng",
    )
    def test_mixed_pdf_keeps_native_page_and_ocrs_only_scanned_page(self):
        manifest = analyze_pdf(_mixed_native_scan_pdf())

        self.assertEqual([question["q_no"] for question in manifest["questions"]], [1, 2])
        self.assertTrue(manifest["confidence"]["is_confident"])
