"""Təhlükəsizlik auditi 2026-10-05 — yükləmə yolu ilə stored XSS.

* ``.xht`` / ``.rdf`` / ``.rss`` … uzantıları block-list-də yox idi; müştəri
  ``Content-Type: text/plain`` göndərəndə ``text/`` prefiksi ilə keçirdi, fayl
  isə serve zamanı ``mimetypes`` ilə ``application/xhtml+xml`` alırdı — brauzer
  onu öz origin-imizdə skript kimi icra edir.
* ``protected_media`` hər faylı ``inline`` verirdi; indi yalnız raster şəkil /
  PDF / video / audio inline qalır, qalan hər şey ``attachment``-dir.
* Laboratoriya ``allowed_extensions`` müəllimin sərbəst mətni idi — indi sabit
  server superset-i ilə kəsişdirilir.
"""

from __future__ import annotations

import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

import pytest

from core.upload_security import validate_uploaded_file

XHTML = b'<html xmlns="http://www.w3.org/1999/xhtml"><script>alert(document.cookie)</script></html>'


class MarkupExtensionUploadTest(SimpleTestCase):
    @pytest.mark.filterwarnings("ignore")
    def test_markup_capable_extensions_are_rejected(self):
        for name in ("x.xht", "x.xpdl", "x.rdf", "x.wsdl", "x.rss", "x.atom", "x.xul", "x.dtd"):
            upload = SimpleUploadedFile(name, XHTML, content_type="text/plain")
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_uploaded_file(upload)

    def test_unknown_xml_family_extension_is_rejected_by_guessed_mime(self):
        # Hər hansı ``+xml`` / html / javascript kimi tanınan uzantı — siyahıda olmasa belə.
        import mimetypes

        mimetypes.add_type("application/x-secaudit+xml", ".secaudit")
        upload = SimpleUploadedFile("x.secaudit", XHTML, content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_uploaded_file(upload)

    def test_plain_documents_still_pass(self):
        validate_uploaded_file(SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain"))
        validate_uploaded_file(SimpleUploadedFile("data.csv", b"a,b\n1,2", content_type="text/csv"))


class ProtectedMediaDispositionTest(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="secaudit_media_su", email="secaudit_media_su@example.com", password="StrongPass123!"
        )
        self.media_tmp = tempfile.mkdtemp()
        folder = os.path.join(self.media_tmp, "labs", "submissions")
        os.makedirs(folder, exist_ok=True)
        for name, body in (("evil.xht", XHTML), ("pic.png", b"\x89PNG\r\n\x1a\n"), ("doc.pdf", b"%PDF-1.4")):
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(body)

    def _get(self, path, **extra_settings):
        from core.media_views import protected_media

        request = RequestFactory().get(f"/media/{path}")
        request.user = self.superuser
        request.session = {}
        with override_settings(MEDIA_ROOT=self.media_tmp, ADMIN_2FA_REQUIRED=False, **extra_settings):
            return protected_media(request, path)

    def test_markup_file_is_forced_to_download(self):
        response = self._get("labs/submissions/evil.xht")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_markup_file_is_forced_to_download_via_accel(self):
        response = self._get("labs/submissions/evil.xht", MEDIA_ACCEL_REDIRECT_URL="/internal_media")
        self.assertIn("X-Accel-Redirect", response)
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    def test_raster_image_and_pdf_stay_inline(self):
        for path in ("labs/submissions/pic.png", "labs/submissions/doc.pdf"):
            with self.subTest(path=path):
                response = self._get(path)
                self.assertNotIn("attachment", response.get("Content-Disposition", ""))


class LabExtensionSupersetTest(SimpleTestCase):
    def test_teacher_cannot_widen_lab_extensions_beyond_server_superset(self):
        from apps.labs.views.shared._helpers import _normalize_extensions

        extensions = _normalize_extensions("pdf,xht,rdf,exe,py")
        self.assertEqual(extensions, {".pdf", ".py"})

    def test_only_unknown_extensions_fall_back_to_default(self):
        from apps.labs.views.shared._helpers import DEFAULT_LAB_ALLOWED_EXTENSIONS, _normalize_extensions

        self.assertEqual(_normalize_extensions("xht,rss"), set(DEFAULT_LAB_ALLOWED_EXTENSIONS))
