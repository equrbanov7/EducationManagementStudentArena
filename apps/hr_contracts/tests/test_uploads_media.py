"""Müqavilə faylı — məzmun imzası, təsadüfi ad, qorunan media (kim görür)."""

from __future__ import annotations

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.hr_contracts.media import check_file_access
from apps.hr_contracts.models import EmploymentContract
from apps.hr_contracts.services import contracts as service
from core.rls import bypass_rls

from .world import PDF_BYTES, actor, build_world, client_for, contract_data, make_contract

_MEDIA = tempfile.mkdtemp(prefix="hrc-media-")


@override_settings(MEDIA_ROOT=_MEDIA)
class UploadTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcfile")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def _pdf(self, name="Müqavilə 2026.pdf", content=PDF_BYTES):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_pdf_is_stored_under_random_protected_name(self):
        contract = make_contract(self.w, number="F-1", files={"file": self._pdf()})
        self.assertTrue(contract.file.name.startswith(f"hr_contracts/{self.w['org'].pk}/"))
        self.assertNotIn("Müqavilə", contract.file.name)
        self.assertEqual(contract.file_name, "Müqavilə 2026.pdf")

    def test_fake_or_dangerous_file_rejected(self):
        client = client_for(self.w["org"], self.w["hr"])
        for upload in (
            self._pdf("fake.pdf", b"<script>alert(1)</script>"),
            SimpleUploadedFile("run.exe", b"MZ\x90\x00", content_type="application/octet-stream"),
            SimpleUploadedFile("page.html", b"<html></html>", content_type="text/html"),
        ):
            data = contract_data(self.w["t1"], number=f"F-{upload.name}")
            response = client.post(reverse("hr_contracts:save"), {**data, "file": upload})
            self.assertEqual(response.status_code, 400, upload.name)
            self.assertEqual(response.json()["field"], "file")
        with bypass_rls():
            self.assertFalse(EmploymentContract.objects.filter(number__startswith="F-").exists())

    def test_replacing_file_records_event(self):
        contract = make_contract(self.w, number="F-2")
        data = contract_data(self.w["t1"], number="F-2", id=contract.pk)
        response = client_for(self.w["org"], self.w["hr"]).post(
            reverse("hr_contracts:save"), {**data, "file": self._pdf()}
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.assertTrue(contract.events.filter(kind="file_replaced").exists())

    def test_media_access_policy(self):
        contract = make_contract(self.w, number="F-3", files={"file": self._pdf()})
        staff_contract = make_contract(self.w, "m1", number="F-4", files={"file": self._pdf()})
        path = contract.file.name
        with bypass_rls():
            self.assertTrue(check_file_access(self.w["t1"], path))  # işçinin özü
            self.assertTrue(check_file_access(self.w["hr"], path))
            self.assertTrue(check_file_access(self.w["unit_hr"], path))  # F1 əhatəsi
            self.assertTrue(check_file_access(self.w["trustee"], path))  # yalnız oxu açarı
            self.assertFalse(check_file_access(self.w["t2"], path))  # həmkar
            self.assertFalse(check_file_access(self.w["dean"], path))  # açar yoxdur
            self.assertFalse(check_file_access(self.w["s1"], path))
            self.assertFalse(check_file_access(self.w["unit_hr"], staff_contract.file.name))  # F2 əhatədən kənar
            self.assertFalse(check_file_access(self.w["hr"], "hr_contracts/yoxdur.pdf"))

    def test_draft_file_hidden_from_employee_until_sent(self):
        draft = make_contract(self.w, "t2", number="F-5", status="draft", files={"file": self._pdf()})
        with bypass_rls():
            self.assertFalse(check_file_access(self.w["t2"], draft.file.name))
            service.mark_sent(actor(self.w, "hr"), draft.pk)
            self.assertTrue(check_file_access(self.w["t2"], draft.file.name))

    def test_protected_media_view(self):
        contract = make_contract(self.w, number="F-6", files={"file": self._pdf()})
        url = f"/media/{contract.file.name}"
        self.assertEqual(client_for(self.w["org"], self.w["t2"]).get(url).status_code, 404)
        self.assertEqual(client_for(self.w["org"], self.w["t1"]).get(url).status_code, 200)
