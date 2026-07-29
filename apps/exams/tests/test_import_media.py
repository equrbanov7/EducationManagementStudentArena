"""Canonical PDF import media pipeline integration tests."""

from __future__ import annotations

import hashlib
import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

import fitz
from PIL import Image

from apps.exams.models import BankQuestion, BankQuestionOption, QuestionBank
from apps.exams.services.import_media import (
    _validate_manifest,
    attach_import_media_batch,
    attach_math_images,
    bind_import_manifest,
    clear_stash,
    get_stashed_import_text,
    stash_math_images,
)
from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.parsing.extraction.safety import _dangerous_action
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _visual_pdf() -> bytes:
    """Mətn, 2D formula xətti və rəngli vektor qrafikləri olan MCQ PDF."""

    document = fitz.open()
    page = document.new_page(width=420, height=280)
    page.insert_text((36, 28), "1. Evaluate the visual expression", fontsize=12)
    page.insert_text((132, 52), "x + 1", fontsize=12)
    page.draw_line((126, 58), (178, 58), color=(0, 0, 0), width=1.5)
    page.insert_text((148, 75), "2", fontsize=12)
    # Text extraction bu formanı görmür; stem PNG-də qalması fidelity sübutudur.
    page.draw_rect(
        fitz.Rect(210, 45, 225, 60),
        color=(1, 0, 0),
        fill=(1, 0, 0),
    )

    page.insert_text((36, 105), "A) First option", fontsize=12)
    page.draw_rect(
        fitz.Rect(190, 112, 205, 125),
        color=(0, 0, 1),
        fill=(0, 0, 1),
    )
    page.insert_text((36, 145), "B) Second option", fontsize=12)
    page.insert_text((36, 185), "C) Third option", fontsize=12)
    page.insert_text((36, 225), "D) Fourth option", fontsize=12)

    data = document.tobytes(garbage=4, deflate=True)
    document.close()
    return data


def _incomplete_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=420, height=240)
    page.insert_text((36, 30), "1. Missing an option", fontsize=12)
    for index, label in enumerate("ABC", start=1):
        page.insert_text((36, 30 + index * 38), f"{label}) value", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _stub_manifest() -> dict:
    segment = {
        "text": "value",
        "slices": [{"page_index": 0, "clip": [0, 0, 10, 10], "masks": []}],
    }
    return {
        "page_count": 1,
        "questions": [
            {
                "ordinal": 1,
                "q_no": 1,
                "stem": {**segment, "text": "Image prompt"},
                "options": {label: {**segment, "text": label} for label in "ABCD"},
                "correct": ["A"],
            }
        ],
        "canonical_text": ("1. Image prompt\n*A) A\nB) B\nC) C\nD) D"),
        "confidence": {
            "is_confident": True,
            "question_anchor_count": 1,
            "option_anchor_count": 4,
            "issues": [],
        },
    }


def _oriented_jpeg() -> bytes:
    image = Image.new("RGB", (1200, 600), "white")
    image.paste((220, 20, 20), (0, 0, 80, 80))
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, format="JPEG", quality=95, exif=exif)
    return output.getvalue()


def _has_color(png: bytes, color: str) -> bool:
    image = Image.open(BytesIO(png)).convert("RGB")
    if color == "red":
        return any(red > 180 and green < 80 and blue < 80 for red, green, blue in image.getdata())
    return any(blue > 180 and red < 80 and green < 80 for red, green, blue in image.getdata())


