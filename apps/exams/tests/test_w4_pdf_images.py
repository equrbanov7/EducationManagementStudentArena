"""W4 2026-09-14 (w3import yarımçıq 6) — PDF mətn-fallback yolunda gömülü raster şəkillər.

Layout inamsız PDF (məs. sual nömrələri ardıcıl deyil: 1, 3) vizual-first
bundle-a düşmür və mətn yoluna keçir; əvvəl sənədin şəkilləri itirdi. İndi
`parsing/pdf_images` şəkilləri sual bölgəsinə görə (`page.get_images` +
`get_image_rects` ↔ sual/variant lövbərləri) `[[img:N]]` markeri ilə mətnə
bağlayır, `import_media_pdf.stash_pdf_image_bundle` DOCX-formatlı bundle yazır
və save DOCX ilə eyni yolla `BankQuestion.image` / `BankQuestionOption.image`
doldurur. PDF fikstürü testin içində PyMuPDF ilə qurulur.
"""

from __future__ import annotations

import io
import tempfile
import unittest

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from PIL import Image

from apps.accounts.models import ProfileRole
from apps.exams.models import BankQuestion, QuestionBank
from apps.exams.services import import_media
from apps.exams.services.import_media_docx import load_docx_manifest
from apps.exams.services.import_media_pdf import stash_pdf_image_bundle
from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.parsing.extraction._deps import fitz
from apps.exams.services.parsing.pdf_images import extract_pdf_question_images, pdf_has_raster_images
from apps.exams.services.visual_import_upload import prepare_question_upload
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _png(width=120, height=90, color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def _jpeg(width=60, height=15, color=(30, 30, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "JPEG")
    return buffer.getvalue()


LINE_STEP = 22


def build_pdf(pages, *, header_logo=False, full_page_background=False) -> bytes:
    """``pages``: hər səhifə üçün sətir siyahısı; ``("img", stream, y0, y1)`` şəkil yerləşimidir.

    Mətn sətirləri ``"1. Sual?"`` / ``"A) bir"`` (ASCII — helv fontu). Şəkil
    tuple-ında ``y0/y1`` mütləq koordinatdır ki, test şəkilin hansı sətirlərlə
    üst-üstə düşdüyünü dəqiq idarə etsin.
    """

    document = fitz.open()
    for page_items in pages:
        page = document.new_page(width=595, height=842)
        if full_page_background:
            page.insert_image(fitz.Rect(0, 0, 595, 842), stream=_png(600, 850, (250, 250, 250)))
        if header_logo:
            page.insert_image(fitz.Rect(50, 10, 110, 30), stream=_png(60, 20, (0, 120, 0)))
        y = 60
        for item in page_items:
            if isinstance(item, tuple):
                _kind, stream, y0, y1 = item
                page.insert_image(fitz.Rect(300, y0, 420, y1), stream=stream)
                continue
            if item:
                page.insert_text((50, y), item, fontsize=12, fontname="helv")
            y += LINE_STEP
    data = document.tobytes()
    document.close()
    return data


def _line_y(index: int) -> float:
    """``build_pdf``-də ``index``-ci MƏTN sətrinin baseline-ı (şəkil tuple-ları sayılmır)."""

    return 60 + LINE_STEP * index


# Sual 1 (sətir 0–4) sağda stem şəkli (variantlardan yuxarı başlayır),
# sual 3 (sətir 6–10) B variantının sətrində kiçik JPEG. Nömrələr 1 və 3 —
# vizual-first layout QƏSDƏN inamsızdır (ardıcıl deyil) → mətn fallback.
def gapped_pages():
    return [
        [
            "1. Which figure is shown?",
            ("img", _png(), _line_y(0) - 12, _line_y(2)),
            "A) square",
            "B) circle",
            "C) triangle",
            "D) rectangle",
            "",
            "3. Second question",
            "A) one",
            ("img", _jpeg(), _line_y(8) - 8, _line_y(8) + 4),
            "B) two",
            "C) three",
            "D) four",
        ]
    ]


@unittest.skipUnless(fitz is not None, "PyMuPDF yoxdur")
class PdfQuestionImageExtractionTests(SimpleTestCase):
    def _text(self, data: bytes) -> str:
        from apps.exams.services.parsing import extract_text_from_upload

        return extract_text_from_upload(SimpleUploadedFile("q.pdf", data))

    def test_images_are_tied_to_stem_and_option_by_region(self):
        data = build_pdf(gapped_pages())
        self.assertTrue(pdf_has_raster_images(data))
        text = self._text(data)
        extract = extract_pdf_question_images(data, text)

        self.assertEqual(extract.placements, [("1", "stem", 1), ("3", "B", 2)])
        self.assertEqual([image.index for image in extract.images], [1, 2])
        self.assertEqual([image.content_type for image in extract.images], ["image/png", "image/jpeg"])
        self.assertEqual((extract.images[0].width, extract.images[0].height), (120, 90))
        lines = extract.text.splitlines()
        self.assertTrue(lines[0].startswith("1. Which figure is shown?"))
        self.assertTrue(lines[0].endswith("[[img:1]]"), lines[0])
        option_b = next(line for line in lines if line.startswith("B) two"))
        self.assertTrue(option_b.endswith("[[img:2]]"), option_b)
        self.assertEqual(extract.text.count("[[img:"), 2)
        self.assertEqual(extract.warnings, [])

        # Parser markerləri media_refs-ə çıxarır — mətn təmiz qalır.
        parsed = parse_bulk_mcq(extract.text)
        self.assertEqual([q["q_no"] for q in parsed], ["1", "3"])
        self.assertEqual(parsed[0]["media_refs"], {"stem": [1]})
        self.assertEqual(parsed[1]["media_refs"], {"B": [2]})
        self.assertEqual(parsed[1]["options"]["B"], "two")

    def test_header_logo_and_full_page_background_are_skipped_with_warnings(self):
        data = build_pdf(gapped_pages(), header_logo=True, full_page_background=True)
        extract = extract_pdf_question_images(data, self._text(data))
        self.assertEqual(extract.placements, [("1", "stem", 1), ("3", "B", 2)])
        self.assertEqual(len(extract.images), 2)
        unsupported, unanchored = extract.warnings
        # Tam səhifə fonu → mövcud `images_unsupported_skipped` (tərcüməli) sayğacı.
        self.assertTrue(unsupported.startswith("1 "), unsupported)
        self.assertIn("EMF/WMF/SVG", unsupported)
        # Başlıq loqosu → `pdf_images_unanchored_skipped` (kataloqa fill skripti ilə
        # düşür; ondan əvvəl pgettext açarın özünü qaytarır — hər iki forma qəbuldur).
        self.assertTrue(
            unanchored == "pdf_images_unanchored_skipped" or unanchored.startswith("1 "),
            unanchored,
        )

    def test_same_image_placed_twice_is_stored_once(self):
        stream = _png(50, 50, (10, 200, 10))
        pages = [
            [
                "1. First",
                ("img", stream, _line_y(0) - 10, _line_y(0) + 5),
                "A) a",
                "B) b",
                "C) c",
                "D) d",
                "",
                "3. Third",
                ("img", stream, _line_y(6) - 10, _line_y(6) + 5),
                "A) a",
                "B) b",
                "C) c",
                "D) d",
            ]
        ]
        data = build_pdf(pages)
        extract = extract_pdf_question_images(data, self._text(data))
        self.assertEqual(len(extract.images), 1)
        self.assertEqual(extract.placements, [("1", "stem", 1), ("3", "stem", 1)])
        self.assertEqual(extract.text.count("[[img:1]]"), 2)

    def test_image_at_top_of_next_page_belongs_to_previous_question(self):
        pages = [
            ["1. First", "A) a", "B) b", "C) c", "D) d"],
            [("img", _png(), 40, 100), "", "", "", "3. Third", "A) a", "B) b", "C) c", "D) d"],
        ]
        data = build_pdf(pages)
        extract = extract_pdf_question_images(data, self._text(data))
        # Bölgə səhifə keçidini əhatə edir: 3-cü sualdan ƏVVƏLKİ şəkil 1-ci sualındır;
        # üstü sonuncu variantın (D) sətrindən aşağıda olduğu üçün D-yə bağlanır.
        self.assertEqual(extract.placements, [("1", "D", 1)])

    def test_oversized_image_is_downscaled_like_docx(self):
        # 2600×400 px → DOCX ilə eyni qapı (MAX_SIDE_PX=2000): 2000×308.
        pages = [["1. First", ("img", _png(2600, 400, (5, 5, 5)), _line_y(0) - 10, _line_y(0) + 10), "A) a", "B) b"]]
        data = build_pdf(pages)
        extract = extract_pdf_question_images(data, self._text(data))
        self.assertEqual(len(extract.images), 1)
        self.assertEqual(extract.images[0].width, 2000)
        self.assertLess(extract.images[0].height, 400)

    def test_pdf_without_images_is_reported_quickly(self):
        data = build_pdf([["1. First", "A) a", "B) b", "C) c", "D) d"]])
        self.assertFalse(pdf_has_raster_images(data))
        extract = extract_pdf_question_images(data, "1. First\nA) a\nB) b")
        self.assertEqual(extract.images, [])
        self.assertEqual(extract.text, "1. First\nA) a\nB) b")


@unittest.skipUnless(fitz is not None, "PyMuPDF yoxdur")
class PdfImageBundleFlowTests(TestCase):
    """PDF (layout inamsız) → preview → save: şəkillər DOCX yolu ilə bazaya bağlanır."""

    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.teacher = User.objects.create_user(
            username="w4-pdf-teacher", email="w4-pdf@example.com", password="StrongPass123!"
        )
        self.organization = Organization.objects.create(
            name="W4 Pdf Org",
            slug="w4-pdf-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.organization
        profile.organization_type = self.organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=self.teacher,
            organization=self.organization,
            defaults={"role": self.organization.roles.get(name="teacher"), "is_primary": True, "is_active": True},
        )
        self.bank = QuestionBank.objects.create(
            name="W4 Pdf Bank",
            created_by=self.teacher,
            organization=self.organization,
            default_question_type="test",
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()
        self.url = reverse("exams:question_bank_bulk_add", kwargs={"bank_id": self.bank.id})

    def test_stash_writes_docx_shaped_manifest_with_pdf_origin(self):
        upload = SimpleUploadedFile("suallar.pdf", build_pdf(gapped_pages()))
        text, token = stash_pdf_image_bundle(upload, owner_id=self.teacher.pk, organization_id=self.organization.pk)
        self.addCleanup(import_media.clear_stash, token)
        self.assertIn("[[img:1]]", text)
        manifest = load_docx_manifest(token)
        self.assertEqual(manifest["kind"], "docx")
        self.assertEqual(manifest["source"]["origin"], "pdf")
        self.assertEqual(manifest["source"]["owner_id"], self.teacher.pk)
        self.assertEqual(manifest["source"]["filename"], "suallar.pdf")
        self.assertEqual([entry["name"] for entry in manifest["images"]], ["img_1.png", "img_2.jpg"])
        for entry in manifest["images"]:
            self.assertTrue(import_media.default_storage.exists(f"question_imports/{token}/{entry['name']}"))
        self.assertEqual(manifest["canonical_text"], text)

    def test_prepare_question_upload_falls_back_to_image_bundle_when_layout_is_not_confident(self):
        text, token = prepare_question_upload(
            SimpleUploadedFile("suallar.pdf", build_pdf(gapped_pages())),
            owner_id=self.teacher.pk,
            organization_id=self.organization.pk,
        )
        self.assertEqual(len(token), 32)
        self.addCleanup(import_media.clear_stash, token)
        self.assertIn("[[img:1]]", text)
        self.assertIn("[[img:2]]", text)

    def test_pdf_without_images_keeps_text_only_path(self):
        text, token = prepare_question_upload(
            SimpleUploadedFile("duz.pdf", build_pdf([["1. First", "A) a", "B) b", "C) c", "D) d", "", "3. Third"]])),
            owner_id=self.teacher.pk,
            organization_id=self.organization.pk,
        )
        self.assertEqual(token, "")
        self.assertIn("1. First", text)
        self.assertNotIn("[[img:", text)

    def test_preview_then_save_attaches_pdf_images_like_docx(self):
        response = self.client.post(
            self.url,
            {
                "action": "preview",
                "raw_text": "",
                "language": "az",
                "upload_file": SimpleUploadedFile("suallar.pdf", build_pdf(gapped_pages())),
            },
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('name="math_token" value="', html)
        token = html.split('name="math_token" value="', 1)[1].split('"', 1)[0]
        self.assertEqual(len(token), 32)
        self.assertIn("q-badge--image", html)
        self.assertNotIn("[[img:", html.split('id="questionList"', 1)[1])

        preview_url = reverse("exams:question_import_visual_preview", kwargs={"token": token, "source_index": 0})
        image_response = self.client.get(preview_url)
        self.assertEqual(image_response.status_code, 200)
        self.assertTrue(image_response.content.startswith(b"\x89PNG"))

        raw_text = response.context["raw_text"]
        self.assertIn("[[img:1]]", raw_text)
        save = self.client.post(
            self.url,
            {"action": "save", "raw_text": raw_text, "math_token": token, "language": "az", "selected_indices": "1,2"},
        )
        self.assertEqual(save.status_code, 302)

        questions = list(BankQuestion.objects.filter(bank=self.bank).order_by("id"))
        self.assertEqual(len(questions), 2)
        first, second = questions
        self.assertEqual(first.text, "Which figure is shown?")
        self.assertTrue(first.image, "1-ci sualın stem şəkli bağlanmalıdır")
        self.assertFalse(first.image_replaces_text)
        self.assertTrue(first.image.storage.exists(first.image.name))
        self.assertFalse(second.image)
        options = {opt.label: opt for opt in second.options.all()}
        self.assertTrue(options["B"].image, "3-cü sualın B variantı şəkilli olmalıdır")
        self.assertEqual(options["B"].text, "two")
        self.assertFalse(options["A"].image)
        self.assertFalse(import_media.default_storage.exists(f"question_imports/{token}/manifest.json"))
