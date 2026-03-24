"""
Unit tests for core.upload_security.

Covers:
- Blocked extension detection (.php, .exe, .html)
- Double-extension attack detection (.php.jpg)
- MIME spoofing scenarios (blocked MIME with innocent extension)
- EXE/PHP file-signature detection inside files with allowed extensions
- Oversized file rejection
- Valid file accepted baseline
- Filename randomization via randomize_uploaded_filename
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.upload_security import (
    randomize_uploaded_filename,
    validate_uploaded_file,
)


class UploadSecurityBlockedExtensionTest(TestCase):
    """validate_uploaded_file rejects files with blocked extensions."""

    def _make_file(self, filename, content=b"safe content", content_type="application/octet-stream"):
        return SimpleUploadedFile(filename, content, content_type=content_type)

    def test_rejects_php_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(self._make_file("shell.php", b"<?php echo 1;", "application/x-httpd-php"))

    def test_rejects_exe_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(self._make_file("virus.exe", b"MZ\x90\x00", "application/x-msdownload"))

    def test_rejects_html_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(self._make_file("page.html", b"<html></html>", "text/html"))

    def test_rejects_bat_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(self._make_file("run.bat", b"@echo off", "text/plain"))

    def test_rejects_sh_extension(self):
        with self.assertRaises(ValidationError):
            validate_uploaded_file(self._make_file("script.sh", b"#!/bin/bash", "text/plain"))


class UploadSecurityDoubleExtensionTest(TestCase):
    """validate_uploaded_file detects double-extension attacks."""

    def test_rejects_php_jpg_double_extension(self):
        """shell.php.jpg — inner .php suffix is blocked."""
        f = SimpleUploadedFile("shell.php.jpg", b"\xff\xd8\xff\xe0", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_php_zip_double_extension(self):
        """shell.php.zip — inner .php suffix is blocked."""
        f = SimpleUploadedFile("shell.php.zip", b"PK\x03\x04", content_type="application/zip")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_exe_pdf_double_extension(self):
        """virus.exe.pdf — inner .exe suffix is blocked."""
        f = SimpleUploadedFile("virus.exe.pdf", b"%PDF-1.4", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)


class UploadSecurityMimeSpoofingTest(TestCase):
    """validate_uploaded_file rejects MIME spoofing attempts."""

    def test_rejects_blocked_mime_with_jpg_extension(self):
        """File with .jpg extension but application/x-httpd-php MIME type is blocked."""
        f = SimpleUploadedFile("image.jpg", b"\xff\xd8\xff\xe0", content_type="application/x-httpd-php")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_blocked_mime_with_pdf_extension(self):
        """File with .pdf extension but application/x-msdownload MIME type is blocked."""
        f = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_blocked_mime_with_zip_extension(self):
        """File with .zip extension but application/x-executable MIME type is blocked."""
        f = SimpleUploadedFile("archive.zip", b"PK\x03\x04", content_type="application/x-executable")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)


class UploadSecuritySignatureTest(TestCase):
    """validate_uploaded_file detects dangerous file signatures regardless of extension."""

    def test_rejects_exe_signature_in_pdf(self):
        """A .pdf file with an MZ (EXE) signature is blocked."""
        f = SimpleUploadedFile(
            "document.pdf",
            b"MZ\x90\x00\x03\x00\x00\x00",
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_php_signature_in_jpg(self):
        """A .jpg file with a <?php signature is blocked."""
        f = SimpleUploadedFile(
            "photo.jpg",
            b"<?php echo 'pwn';",
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_rejects_php_signature_in_docx(self):
        """A .docx file with a <?php signature is blocked."""
        f = SimpleUploadedFile(
            "report.docx",
            b"<?php system($_GET['cmd']);",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)


class UploadSecurityOversizedFileTest(TestCase):
    """validate_uploaded_file rejects files that exceed the configured size limit."""

    def test_rejects_file_exceeding_max_size_mb(self):
        """A file just over the 1 MB limit is rejected."""
        big_content = b"X" * (1 * 1024 * 1024 + 1)
        f = SimpleUploadedFile("bigfile.pdf", big_content, content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f, max_size_mb=1)

    def test_accepts_file_at_max_size_mb_boundary(self):
        """A file exactly at the 1 MB boundary is accepted."""
        exact_content = b"X" * (1 * 1024 * 1024)
        f = SimpleUploadedFile("exactfile.pdf", exact_content, content_type="application/pdf")
        # Should NOT raise
        validate_uploaded_file(f, max_size_mb=1)

    def test_accepts_file_below_max_size_mb(self):
        """A small file well within the size limit is accepted."""
        f = SimpleUploadedFile("small.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", content_type="application/pdf")
        # Should NOT raise (default 25 MB limit)
        validate_uploaded_file(f)


class UploadSecurityValidFileTest(TestCase):
    """validate_uploaded_file accepts legitimate file uploads."""

    def test_accepts_valid_pdf(self):
        f = SimpleUploadedFile("report.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", content_type="application/pdf")
        validate_uploaded_file(f)  # must not raise

    def test_accepts_valid_jpeg(self):
        f = SimpleUploadedFile("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", content_type="image/jpeg")
        validate_uploaded_file(f)  # must not raise

    def test_accepts_valid_zip(self):
        f = SimpleUploadedFile("archive.zip", b"PK\x03\x04", content_type="application/zip")
        validate_uploaded_file(f)  # must not raise

    def test_accepts_valid_png(self):
        f = SimpleUploadedFile("image.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        validate_uploaded_file(f)  # must not raise


class UploadSecurityFilenameRandomizationTest(TestCase):
    """randomize_uploaded_filename replaces the original filename with a UUID."""

    def test_randomize_strips_original_name(self):
        f = SimpleUploadedFile("secret_name.pdf", b"%PDF-1.4", content_type="application/pdf")
        randomize_uploaded_filename(f)
        self.assertNotIn("secret_name", f.name)

    def test_randomize_preserves_extension(self):
        f = SimpleUploadedFile("my_report.pdf", b"%PDF-1.4", content_type="application/pdf")
        randomize_uploaded_filename(f)
        self.assertTrue(f.name.endswith(".pdf"))

    def test_randomize_handles_none_gracefully(self):
        result = randomize_uploaded_filename(None)
        self.assertIsNone(result)

    def test_randomize_produces_different_names_each_call(self):
        f1 = SimpleUploadedFile("file.pdf", b"%PDF-1.4", content_type="application/pdf")
        f2 = SimpleUploadedFile("file.pdf", b"%PDF-1.4", content_type="application/pdf")
        randomize_uploaded_filename(f1)
        randomize_uploaded_filename(f2)
        self.assertNotEqual(f1.name, f2.name)


# ---------------------------------------------------------------------------
# Task 8 — Required named tests
# ---------------------------------------------------------------------------


class UploadSecurityRequiredNamedTests(TestCase):
    """
    Canonical test methods required by the Task 8 acceptance criteria.

    Each test maps to the exact name listed in the problem statement so that
    CI can verify their presence.  Where equivalent coverage already exists in
    the classes above these tests use the same helpers to avoid duplication.
    """

    def _make_file(self, filename, content=b"safe content", content_type="application/octet-stream"):
        return SimpleUploadedFile(filename, content, content_type=content_type)

    def test_exe_upload_blocked(self):
        """Files with an ``.exe`` extension must be rejected."""
        f = self._make_file("malware.exe", b"MZ\x90\x00", "application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_double_extension_attack_blocked(self):
        """A file like ``shell.php.jpg`` must be rejected due to the hidden ``.php``."""
        f = SimpleUploadedFile("shell.php.jpg", b"\xff\xd8\xff\xe0", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_file_size_limit_enforced(self):
        """A file exceeding the configured size limit must be rejected."""
        oversized = b"X" * (1 * 1024 * 1024 + 1)
        f = self._make_file("big.pdf", oversized, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f, max_size_mb=1)

    def test_pe_magic_bytes_blocked(self):
        """
        A file whose first two bytes are the PE magic number (``MZ`` / ``4D 5A``)
        must be blocked even when it carries an innocent extension such as
        ``.pdf``.  This catches EXE/DLL files smuggled with renamed extensions.
        """
        # DOS/PE header: MZ followed by the standard DOS stub header bytes.
        pe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        f = self._make_file("document.pdf", pe_content, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_octet_stream_mime_blocked(self):
        """application/octet-stream must be rejected as it is a generic bypass vector."""
        f = SimpleUploadedFile("data.bin", b"some binary content", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_magic_byte_exe_detection(self):
        """A file with the EXE (MZ) magic bytes must be rejected regardless of extension."""
        f = SimpleUploadedFile("seemingly_safe.pdf", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_magic_byte_php_detection(self):
        """A file starting with <?php must be rejected regardless of its declared extension."""
        f = SimpleUploadedFile("photo.jpg", b"<?php system($_GET['cmd']);", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)


# ─────────────────────────────────────────────────────────────────────────────
# ZIP bomb / archive guard tests
# ─────────────────────────────────────────────────────────────────────────────


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP with the given filename→content mapping."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _make_zip_file(entries: dict[str, bytes], name: str = "upload.zip"):
    """Return a SimpleUploadedFile ZIP archive."""
    data = _make_zip(entries)
    return SimpleUploadedFile(name, data, content_type="application/zip")


class ZipArchiveValidationTest(TestCase):
    """Tests for validate_zip_archive – bomb and abuse protection."""

    def setUp(self):
        from core.upload_security import validate_zip_archive

        self.validate = validate_zip_archive

    # ── happy-path ────────────────────────────────────────────────────────

    def test_valid_zip_accepted(self):
        """A normal ZIP with a few small files must pass without error."""
        f = _make_zip_file({"a.txt": b"hello", "b.txt": b"world"})
        self.assertIsNone(self.validate(f))  # no exception

    def test_empty_zip_accepted(self):
        """An empty ZIP archive is valid."""
        f = _make_zip_file({})
        self.assertIsNone(self.validate(f))

    # ── invalid ZIP ───────────────────────────────────────────────────────

    def test_bad_zip_raises(self):
        """Non-ZIP bytes must raise ValidationError."""
        f = SimpleUploadedFile("bad.zip", b"not a zip", content_type="application/zip")
        with self.assertRaises(ValidationError):
            self.validate(f)

    # ── file count limit ─────────────────────────────────────────────────

    def test_too_many_files_raises(self):
        """ZIPs exceeding the file-count limit must be rejected."""
        entries = {f"file{i}.txt": b"x" for i in range(5)}
        f = _make_zip_file(entries)
        with self.assertRaises(ValidationError):
            self.validate(f, max_file_count=3)

    def test_exactly_at_limit_accepted(self):
        """ZIPs at the exact file-count limit must be accepted."""
        entries = {f"file{i}.txt": b"x" for i in range(3)}
        f = _make_zip_file(entries)
        self.assertIsNone(self.validate(f, max_file_count=3))

    # ── extracted size limit ─────────────────────────────────────────────

    def test_oversized_compressed_total_raises(self):
        """ZIPs whose total compressed size exceeds the limit must be rejected."""
        # Deflate compresses b"a"*100 to ~6 bytes; 3 such entries = ~18 bytes.
        # Use a limit of 10 bytes to reliably trigger the size guard.
        entries = {f"file{i}.txt": b"a" * 100 for i in range(3)}
        f = _make_zip_file(entries)
        with self.assertRaises(ValidationError):
            self.validate(f, max_extracted_size_bytes=10)

    # ── compression-ratio (zip bomb) guard ───────────────────────────────

    def test_zip_bomb_ratio_raises(self):
        """An entry with extreme compression ratio must be flagged as a zip bomb."""
        import io
        import zipfile

        # 1 MB of zero bytes compresses to ~1 KB via DEFLATE.
        # ratio ≈ 1015 >> ZIP_BOMB_RATIO_THRESHOLD (99).
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", b"\x00" * (1024 * 1024))
        bomb_data = buf.getvalue()

        f = SimpleUploadedFile("bomb.zip", bomb_data, content_type="application/zip")
        with self.assertRaises(ValidationError):
            self.validate(f)

    # ── nesting depth ─────────────────────────────────────────────────────

    def test_nested_zip_exceeding_depth_raises(self):
        """Nested ZIPs beyond the allowed depth must be rejected.

        max_nesting_depth=0 means the top-level ZIP may not contain any nested
        ZIPs at all; any nested ZIP triggers a ValidationError.
        """
        # outer.zip → inner.zip → file.txt  (2 levels)
        inner_data = _make_zip({"file.txt": b"deep"})
        outer_data = _make_zip({"inner.zip": inner_data})

        f = SimpleUploadedFile("outer.zip", outer_data, content_type="application/zip")
        with self.assertRaises(ValidationError):
            # Depth 0 means nested ZIPs are not permitted at all.
            self.validate(f, max_nesting_depth=0)

    def test_nested_zip_within_depth_accepted(self):
        """Nested ZIPs within the allowed depth must pass."""
        inner_data = _make_zip({"file.txt": b"ok"})
        outer_data = _make_zip({"inner.zip": inner_data})
        f = SimpleUploadedFile("outer.zip", outer_data, content_type="application/zip")
        # max_nesting_depth=1 allows outer→inner.zip to be inspected.
        self.assertIsNone(self.validate(f, max_nesting_depth=1))