@override_settings(MEDIA_URL="/media/")
class ImportMediaPipelineTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.owner = User.objects.create_user(
            username="pdf_import_owner",
            email="pdf-import@example.com",
            password="pw",
        )
        self.organization = Organization.objects.create(
            name="PDF Import Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.bank = QuestionBank.objects.create(
            name="PDF Visual Bank",
            created_by=self.owner,
            organization=self.organization,
        )
        self.tokens: set[str] = set()
        self.addCleanup(self._clear_tokens)

    def _clear_tokens(self):
        for token in self.tokens:
            clear_stash(token)

    def _stash(self) -> str:
        upload = SimpleUploadedFile(
            "visual-questions.pdf",
            _visual_pdf(),
            content_type="application/pdf",
        )
        token = stash_math_images(
            upload,
            owner_id=self.owner.pk,
            organization_id=self.organization.pk,
        )
        self.assertIsNotNone(token)
        self.tokens.add(token)
        return token

    def _question(self, *, labels: str = "ABCD") -> BankQuestion:
        question = BankQuestion.objects.create(
            bank=self.bank,
            text="Parsed fallback text",
            question_type="test",
        )
        # Qəsdən tərs insertion sırası: bağlama queryset sırasından asılı olmamalıdır.
        for label in reversed(labels):
            BankQuestionOption.objects.create(
                question=question,
                label=label,
                text=f"Parsed option {label}",
            )
        return question

    def _canonical_parsed(self, token: str) -> list[dict]:
        manifest_name = f"question_imports/{token}/manifest.json"
        with default_storage.open(manifest_name, "rb") as handle:
            manifest = json.load(handle)
        return parse_bulk_mcq(manifest["canonical_text"])

    def test_stash_bind_and_batch_attach_preserve_stem_formula_and_option_graphic(self):
        token = self._stash()
        source_name = f"question_imports/{token}/source.pdf"
        manifest_name = f"question_imports/{token}/manifest.json"
        self.assertTrue(default_storage.exists(source_name))
        self.assertTrue(default_storage.exists(manifest_name))

        with default_storage.open(manifest_name, "rb") as handle:
            manifest = json.load(handle)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertTrue(manifest["confidence"]["is_confident"])
        self.assertEqual(manifest["source"]["owner_id"], self.owner.pk)
        self.assertEqual(manifest["source"]["organization_id"], str(self.organization.pk))
        self.assertEqual(manifest["source"]["filename"], "visual-questions.pdf")
        self.assertEqual(
            manifest["source"]["original_sha256"],
            manifest["source"]["canonical_pdf_sha256"],
        )
        self.assertEqual(
            manifest["source"]["original_byte_size"],
            manifest["source"]["canonical_pdf_byte_size"],
        )

        parsed = parse_bulk_mcq(manifest["canonical_text"])
        returned = bind_import_manifest(
            token,
            parsed,
            owner_id=self.owner.pk,
            organization_id=self.organization.pk,
        )
        self.assertIs(returned, parsed)
        self.assertEqual(parsed[0]["source_index"], 0)
        self.assertIs(parsed[0]["has_visual_source"], True)

        question = self._question()
        real_storage_open = default_storage.open
        real_fitz_open = fitz.open
        with (
            patch.object(default_storage, "open", wraps=real_storage_open) as storage_open,
            patch(
                "apps.exams.services.pdf_layout.rendering.fitz.open",
                wraps=real_fitz_open,
            ) as pdf_open,
        ):
            attached = attach_import_media_batch(
                token,
                [(parsed[0]["source_index"], question)],
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )

        self.assertEqual(attached, 1)
        source_opens = [call for call in storage_open.call_args_list if call.args[0] == source_name]
        self.assertEqual(len(source_opens), 1)
        self.assertEqual(pdf_open.call_count, 1)

        question.refresh_from_db()
        options = {option.label: option for option in question.options.all()}
        self.assertTrue(question.image)
        self.assertTrue(question.image_replaces_text)
        self.assertEqual(set(options), set("ABCD"))
        self.assertTrue(all(option.image for option in options.values()))
        self.assertTrue(all(option.image_replaces_text for option in options.values()))

        with question.image.open("rb") as handle:
            stem_png = handle.read()
        with options["A"].image.open("rb") as handle:
            option_png = handle.read()
        self.assertTrue(stem_png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(option_png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(_has_color(stem_png, "red"))
        self.assertTrue(_has_color(option_png, "blue"))

        clear_stash(token)
        self.assertFalse(default_storage.exists(source_name))
        self.assertFalse(default_storage.exists(manifest_name))
        # Final question media stash cleanup-dan sonra da qalmalıdır.
        self.assertTrue(default_storage.exists(question.image.name))

    def test_manifest_accepts_contiguous_non_one_printed_question_numbers(self):
        manifest = _stub_manifest()
        manifest.update(schema_version=2, source={})
        manifest["questions"][0]["q_no"] = 51
        second = json.loads(json.dumps(manifest["questions"][0]))
        second.update(ordinal=2, q_no=52)
        manifest["questions"].append(second)

        self.assertIs(_validate_manifest(manifest), manifest)
        manifest["questions"][1]["q_no"] = 53
        with self.assertRaisesRegex(ValueError, "çap sual sırası"):
            _validate_manifest(manifest)

    def test_bind_and_attach_fail_closed_on_sequence_scope_and_option_mismatch(self):
        token = self._stash()
        wrong_number = [{"q_no": "2"}]
        with self.assertRaisesRegex(ValueError, "nömrəsi uyğun deyil"):
            bind_import_manifest(
                token,
                wrong_number,
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )
        self.assertNotIn("source_index", wrong_number[0])

        parsed = self._canonical_parsed(token)
        with self.assertRaises(PermissionDenied):
            bind_import_manifest(
                token,
                parsed,
                owner_id=self.owner.pk + 1,
                organization_id=self.organization.pk,
            )
        self.assertNotIn("source_index", parsed[0])

        tampered = self._canonical_parsed(token)
        tampered[0]["options"]["A"] = "Changed after preview"
        with self.assertRaisesRegex(ValueError, "məzmunu uyğun deyil"):
            bind_import_manifest(
                token,
                tampered,
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )
        self.assertNotIn("source_index", tampered[0])

        scoped_question = self._question()
        with self.assertRaises(PermissionDenied):
            attach_import_media_batch(
                token,
                [(0, scoped_question)],
                owner_id=self.owner.pk,
                organization_id="another-organization",
            )
        scoped_question.refresh_from_db()
        self.assertFalse(scoped_question.image)
        self.assertFalse(scoped_question.image_replaces_text)

        question = self._question(labels="ABC")
        with self.assertRaisesRegex(ValueError, "variantları uyğun deyil"):
            attach_import_media_batch(
                token,
                [(0, question)],
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )
        question.refresh_from_db()
        self.assertFalse(question.image)
        self.assertFalse(question.image_replaces_text)
        self.assertFalse(question.options.exclude(image="").exists())
        self.assertFalse(question.options.filter(image_replaces_text=True).exists())

    def test_attach_rolls_back_files_and_flags_when_model_save_fails(self):
        token = self._stash()
        question = self._question()
        original_save = BankQuestionOption.save

        def failing_save(instance, *args, **kwargs):
            if instance.label == "B":
                raise RuntimeError("simulated option save failure")
            return original_save(instance, *args, **kwargs)

        with (
            patch.object(BankQuestionOption, "save", new=failing_save),
            self.assertRaisesRegex(RuntimeError, "simulated"),
        ):
            attach_import_media_batch(
                token,
                [(0, question)],
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )

        question.refresh_from_db()
        self.assertFalse(question.image)
        self.assertFalse(question.image_replaces_text)
        for option in question.options.all():
            self.assertFalse(option.image)
            self.assertFalse(option.image_replaces_text)
        bank_media = Path(self.media_directory.name) / "bank_media"
        self.assertEqual(list(bank_media.rglob("*.png")) if bank_media.exists() else [], [])

    def test_large_attach_renders_in_bounded_chunks(self):
        questions = [self._question() for _ in range(25)]
        source_questions = [
            {
                "stem": {"kind": "stem"},
                "options": {label: {"kind": label} for label in "ABCD"},
            }
            for _ in questions
        ]
        png_buffer = BytesIO()
        Image.new("RGB", (2, 2), "white").save(png_buffer, format="PNG")
        png = png_buffer.getvalue()
        chunk_sizes = []

        def render(_source, segments):
            chunk_sizes.append(len(segments))
            return [png] * len(segments)

        with (
            patch(
                "apps.exams.services.import_media._load_manifest",
                return_value={
                    "source": {
                        "owner_id": self.owner.pk,
                        "organization_id": self.organization.pk,
                    },
                    "questions": source_questions,
                },
            ),
            patch("apps.exams.services.import_media._load_source", return_value=b"%PDF"),
            patch("apps.exams.services.pdf_layout.render_segments", side_effect=render),
        ):
            attached = attach_import_media_batch(
                "b" * 32,
                list(enumerate(questions)),
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )

        self.assertEqual(attached, 25)
        self.assertEqual(chunk_sizes, [120, 5])
        self.assertEqual(BankQuestion.objects.filter(image_replaces_text=True).count(), 25)
        self.assertEqual(BankQuestionOption.objects.filter(image_replaces_text=True).count(), 100)

    def test_stash_layout_and_storage_failures_never_return_partial_token(self):
        invalid = SimpleUploadedFile(
            "invalid-layout.pdf",
            _incomplete_pdf(),
            content_type="application/pdf",
        )
        with self.assertRaisesRegex(ValueError, "layout"):
            stash_math_images(invalid)
        import_root = Path(self.media_directory.name) / "question_imports"
        self.assertEqual(list(import_root.rglob("*")) if import_root.exists() else [], [])

        upload = SimpleUploadedFile(
            "storage-failure.pdf",
            _visual_pdf(),
            content_type="application/pdf",
        )
        real_save = default_storage.save
        written_names: list[str] = []

        def fail_manifest_write(name, content, *args, **kwargs):
            if name.endswith("/manifest.json"):
                raise OSError("manifest write failed")
            written_names.append(name)
            return real_save(name, content, *args, **kwargs)

        with (
            patch.object(default_storage, "save", side_effect=fail_manifest_write),
            self.assertRaisesRegex(OSError, "manifest write failed"),
        ):
            stash_math_images(upload)
        self.assertEqual(len(written_names), 1)
        failed_prefix = written_names[0].rsplit("/", 1)[0]
        self.assertFalse(default_storage.exists(f"{failed_prefix}/source.pdf"))
        self.assertFalse(default_storage.exists(f"{failed_prefix}/manifest.json"))

    def test_visual_stash_reuses_upload_security_guards(self):
        active_pdf = SimpleUploadedFile(
            "active.pdf",
            _visual_pdf() + b"\n/JavaScript",
            content_type="application/pdf",
        )
        with (
            patch("apps.exams.services.import_media.extract_pdf_layout") as extract,
            self.assertRaises(ValueError),
        ):
            stash_math_images(active_pdf)
        extract.assert_not_called()

        late_action = SimpleUploadedFile(
            "late-action.pdf",
            b"%PDF-1.4\n" + b"x" * (300 * 1024) + b"/OpenAction",
            content_type="application/pdf",
        )
        with (
            patch("apps.exams.services.import_media.extract_pdf_layout") as extract,
            self.assertRaises(ValueError),
        ):
            stash_math_images(late_action)
        extract.assert_not_called()

        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        page[NameObject("/AA")] = DictionaryObject()
        structured = BytesIO()
        writer.write(structured)
        with (
            patch("apps.exams.services.import_media.extract_pdf_layout") as extract,
            self.assertRaises(ValueError),
        ):
            stash_math_images(SimpleUploadedFile("additional-action.pdf", structured.getvalue()))
        extract.assert_not_called()

        disguised = SimpleUploadedFile(
            "disguised.png",
            b"%PDF-1.4",
            content_type="image/png",
        )
        with self.assertRaises(ValueError):
            stash_math_images(disguised)

    def test_pdf_action_audit_is_bounded_for_cyclic_next_chain(self):
        action = {}
        action["/Next"] = action

        self.assertFalse(_dangerous_action(action))
        action["/JS"] = "alert(1)"
        self.assertTrue(_dangerous_action(action))

    def test_legacy_attach_wrapper_maps_printed_number_to_zero_based_index(self):
        token = self._stash()
        sentinel = object()
        with patch(
            "apps.exams.services.import_media.attach_import_media_batch",
        ) as batch_attach:
            attach_math_images(token, "1", sentinel)
        batch_attach.assert_called_once_with(token, [(0, sentinel)])

    def test_non_pdf_stash_remains_a_noop_for_legacy_callers(self):
        upload = SimpleUploadedFile("questions.txt", b"1. text", content_type="text/plain")
        self.assertIsNone(stash_math_images(upload))

    def test_oriented_image_becomes_lossless_300_dpi_pdf_with_split_hash_metadata(self):
        original = _oriented_jpeg()
        upload = SimpleUploadedFile(
            "phone-capture.jpeg",
            original,
            content_type="image/jpeg",
        )
        typed_manifest = Mock()
        typed_manifest.to_dict.return_value = _stub_manifest()
        captured: dict[str, bytes] = {}

        def extract(canonical_pdf, *, fail_closed):
            self.assertTrue(fail_closed)
            captured["canonical_pdf"] = canonical_pdf
            return typed_manifest

        with patch(
            "apps.exams.services.import_media.extract_pdf_layout",
            side_effect=extract,
        ):
            token = stash_math_images(
                upload,
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            )
        self.tokens.add(token)
        canonical_pdf = captured["canonical_pdf"]

        with fitz.open(stream=canonical_pdf, filetype="pdf") as document:
            self.assertEqual(document.page_count, 1)
            page = document[0]
            # EXIF orientation=6 1200x600 mənbəni 600x1200 edir.
            self.assertAlmostEqual(page.rect.width, 600 * 72 / 300, places=2)
            self.assertAlmostEqual(page.rect.height, 1200 * 72 / 300, places=2)
            embedded = page.get_images(full=True)
            self.assertEqual((embedded[0][2], embedded[0][3]), (600, 1200))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
            self.assertEqual((pixmap.width, pixmap.height), (600, 1200))

        manifest_name = f"question_imports/{token}/manifest.json"
        source_name = f"question_imports/{token}/source.pdf"
        with default_storage.open(manifest_name, "rb") as handle:
            manifest = json.load(handle)
        with default_storage.open(source_name, "rb") as handle:
            stored_pdf = handle.read()
        source = manifest["source"]
        self.assertEqual(source["filename"], "phone-capture.jpeg")
        self.assertEqual(source["original_byte_size"], len(original))
        self.assertEqual(source["original_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(source["canonical_pdf_byte_size"], len(canonical_pdf))
        self.assertEqual(
            source["canonical_pdf_sha256"],
            hashlib.sha256(canonical_pdf).hexdigest(),
        )
        self.assertEqual(stored_pdf, canonical_pdf)
        self.assertEqual(
            get_stashed_import_text(
                token,
                owner_id=self.owner.pk,
                organization_id=self.organization.pk,
            ),
            _stub_manifest()["canonical_text"],
        )
        with self.assertRaises(PermissionDenied):
            get_stashed_import_text(
                token,
                owner_id=self.owner.pk + 1,
                organization_id=self.organization.pk,
            )

    def test_malformed_standalone_image_fails_before_layout_or_storage(self):
        upload = SimpleUploadedFile(
            "broken.png",
            b"not-an-image",
            content_type="image/png",
        )
        with (
            patch("apps.exams.services.import_media.extract_pdf_layout") as extract,
            self.assertRaisesRegex(ValueError, "uyğun"),
        ):
            stash_math_images(upload)
        extract.assert_not_called()
        import_root = Path(self.media_directory.name) / "question_imports"
        self.assertEqual(list(import_root.rglob("*")) if import_root.exists() else [], [])

    def test_png_and_jpg_extensions_enter_the_canonical_pdf_pipeline(self):
        for filename, image_format in (("scan.png", "PNG"), ("scan.jpg", "JPEG")):
            with self.subTest(filename=filename):
                encoded = BytesIO()
                Image.new("RGB", (80, 40), "white").save(encoded, format=image_format)
                typed_manifest = Mock()
                typed_manifest.to_dict.return_value = _stub_manifest()
                with patch(
                    "apps.exams.services.import_media.extract_pdf_layout",
                    return_value=typed_manifest,
                ) as extract:
                    token = stash_math_images(
                        SimpleUploadedFile(filename, encoded.getvalue()),
                        owner_id=self.owner.pk,
                        organization_id=self.organization.pk,
                    )
                self.tokens.add(token)
                canonical_pdf = extract.call_args.args[0]
                self.assertTrue(canonical_pdf.startswith(b"%PDF"))
                self.assertTrue(extract.call_args.kwargs["fail_closed"])

    def test_clear_stash_deletes_canonical_keys_when_storage_has_no_listdir(self):
        token = self._stash()
        deleted: list[str] = []
        real_delete = default_storage.delete

        def record_delete(name):
            deleted.append(name)
            return real_delete(name)

        with (
            patch.object(default_storage, "listdir", side_effect=NotImplementedError),
            patch.object(default_storage, "delete", side_effect=record_delete),
        ):
            clear_stash(token)

        self.assertIn(f"question_imports/{token}/source.pdf", deleted)
        self.assertIn(f"question_imports/{token}/manifest.json", deleted)
