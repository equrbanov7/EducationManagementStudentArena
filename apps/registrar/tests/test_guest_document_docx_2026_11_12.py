"""Sahib 2026-11-12: dekanlıq təqdimatları docx gəlir — alt qrup sənədi kimi qəbul olunur."""

from django.test import SimpleTestCase

from apps.registrar import subgroup_documents
from apps.registrar.models import GUEST_DOCUMENT_EXTENSIONS


class GuestDocumentDocxTests(SimpleTestCase):
    def test_word_files_are_accepted_as_subgroup_evidence(self):
        for ext in (".doc", ".docx"):
            self.assertIn(ext, GUEST_DOCUMENT_EXTENSIONS)
            self.assertIn(ext, subgroup_documents.ALLOWED_EXTENSIONS)

    def test_scans_and_photos_stay_accepted(self):
        for ext in (".pdf", ".jpg", ".png"):
            self.assertIn(ext, GUEST_DOCUMENT_EXTENSIONS)
