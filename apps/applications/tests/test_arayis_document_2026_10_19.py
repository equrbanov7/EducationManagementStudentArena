"""«Arayış sorğusu» → «Arayışı hazırla və əlavə et» (sahib 2026-10-19).

Emalçı (Tələbə xidmətləri — «telebe» şöbəsi) + ``transcript.issue`` əhatəsi olan aktor müraciətə möhürlü
arayış PDF-ini açıq qeyd kimi əlavə edir; sahib onu görür. Emalçı olmayan (dekan) blok görmür, aktiv olmayan
tələbə üçün blok imtina mətni göstərir və POST 409 qaytarır. View-as rejimində 403.
"""

from __future__ import annotations

import json

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.applications.models import Application, ApplicationAttachment
from apps.applications.services import submit
from apps.applications.services.catalog import seed_catalog
from apps.applications.views import application_issue_arayis
from apps.registrar.models import AcademicStatus, StudentAcademicRecord
from apps.verification.models import DocType, DocumentSeal
from apps.verification.tests.world import client_for
from apps.verification.tests.world_documents import build_documents_world
from core.rls import bypass_rls


def _body(response):
    return json.loads(response.content.decode())


class ArayisApplicationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkuap")
        with bypass_rls():
            _units, kinds = seed_catalog(cls.w["org"])
            cls.application = submit.submit_application(
                organization=cls.w["org"],
                user=cls.w["student"],
                kind=kinds["arayis"],
                subject="Hərbi komissarlıq üçün arayış",
                body="Hərbi komissarlığa təqdim etmək üçün təhsil arayışı lazımdır.",
            )

    def _detail(self, user):
        client = client_for(self.w["org"], user)
        return client.get(reverse("applications:detail", args=[self.application.pk]))

    def _issue(self, user, place="Səbail rayon hərbi komissarlığına"):
        client = client_for(self.w["org"], user)
        return client.post(reverse("applications:issue_arayis", args=[self.application.pk]), {"place": place})

    def test_handler_sees_the_tool_and_attaches_a_sealed_pdf(self):
        response = self._detail(self.w["txm"])
        self.assertEqual(response.status_code, 200)
        tool = _body(response)["application"]["arayis_tool"]
        self.assertIsNotNone(tool)
        self.assertEqual(tool["blocked"], "")

        response = self._issue(self.w["txm"])
        self.assertEqual(response.status_code, 200, response.content)
        payload = _body(response)["application"]
        self.assertTrue(any(item["name"].endswith(".pdf") for item in payload["attachments"]))
        with bypass_rls():
            seal = DocumentSeal.objects.get(doc_type=DocType.ENROLLMENT_CERTIFICATE, subject_user=self.w["student"])
            attachment = ApplicationAttachment.objects.get(application=self.application)
            self.assertFalse(attachment.event.is_internal)
            self.assertIn(seal.code, attachment.event.text)
            # Status DƏYİŞMİR — açılış «Baxılır» etdi, arayış qeydi həll ETMİR (emalçı sonra «Həll et» edir).
            self.assertEqual(Application.objects.get(pk=self.application.pk).status, "in_review")

        sender_view = _body(self._detail(self.w["student"]))["application"]
        self.assertEqual(len(sender_view["attachments"]), 1)
        self.assertIsNone(sender_view["arayis_tool"])

    def test_non_handler_gets_no_tool_and_404(self):
        self.assertEqual(self._detail(self.w["dean"]).status_code, 404)
        self.assertEqual(self._issue(self.w["dean"]).status_code, 404)
        self.assertEqual(self._issue(self.w["student"]).status_code, 404)
        with bypass_rls():
            self.assertFalse(DocumentSeal.objects.filter(subject_user=self.w["student"]).exists())

    def test_inactive_student_is_refused(self):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(pk=self.w["record"].pk).update(status=AcademicStatus.EXPELLED)
        tool = _body(self._detail(self.w["txm"]))["application"]["arayis_tool"]
        self.assertTrue(tool["blocked"])
        response = self._issue(self.w["txm"])
        self.assertEqual(response.status_code, 409)
        with bypass_rls():
            self.assertFalse(ApplicationAttachment.objects.filter(application=self.application).exists())
            self.assertFalse(DocumentSeal.objects.filter(subject_user=self.w["student"]).exists())

    def test_view_as_is_blocked(self):
        request = RequestFactory().post("/", {"place": ""})
        request.user = self.w["txm"]
        request.real_user = self.w["owner"]
        request.is_view_as = True
        request.organization = self.w["org"]
        request._dont_enforce_csrf_checks = True
        response = application_issue_arayis(request, application_id=self.application.pk)
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertFalse(DocumentSeal.objects.filter(subject_user=self.w["student"]).exists())

    def test_retry_returns_the_existing_attachment_instead_of_a_second_one(self):
        """Rəy 2026-10-19 (MEDIUM): təkrar klik / iki tab — eyni məzmun ikinci qeyd + fayl YARATMIR."""
        first = self._issue(self.w["txm"])
        second = self._issue(self.w["txm"])
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        with bypass_rls():
            attachments = list(ApplicationAttachment.objects.filter(application=self.application))
            seals = DocumentSeal.objects.filter(doc_type=DocType.ENROLLMENT_CERTIFICATE, subject_user=self.w["student"])
            self.assertEqual(len(attachments), 1)
            self.assertEqual(seals.count(), 1)
            self.assertIn(seals.get().code, attachments[0].original_name)
            self.assertEqual(attachments[0].event.text.count(seals.get().code), 1)
        tool = _body(second)["application"]["arayis_tool"]
        self.assertEqual(len(tool["attached"]), 1)
        self.assertEqual(tool["attached"][0]["name"], attachments[0].original_name)
        self.assertIn(str(attachments[0].pk), tool["attached"][0]["download_url"])
        self.assertEqual(tool["attached"][0]["place"], "Səbail rayon hərbi komissarlığına")
        self.assertTrue(tool["attached_label"])
        self.assertTrue(tool["again_label"])

    def test_tool_reports_no_attachment_before_issuing(self):
        tool = _body(self._detail(self.w["txm"]))["application"]["arayis_tool"]
        self.assertEqual(tool["attached"], [])

    def test_sender_upload_named_like_an_arayis_does_not_count(self):
        from django.core.files.base import ContentFile

        from apps.applications.services.submit import attach_files

        with bypass_rls():
            attach_files(
                self.application,
                [ContentFile(b"%PDF-1.4 fake", name="Arayış_Elvin_2026-10-19_QKUAP-AAAA-BBBB-CCCC-DDDD.pdf")],
                uploaded_by=self.w["student"],
            )
        tool = _body(self._detail(self.w["txm"]))["application"]["arayis_tool"]
        self.assertEqual(tool["attached"], [])

    def test_issue_locks_the_application_row(self):
        """İki tab paralel göndərəndə ikincisi birincinin commit-ini gözləyir və onun möhürünü/faylını tapır."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self._issue(self.w["txm"]).status_code, 200)
        locks = [
            q["sql"]
            for q in ctx.captured_queries
            if "FOR UPDATE" in q["sql"] and "applications_application" in q["sql"]
        ]
        self.assertTrue(locks)

    def test_another_place_adds_a_second_arayis_and_the_list_shows_both(self):
        """Sahib 2026-10-19: «Yeni arayış hazırla (başqa yer üçün)» — başqa yer → yeni möhür + yeni fayl."""
        self.assertEqual(self._issue(self.w["txm"], place="Səbail rayon hərbi komissarlığına").status_code, 200)
        second = self._issue(self.w["txm"], place="Kapital Bank ASC-yə")
        self.assertEqual(second.status_code, 200)
        again = self._issue(self.w["txm"], place="Kapital Bank ASC-yə")  # eyni yer → mövcud fayl
        self.assertEqual(again.status_code, 200)
        with bypass_rls():
            seals = {
                seal.code: seal.payload["place"]
                for seal in DocumentSeal.objects.filter(
                    doc_type=DocType.ENROLLMENT_CERTIFICATE, subject_user=self.w["student"]
                )
            }
            self.assertEqual(ApplicationAttachment.objects.filter(application=self.application).count(), 2)
        self.assertEqual(len(seals), 2)
        rows = _body(again)["application"]["arayis_tool"]["attached"]
        self.assertEqual({row["code"]: row["place"] for row in rows}, seals)
        self.assertEqual(rows[0]["place"], "Kapital Bank ASC-yə")  # ən yenisi əvvəl
        self.assertTrue(all(row["download_url"] for row in rows))

    def test_empty_place_is_listed_with_the_default_wording(self):
        self.assertEqual(self._issue(self.w["txm"], place="").status_code, 200)
        rows = _body(self._detail(self.w["txm"]))["application"]["arayis_tool"]["attached"]
        self.assertEqual(rows[0]["place"], "tələb olunan yerə")
