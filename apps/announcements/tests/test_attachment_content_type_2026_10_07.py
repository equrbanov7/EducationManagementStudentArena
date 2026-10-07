"""Təhlükəsizlik auditi 2026-10-07 — elan sənədinin ``Content-Type``-ı klient bəyanından gəlmir.

Endirmə ``attachment.content_type``-ı (yükləmədə brauzerin BƏYAN etdiyi dəyər)
olduğu kimi qaytarırdı: ``text/html`` bəyanı ilə yüklənmiş əsl PDF (imza yoxlamasını
keçir) bizim origin-dən ``text/html`` kimi verilirdi. İndi tip adın uzantısından
(``core.download_types`` ağ siyahısı) çıxarılır; ``attachment`` + ``nosniff`` qalır.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.announcements.models import AnnouncementAttachment
from core.rls import bypass_rls

from .world import build_world, client_for, make_announcement

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class AttachmentContentTypeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annct")
        cls.item = make_announcement(cls.w, title="Sənədli elan", units=[cls.w["f1"].pk])

    def _upload(self, name, content, content_type):
        data = {
            "title": "Sənədli elan",
            "category": "exam",
            "priority": "0",
            "audience_families": ["students"],
            "audience_units": [str(self.w["f1"].pk)],
            "apply_mode": "none",
            "files": SimpleUploadedFile(name, content, content_type=content_type),
        }
        client = client_for(self.w["org"], self.w["owner"])
        response = client.post(reverse("announcements:manage_edit", args=[self.item.pk]), data)
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            return AnnouncementAttachment.objects.get(announcement=self.item)

    def _download(self, attachment):
        url = reverse("announcements:attachment_download", args=[self.item.pk, attachment.pk])
        return client_for(self.w["org"], self.w["s1"]).get(url)

    def test_html_claim_on_pdf_is_not_echoed(self):
        attachment = self._upload("cedvel.pdf", PDF, "text/html")
        self.assertEqual(attachment.content_type, "application/pdf")
        response = self._download(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_legacy_stored_claim_is_ignored_on_download(self):
        attachment = self._upload("cedvel.pdf", PDF, "application/pdf")
        with bypass_rls():  # düzəlişdən ƏVVƏL yazılmış sətir: klient bəyanı saxlanıb
            AnnouncementAttachment.objects.filter(pk=attachment.pk).update(content_type="image/svg+xml")
        response = self._download(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
