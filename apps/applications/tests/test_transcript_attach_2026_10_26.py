"""«Transkript sorğusu» → «Transkripti hazırla və əlavə et» (sahib 2026-10-26).

Tələbə Xidmətləri («telebe» şöbəsinin emalçısı, ``student_services`` — ``transcript.issue`` açarı şablondan)
müraciətə staff yükləməsi ilə EYNİ möhürlü transkripti (QR + yoxlama kodu) açıq qeyd kimi əlavə edir; sahib
onu müraciətdən endirir; status dəyişmir; ``registrar.transcript_pdf`` audit sətri yazılır. Emalçı olmayan /
``transcript.issue``-suz / əhatədən kənar aktor blok görmür və POST 403/404 alır; view-as 403.
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.applications.models import Application, ApplicationAttachment
from apps.applications.services import submit
from apps.applications.services.catalog import seed_catalog
from apps.applications.views import application_issue_transcript
from apps.registrar.models import AcademicStatus, StudentAcademicRecord
from apps.verification.models import DocType, DocumentSeal
from apps.verification.tests.world import client_for
from apps.verification.tests.world_documents import build_documents_world, pdf_text
from core.rls import bypass_rls

_SERVICE = "apps.applications.services.documents"


def _body(response):
    return json.loads(response.content.decode())


def _seals(world):
    with bypass_rls():
        return list(DocumentSeal.objects.filter(doc_type=DocType.TRANSCRIPT, subject_user=world["student"]))


class TranscriptApplicationAttachTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkutr")
        with bypass_rls():
            _units, cls.kinds = seed_catalog(cls.w["org"])
            cls.application = submit.submit_application(
                organization=cls.w["org"],
                user=cls.w["student"],
                kind=cls.kinds["transkript"],
                subject="Transkript sorğusu",
                body="Rəsmi transkript lazımdır.",
            )

    def _detail(self, user):
        return client_for(self.w["org"], user).get(reverse("applications:detail", args=[self.application.pk]))

    def _issue(self, user, application=None):
        target = application or self.application
        return client_for(self.w["org"], user).post(reverse("applications:issue_transcript", args=[target.pk]))

    def test_handler_sees_the_tool_without_a_place_field(self):
        response = self._detail(self.w["txm"])
        self.assertEqual(response.status_code, 200)
        payload = _body(response)["application"]
        tool = payload["document_tool"]
        self.assertIsNotNone(tool)
        self.assertEqual(tool["kind"], "transkript")
        self.assertFalse(tool["has_place"])
        self.assertEqual(tool["blocked"], "")
        self.assertEqual(tool["attached"], [])
        self.assertEqual(tool["button"], "Transkripti hazırla və əlavə et")
        self.assertEqual(tool["url"], reverse("applications:issue_transcript", args=[self.application.pk]))
        self.assertIsNone(payload["arayis_tool"])  # köhnə açar yalnız arayış növündədir

    def test_handler_attaches_a_sealed_transcript_status_unchanged_and_audited(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            status_before = Application.objects.get(pk=self.application.pk).status
        response = self._issue(self.w["txm"])
        self.assertEqual(response.status_code, 200, response.content)
        payload = _body(response)["application"]
        seals = _seals(self.w)
        self.assertEqual(len(seals), 1)
        seal = seals[0]
        with bypass_rls():
            attachment = ApplicationAttachment.objects.get(application=self.application)
            self.assertFalse(attachment.event.is_internal)
            self.assertIn(seal.code, attachment.event.text)
            self.assertTrue(attachment.original_name.startswith("Transkript_"))
            self.assertTrue(attachment.original_name.endswith(f"_{seal.code}.pdf"))
            self.assertEqual(Application.objects.get(pk=self.application.pk).status, status_before)
            audit = AuditLog.objects.filter(resource_type="registrar.transcript_pdf").order_by("-created_at").first()
        self.assertIsNotNone(audit)
        self.assertIn(seal.code, audit.reason)
        self.assertEqual(audit.resource_id, str(self.w["record"].pk))
        rows = payload["document_tool"]["attached"]
        self.assertEqual([row["code"] for row in rows], [seal.code])
        self.assertTrue(rows[0]["note"])

        # Sahib (tələbə) faylı müraciətdən endirir — möhürlü PDF, kod mətndədir.
        sender_view = _body(self._detail(self.w["student"]))["application"]
        self.assertIsNone(sender_view["document_tool"])
        self.assertEqual(len(sender_view["attachments"]), 1)
        download = client_for(self.w["org"], self.w["student"]).get(
            reverse(
                "applications:attachment_download",
                kwargs={"application_id": self.application.pk, "attachment_id": attachment.pk},
            )
        )
        self.assertEqual(download.status_code, 200)
        content = b"".join(download.streaming_content) if download.streaming else download.content
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertIn(seal.code, pdf_text(content))

    def test_retry_returns_the_existing_attachment(self):
        self.assertEqual(self._issue(self.w["txm"]).status_code, 200)
        second = self._issue(self.w["txm"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(_seals(self.w)), 1)
        with bypass_rls():
            self.assertEqual(ApplicationAttachment.objects.filter(application=self.application).count(), 1)
        self.assertEqual(len(_body(second)["application"]["document_tool"]["attached"]), 1)

    def test_former_student_still_gets_a_transcript(self):
        """Transkript məzuna / xaric olunana da verilir (staff yükləməsi kimi) — arayışın aktivlik şərti yoxdur."""
        with bypass_rls():
            StudentAcademicRecord.objects.filter(pk=self.w["record"].pk).update(status=AcademicStatus.EXPELLED)
        self.assertEqual(_body(self._detail(self.w["txm"]))["application"]["document_tool"]["blocked"], "")
        self.assertEqual(self._issue(self.w["txm"]).status_code, 200)

    def test_nothing_to_certify_is_refused_with_409(self):
        with mock.patch(
            "apps.registrar.transcript_issue.transcript_service.build_student_transcript",
            return_value={"has_record": False},
        ):
            response = self._issue(self.w["txm"])
        self.assertEqual(response.status_code, 409)
        self.assertTrue(_body(response)["errors"]["__all__"][0])
        self.assertEqual(_seals(self.w), [])
        with bypass_rls():
            self.assertFalse(ApplicationAttachment.objects.filter(application=self.application).exists())

    def test_non_handler_gets_no_tool_and_404(self):
        self.assertEqual(self._detail(self.w["dean"]).status_code, 404)
        self.assertEqual(self._issue(self.w["dean"]).status_code, 404)
        self.assertEqual(self._issue(self.w["student"]).status_code, 404)
        self.assertEqual(_seals(self.w), [])

    def test_handler_without_transcript_issue_gets_no_tool_and_404(self):
        with mock.patch(f"{_SERVICE}.can_issue_documents", return_value=False):
            self.assertIsNone(_body(self._detail(self.w["txm"]))["application"]["document_tool"])
            self.assertEqual(self._issue(self.w["txm"]).status_code, 404)
        self.assertEqual(_seals(self.w), [])

    def test_out_of_scope_student_gets_no_tool_and_404(self):
        with mock.patch(f"{_SERVICE}.issuable_record_for_student", return_value=None):
            self.assertIsNone(_body(self._detail(self.w["txm"]))["application"]["document_tool"])
            self.assertEqual(self._issue(self.w["txm"]).status_code, 404)
        self.assertEqual(_seals(self.w), [])

    def test_transcript_url_on_an_arayis_application_is_404(self):
        with bypass_rls():
            arayis = submit.submit_application(
                organization=self.w["org"],
                user=self.w["student"],
                kind=self.kinds["arayis"],
                subject="Arayış sorğusu",
                body="Təhsil arayışı lazımdır.",
            )
        self.assertEqual(self._issue(self.w["txm"], application=arayis).status_code, 404)
        self.assertEqual(_seals(self.w), [])

    def test_view_as_is_blocked(self):
        request = RequestFactory().post("/")
        request.user = self.w["txm"]
        request.real_user = self.w["owner"]
        request.is_view_as = True
        request.organization = self.w["org"]
        request._dont_enforce_csrf_checks = True
        response = application_issue_transcript(request, application_id=self.application.pk)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(_seals(self.w), [])
