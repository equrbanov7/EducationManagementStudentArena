"""
Integration tests – Upload Security.

Verifies that ``core.upload_security.validate_uploaded_file`` blocks
dangerous file uploads: executable files, double-extension attacks,
PE magic-byte smuggling, and oversized files.

These tests act as a regression guard for upload-security fixes and map
directly to the acceptance-criteria test names specified in the task.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.upload_security import validate_uploaded_file


class UploadSecurityIntegrationTest(TestCase):
    """
    Integration-level named upload security tests as required by the
    acceptance criteria.
    """

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_file(self, filename, content=b"safe content", content_type="application/octet-stream"):
        return SimpleUploadedFile(filename, content, content_type=content_type)

    # ------------------------------------------------------------------
    # Required named tests
    # ------------------------------------------------------------------

    def test_exe_upload_blocked(self):
        """
        Files with an ``.exe`` extension must be rejected regardless of
        the declared MIME type.
        """
        f = self._make_file("malware.exe", b"MZ\x90\x00", "application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_double_extension_attack_blocked(self):
        """
        A filename like ``shell.php.jpg`` must be rejected because the inner
        ``.php`` suffix is a blocked extension (double-extension attack).
        """
        f = SimpleUploadedFile("shell.php.jpg", b"\xff\xd8\xff\xe0", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_pe_magic_bytes_blocked(self):
        """
        A file whose first two bytes are the PE/DOS magic number ``MZ``
        (``0x4D 0x5A``) must be blocked even when it carries an innocent
        extension (e.g. ``.pdf``).

        This prevents EXE/DLL files from being smuggled via extension rename.
        """
        pe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        f = self._make_file("document.pdf", pe_content, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_file_size_limit_enforced(self):
        """
        A file that exceeds the configured ``max_size_mb`` limit must be
        rejected with a ``ValidationError``.
        """
        oversized = b"X" * (1 * 1024 * 1024 + 1)  # 1 MB + 1 byte
        f = self._make_file("big.pdf", oversized, "application/pdf")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f, max_size_mb=1)

    # ------------------------------------------------------------------
    # Additional regression guards
    # ------------------------------------------------------------------

    def test_valid_pdf_accepted(self):
        """A well-formed PDF must not be rejected."""
        f = self._make_file("report.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", "application/pdf")
        # Must not raise
        validate_uploaded_file(f)

    def test_valid_jpeg_accepted(self):
        """A well-formed JPEG must not be rejected."""
        f = self._make_file("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg")
        validate_uploaded_file(f)

    def test_php_extension_blocked(self):
        """Files with a ``.php`` extension must always be rejected."""
        f = self._make_file("shell.php", b"<?php echo 1;", "application/x-httpd-php")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_bat_extension_blocked(self):
        """Windows batch files (``.bat``) must be rejected."""
        f = self._make_file("run.bat", b"@echo off\ndir", "text/plain")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)

    def test_file_exactly_at_size_limit_accepted(self):
        """A file exactly at the size boundary must be accepted."""
        exact_content = b"X" * (1 * 1024 * 1024)
        f = self._make_file("exact.pdf", exact_content, "application/pdf")
        validate_uploaded_file(f, max_size_mb=1)

    def test_php_signature_in_jpg_blocked(self):
        """A ``.jpg`` containing ``<?php`` in its content must be rejected."""
        f = self._make_file("photo.jpg", b"<?php system($_GET['cmd']);", "image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(f)
