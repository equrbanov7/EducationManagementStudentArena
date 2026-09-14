"""2026-09-14 wave 2 (audit F-06, §27 «upload MIME sniffing») — ``core.upload_security`` sərtləşdirməsi.

Yoxlanılan qatlar:

* block-list genişlənməsi (``.xhtml .mjs .xml .xsl .svgz .shtml .mht .mhtml .htm``);
* şəkil uzantılı hər yükləmə üçün magic-bytes + markup (SVG/HTML) rəddi;
* şəkil SAHƏLƏRİ (``allowed_extensions`` ⊆ şəkil uzantıları) üçün Pillow
  identifikasiyası və uzantı ↔ format uyğunluğu (``.png`` içində GIF → rədd);
* allow-list-li sənəd yükləmələrində bəyan edilən tip ↔ imza (``%PDF`` / ``PK`` / OLE);
* allow-list-siz köhnə çağırış davranışı dəyişmir (``core/tests/test_upload_security.py``
  ilə birlikdə keçməlidir).
"""

from __future__ import annotations

import base64
import io
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from core.upload_security import (
    BLOCKED_UPLOAD_EXTENSIONS,
    IMAGE_ALLOWED_EXTENSIONS,
    FileUploadValidator,
    validate_uploaded_file,
)

# Pillow ilə yaradılmış 2×2 həqiqi şəkillər.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP8zwACTGCSAQANHQEDgslx/wAAAABJRU5ErkJggg=="
)
GIF = base64.b64decode("R0lGODdhAgACAIEAAP8AAAAAAAAAAAAAACwAAAAAAgACAAAIBgABCAQQEAA7")
WEBP = base64.b64decode("UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAIAAUAmJaACdLoB+AADsAD+8ut//NgVzXPv9//S4P0uD9Lg/9KQAAA=")
JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<!DOCTYPE html><html><body><script>alert(1)</script></body></html>"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", "a")
    return buffer.getvalue()


def _upload(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


class BlockListExtensionTest(SimpleTestCase):
    def test_new_markup_and_module_extensions_are_blocked(self):
        for ext in (".xhtml", ".mjs", ".xml", ".xsl", ".xslt", ".svgz", ".shtml", ".mht", ".mhtml", ".htm"):
            with self.subTest(ext=ext):
                self.assertIn(ext, BLOCKED_UPLOAD_EXTENSIONS)
                with self.assertRaises(ValidationError):
                    validate_uploaded_file(_upload(f"page{ext}", b"<x/>", "text/plain"))

    def test_double_extension_with_new_blocked_stem(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("photo.xhtml.png", PNG, "image/png"))


class ImageContentSniffingTest(SimpleTestCase):
    """Şəkil uzantılı HƏR yükləmə (allow-list-siz də) magic-bytes-dən keçir."""

    def test_svg_disguised_as_png_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("logo.png", SVG, "image/png"))

    def test_html_disguised_as_jpeg_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("photo.jpg", HTML, "image/jpeg"))

    def test_html_with_bom_and_whitespace_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("photo.gif", b"\xef\xbb\xbf \n<html>", "image/gif"))

    def test_random_bytes_named_png_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("photo.png", b"fake-image-bytes", "image/png"))

    def test_gif_bytes_named_png_pass_magic_only_without_allow_list(self):
        # Allow-list-siz köhnə çağırış: yalnız uzantının öz imzası yoxlanır → GIF `.png` adı ilə rədd.
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("photo.png", GIF, "image/png"))

    def test_valid_signatures_are_accepted_without_allow_list(self):
        for name, content, mime in (
            ("a.png", PNG, "image/png"),
            ("a.gif", GIF, "image/gif"),
            ("a.webp", WEBP, "image/webp"),
            ("a.jpg", JPEG_HEAD, "image/jpeg"),
            ("a.jfif", JPEG_HEAD, "image/jpeg"),
        ):
            with self.subTest(name=name):
                validate_uploaded_file(_upload(name, content, mime))

    def test_riff_without_webp_tag_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("a.webp", b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 16, "image/webp"))

    def test_image_mime_with_markup_body_is_rejected_even_for_other_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("note.txt", SVG, "image/svg+xml"))


