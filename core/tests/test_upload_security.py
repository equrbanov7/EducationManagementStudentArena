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
