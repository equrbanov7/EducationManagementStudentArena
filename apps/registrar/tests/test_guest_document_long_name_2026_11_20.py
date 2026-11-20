"""Prod 2026-11-20: uzun + nöqtəli adlı təqdimat «Alt qrupdan tələbə əlavə et»-i HTML 400-ə salırdı.

«30.09.2026 Birləşmiş Alt qrup təqdimat 2026-2027 Payız son.pdf» → ``guest_roster_documents/<org>/<ad>`` yolu
``FileField`` 100 simvol limitini keçirdi; Django ``get_available_name`` ilk nöqtədən sonrakı hər şeyi «uzantı»
sayıb kökü («30») kəsə bilmədi → ``SuspiciousFileOperation`` → HTML 400 → modalda yalnız ümumi «Əməliyyat
alınmadı». İndi ad təsadüfiləşir (yol ≤ 100) və saxlama xətası JSON ``error`` ilə qayıdır.
"""

import io
import zipfile
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.registrar.models import Enrollment, GuestRosterDocument, guest_document_path
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

PROD_NAME = "30.09.2026 Birləşmiş Alt qrup təqdimat 2026-2027 Payız son"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pdf(name=PROD_NAME + ".pdf"):
    return SimpleUploadedFile(
        name, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", content_type="application/pdf"
    )


def _docx(name=PROD_NAME + ".docx"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", '<?xml version="1.0"?><w:document/>')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=DOCX_MIME)


class GuestDocumentPathTest(_GuestRosterBase):
    def test_long_dotted_name_fits_the_field(self):
        instance = SimpleNamespace(organization_id=self.org.pk)
        for ext in (".pdf", ".docx", ".jpeg", ".PDF"):
            path = guest_document_path(instance, PROD_NAME + ext)
            self.assertLessEqual(len(path), 100, path)
            self.assertTrue(path.startswith(f"guest_roster_documents/{self.org.pk}/"))
            self.assertTrue(path.endswith(ext.lower()))
            self.assertNotIn("Payız", path)

    def test_unknown_extension_is_dropped(self):
        path = guest_document_path(SimpleNamespace(organization_id=self.org.pk), "a.php")
        self.assertFalse(path.endswith(".php"))


class GuestAddLongDocumentNameTest(_GuestRosterBase):
    def _add(self, document):
        self._drop_own_history(self.guest)
        return self._client(self.coordinator).post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"document": document, "group": str(self.group2.id), "student": str(self.guest.id), "reason": "təqdimat"},
        )

    def test_prod_pdf_name_is_accepted(self):
        resp = self._add(_pdf())
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json()["ok"])
        with bypass_rls():
            stored = GuestRosterDocument.objects.get(enrollment_id=resp.json()["enrollment_id"]).document.name
        self.assertLessEqual(len(stored), 100)
        self.assertTrue(stored.endswith(".pdf"))

    def test_prod_docx_name_with_windows_mime_is_accepted(self):
        resp = self._add(_docx())
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json()["ok"])

    def test_storage_failure_returns_json_reason_and_rolls_back(self):
        with mock.patch(
            "django.core.files.storage.FileSystemStorage.save",
            side_effect=SuspiciousFileOperation("Storage can not find an available filename"),
        ):
            resp = self._add(_pdf())
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["error"])
        with bypass_rls():
            self.assertFalse(
                Enrollment.objects.filter(
                    offering=self.offering, student=self.guest, status=Enrollment.Status.ENROLLED
                ).exists()
            )
