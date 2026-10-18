"""Transkript buraxılışı möhürlənir: QR + kod PDF-dədir, fayl həşi saxlanılır, eyni gün eyni məzmun eyni möhür."""

from __future__ import annotations

import hashlib
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.registrar import finals
from apps.registrar import public as registrar_public
from apps.verification.models import DocType, DocumentSeal
from core.rls import bypass_rls

from .world import build_world, client_for, download_transcript, latest_seal


def _pdf_text(payload: bytes) -> str:
    import fitz

    with fitz.open(stream=payload, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _count(**filters) -> int:
    with bypass_rls():
        return DocumentSeal.objects.filter(**filters).count()


class TranscriptSealIssueTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkuis")

    def test_staff_download_creates_a_seal_and_prints_code_and_url(self):
        response = download_transcript(self.w)
        self.assertEqual(response.status_code, 200)
        payload = response.content
        seal = latest_seal(subject_user=self.w["student"])
        self.assertIsNotNone(seal)
        self.assertEqual(seal.doc_type, DocType.TRANSCRIPT)
        self.assertEqual(seal.organization_id, self.w["org"].pk)
        self.assertEqual(seal.issued_by_id, self.w["owner"].pk)
        self.assertTrue(seal.code.startswith("QKUIS-"))
        self.assertEqual(seal.file_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(seal.scope_path, self.w["g1"].path)
        text = _pdf_text(payload)
        self.assertIn(seal.code, text)  # imza zolağı + hər səhifənin altlığı
        self.assertGreaterEqual(text.count(seal.code), 2)
        self.assertIn("/yoxla", text)

    def test_public_payload_is_minimal(self):
        download_transcript(self.w)
        seal = latest_seal(subject_user=self.w["student"])
        self.assertEqual(seal.payload["holder"], "Elvin Q.")
        self.assertEqual(seal.payload["org"], self.w["org"].name)
        keys = [key for key, _value in seal.payload["facts"]]
        self.assertEqual(keys[:2], ["program", "degree"])
        self.assertIn("credits", keys)
        self.assertIn("gpa", keys)
        blob = str(seal.payload)
        for leak in ("Qurbanov", self.w["student"].username, "CS101", "KE-101", "@"):
            self.assertNotIn(leak, blob)

    def test_same_day_same_content_reuses_the_seal_and_bytes(self):
        first = download_transcript(self.w).content
        second = download_transcript(self.w).content
        self.assertEqual(first, second)
        self.assertEqual(_count(subject_user=self.w["student"]), 1)

    def test_changed_grades_issue_a_new_seal(self):
        download_transcript(self.w)
        with bypass_rls():
            finals.set_exam_score(enrollment=self.w["enrollment"], score=50, by_user=self.w["teacher"])
        response = download_transcript(self.w)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_count(subject_user=self.w["student"]), 2)

    def test_other_language_is_a_different_document(self):
        from apps.registrar import transcript, transcript_seal

        w = self.w
        with bypass_rls():
            data = transcript.build_student_transcript(
                student=w["student"], organization=w["org"], program=w["record"].program
            )
            kwargs = {"organization": w["org"], "student": w["student"], "record": w["record"], "data": data}
            with translation.override("az"):
                _az_bytes, az_seal = transcript_seal.render_sealed_transcript(issued_by=w["owner"], **kwargs)
                _again, az_again = transcript_seal.render_sealed_transcript(issued_by=w["owner"], **kwargs)
            with translation.override("en"):
                _en_bytes, en_seal = transcript_seal.render_sealed_transcript(issued_by=w["owner"], **kwargs)
        self.assertEqual(az_seal.pk, az_again.pk)
        self.assertNotEqual(az_seal.pk, en_seal.pk)
        self.assertEqual((az_seal.language, en_seal.language), ("az", "en"))

    def test_revoked_seal_is_never_reused(self):
        from apps.verification.services import revoke_seal

        download_transcript(self.w)
        seal = latest_seal(subject_user=self.w["student"])
        with bypass_rls():
            revoke_seal(seal=seal, actor=self.w["office"], reason="Səhv buraxılış — yenisi ilə əvəz olunur.")
        download_transcript(self.w)
        newest = latest_seal(subject_user=self.w["student"])
        self.assertNotEqual(newest.code, seal.code)
        self.assertIsNone(newest.revoked_at)

    def test_self_service_download_is_sealed_too(self):
        with mock.patch.object(registrar_public, "STUDENT_TRANSCRIPT_SELF_SERVICE", True):
            response = client_for(self.w["org"], self.w["student"]).get(reverse("registrar:my_transcript_pdf"))
        self.assertEqual(response.status_code, 200)
        seal = latest_seal(subject_user=self.w["student"])
        self.assertEqual(seal.issued_by_id, self.w["student"].pk)
        self.assertEqual(seal.file_sha256, hashlib.sha256(response.content).hexdigest())

    def test_unauthorised_download_creates_no_seal(self):
        response = download_transcript(self.w, user=self.w["teacher"])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_count(subject_user=self.w["student"]), 0)

    def test_issuance_is_audited_with_the_code(self):
        from apps.audit.models import AuditLog

        download_transcript(self.w)
        seal = latest_seal(subject_user=self.w["student"])
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type="verification.seal", resource_id=seal.code).exists())
            row = AuditLog.objects.filter(resource_type="registrar.transcript_pdf").order_by("-created_at").first()
        self.assertIn(seal.code, row.reason)