class ImageFieldPillowVerificationTest(SimpleTestCase):
    """Şəkil sahəsi (allow-list ⊆ şəkil uzantıları) → Pillow identifikasiyası."""

    def _validate(self, name, content, mime="image/png", **kwargs):
        return validate_uploaded_file(
            _upload(name, content, mime),
            allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
            allowed_mime_types=set(),
            allowed_mime_prefixes=("image/",),
            **kwargs,
        )

    def test_real_png_gif_webp_accepted(self):
        self._validate("a.png", PNG)
        self._validate("a.gif", GIF, "image/gif")
        self._validate("a.webp", WEBP, "image/webp")

    def test_truncated_header_only_is_rejected_for_image_field(self):
        # Allow-list-siz çağırış bunu qəbul edir (köhnə test); şəkil sahəsi isə etmir.
        validate_uploaded_file(_upload("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))
        with self.assertRaises(ValidationError):
            self._validate("a.png", b"\x89PNG\r\n\x1a\n")

    def test_png_header_followed_by_html_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._validate("a.png", b"\x89PNG\r\n\x1a\n" + HTML)

    def test_format_must_match_extension(self):
        # PNG məzmunu `.gif` adı ilə — həm magic, həm Pillow format↔uzantı qatı rədd edir.
        with self.assertRaises(ValidationError):
            self._validate("a.gif", PNG, "image/gif")
        # Pillow qatı təkbaşına: magic qatını keçən (`verify_image` ilə açıq) səhv format.
        from unittest import mock

        from core import upload_security

        with mock.patch.object(upload_security, "_image_signature_ok", return_value=True):
            with self.assertRaises(ValidationError):
                self._validate("a.png", GIF, "image/png")

    def test_pillow_can_be_forced_without_allow_list(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("a.png", b"\x89PNG\r\n\x1a\n", "image/png"), verify_image=True)

    def test_pillow_can_be_disabled_explicitly(self):
        self._validate("a.png", b"\x89PNG\r\n\x1a\n", verify_image=False)

    def test_file_position_is_restored(self):
        upload = _upload("a.png", PNG, "image/png")
        upload.seek(3)
        validate_uploaded_file(upload, allowed_extensions=IMAGE_ALLOWED_EXTENSIONS, allowed_mime_prefixes=("image/",))
        self.assertEqual(upload.tell(), 3)
        upload.seek(0)
        validate_uploaded_file(upload, allowed_extensions=IMAGE_ALLOWED_EXTENSIONS, allowed_mime_prefixes=("image/",))
        self.assertEqual(upload.tell(), 0)
        self.assertEqual(upload.read(), PNG)

    def test_avatar_style_allow_list_subset_triggers_pillow(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                _upload("a.png", b"\x89PNG\r\n\x1a\n", "image/png"),
                allowed_extensions={".jpg", ".jpeg", ".png", ".gif", ".webp"},
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )


class DocumentSignatureTest(SimpleTestCase):
    """Allow-list-li sənəd sahələrində bəyan edilən tip ↔ məzmun imzası."""

    def test_html_named_pdf_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("cv.pdf", HTML, "application/pdf"), allowed_extensions={".pdf"})

    def test_text_named_pdf_is_rejected_with_allow_list(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("cv.pdf", b"X" * 64, "application/pdf"), allowed_extensions={".pdf"})

    def test_text_named_pdf_still_passes_without_allow_list(self):
        # Köhnə davranış (core/tests/test_upload_security.py::test_accepts_file_at_max_size_mb_boundary).
        validate_uploaded_file(_upload("cv.pdf", b"X" * 64, "application/pdf"))

    def test_pdf_with_leading_junk_within_window_is_accepted(self):
        validate_uploaded_file(_upload("cv.pdf", b"\n" * 10 + PDF, "application/pdf"), allowed_extensions={".pdf"})

    def test_zip_based_office_requires_pk(self):
        validate_uploaded_file(
            _upload("a.docx", _zip_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            allowed_extensions={".docx"},
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                _upload("a.docx", HTML, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                allowed_extensions={".docx"},
            )

    def test_legacy_office_accepts_ole_or_pk_but_not_text(self):
        validate_uploaded_file(_upload("a.doc", OLE, "application/msword"), allowed_extensions={".doc"})
        validate_uploaded_file(_upload("a.xls", _zip_bytes(), "application/vnd.ms-excel"), allowed_extensions={".xls"})
        with self.assertRaises(ValidationError):
            validate_uploaded_file(
                _upload("a.xls", b"a,b,c\n1,2,3\n", "application/vnd.ms-excel"), allowed_extensions={".xls"}
            )

    def test_csv_declared_as_ms_excel_is_not_signature_checked(self):
        # Windows brauzerləri `.csv` üçün `application/vnd.ms-excel` göndərir — imza cədvəli
        # uzantı ilə açılır, bu MIME qəsdən cədvəldə yoxdur.
        validate_uploaded_file(
            _upload("scores.csv", b"a,b,c\n1,2,3\n", "application/vnd.ms-excel"),
            allowed_extensions={".csv", ".xlsx"},
        )

    def test_mime_fallback_when_extension_unknown(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(_upload("a.bin", HTML, "application/pdf"), allowed_extensions={".bin"})
        validate_uploaded_file(_upload("a.bin", PDF, "application/pdf"), allowed_extensions={".bin"})

    def test_field_validator_passes_signature_and_verify_image(self):
        def _uncommitted(name, content, mime):
            # `FileUploadValidator` yalnız hələ saxlanmamış (`_committed=False`) faylı yoxlayır.
            upload = _upload(name, content, mime)
            upload._committed = False
            return upload

        validator = FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=10)
        with self.assertRaises(ValidationError):
            validator(_uncommitted("cv.pdf", HTML, "application/pdf"))
        validator(_uncommitted("cv.pdf", PDF, "application/pdf"))
        image_validator = FileUploadValidator(allowed_extensions={".png"}, verify_image=True)
        with self.assertRaises(ValidationError):
            image_validator(_uncommitted("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))
        image_validator(_uncommitted("a.png", PNG, "image/png"))
        # Migrasiya sabitliyi: `verify_image=None` deconstruct-a düşmür.
        self.assertNotIn("verify_image", FileUploadValidator(allowed_extensions={".pdf"}).deconstruct()[2])
        self.assertIn("verify_image", image_validator.deconstruct()[2])
