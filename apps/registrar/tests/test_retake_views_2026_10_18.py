"""25% / alt qrup — HTTP qapıları (403/404), kabinet bölmələri, Mühasibatlıq görünüşü, sorğu büdcəsi."""

from __future__ import annotations

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar import retake_decisions, retake_services
from apps.registrar.models import RetakeApplication, RetakeStatus
from core.rls import bypass_rls

from .retake_fixture import RetakeBase, pdf

PROFILE = "/accounts/profile/"


@override_settings(UNIVERSITY_MODE=True)
class RetakeHttpTest(RetakeBase):
    def setUp(self):
        self.fail_exam()

    def _apply(self, client=None, kind="retake_25", receipt=True):
        client = client or self.client_for(self.student)
        data = {"enrollment": str(self.enrollment.id), "kind": kind, "note": "salam"}
        if receipt:
            data["receipt"] = pdf("menim-qebzim.pdf")
        return client.post(reverse("retake:apply"), data)

    def _app(self):
        with bypass_rls():
            return RetakeApplication.objects.get(student=self.student)

    def test_student_applies_and_only_owner_can_act(self):
        response = self._apply()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        app = self._app()
        self.assertEqual(app.status, RetakeStatus.PAYMENT_PENDING_REVIEW)
        other = self.client_for(self.other)
        self.assertEqual(other.post(reverse("retake:withdraw", args=[app.id])).status_code, 404)
        own = self.client_for(self.student).post(reverse("retake:withdraw", args=[app.id]), {"note": ""})
        self.assertEqual(own.status_code, 200)

    def test_payment_requires_key_and_scope(self):
        self._apply()
        app = self._app()
        url = reverse("retake:payment", args=[app.id])
        # açar yoxdur → 403
        self.assertEqual(self.client_for(self.teacher).post(url, {"action": "verify"}).status_code, 403)
        self.assertEqual(self.client_for(self.dean).post(url, {"action": "verify"}).status_code, 403)
        # mühasib → 200 + bank arayışı yazılır
        response = self.client_for(self.accountant).post(url, {"action": "verify", "payment_reference": "KB-1"})
        self.assertEqual(response.status_code, 200, response.content)
        app.refresh_from_db()
        self.assertEqual((app.status, app.payment_reference), (RetakeStatus.PAYMENT_VERIFIED, "KB-1"))

    def test_dean_out_of_scope_gets_404(self):
        self._apply()
        app = self._app()
        with bypass_rls():
            retake_decisions.verify_payment(actor=self.accountant, organization=self.org, application_id=app.id)
        url = reverse("retake:decision", args=[app.id])
        self.assertEqual(self.client_for(self.dean_b).post(url, {"action": "admit"}).status_code, 404)
        self.assertEqual(self.client_for(self.accountant).post(url, {"action": "admit"}).status_code, 403)
        self.assertEqual(self.client_for(self.dean).post(url, {"action": "admit"}).status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, RetakeStatus.ADMITTED)
        result = self.client_for(self.dean).post(reverse("retake:result", args=[app.id]), {"score": "41"})
        self.assertEqual(result.status_code, 200, result.content)

    def test_subgroup_offerings_lookup(self):
        self._apply(kind="subgroup", receipt=False)
        app = self._app()
        response = self.client_for(self.dean).get(reverse("retake:subgroup_offerings", args=[app.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()["results"]], [str(self.target.id)])

    def test_subgroup_decision_requires_document(self):
        self._apply(kind="subgroup", receipt=False)
        app = self._app()
        url = reverse("retake:decision", args=[app.id])
        response = self.client_for(self.dean).post(
            url, {"action": "approve_subgroup", "reason": "Tələbə 25% vermədən alt qrupa qalmaq istəyir."}
        )
        self.assertEqual(response.status_code, 400)

    def test_receipt_media_is_protected(self):
        self._apply()
        app = self._app()
        with bypass_rls():
            path = app.current_receipt.file.name
        url = f"/media/{path}"
        self.assertNotEqual(self.client_for(self.other).get(url).status_code, 200)
        self.assertIn(self.client_for(self.student).get(url).status_code, (200, 302))

    def test_student_section_renders(self):
        response = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('data-profile-section-panel="my-retakes"', body)
        self.assertIn("Proqramlaşdırma", body)
        self.assertIn("25% müraciət et", body)

    def test_desk_shows_receipt_metadata_only_to_accountant(self):
        self._apply()
        acc = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk").content.decode()
        self.assertIn("menim-qebzim.pdf", acc)
        self.assertIn("Ödənişi təsdiqlə", acc)
        dean = self.client_for(self.dean).get(f"{PROFILE}?section=retake-desk&rt_tab=all").content.decode()
        self.assertIn('data-profile-section-panel="retake-desk"', dean)
        self.assertNotIn("menim-qebzim.pdf", dean)
        student = self.client_for(self.student).get(f"{PROFILE}?section=my-retakes").content.decode()
        self.assertNotIn("menim-qebzim.pdf", student)

    def test_duplicate_receipt_badge_for_accountant(self):
        self._apply()
        other_enrollment = self.other.enrollments.get(offering__subject=self.subject)
        self.fail_exam(enrollment=other_enrollment)
        self.client_for(self.other).post(
            reverse("retake:apply"),
            {"enrollment": str(other_enrollment.id), "kind": "retake_25", "receipt": pdf("x.pdf")},
        )
        body = self.client_for(self.accountant).get(f"{PROFILE}?section=retake-desk").content.decode()
        self.assertIn("Bu qəbz başqa müraciətdə də yüklənib", body)

    def test_trail_visible_to_coordinator_in_scope(self):
        self._apply()
        body = (
            self.client_for(self.coordinator)
            .get(f"{PROFILE}?section=retake-desk&rt_tab=all&rt_student={self.student.pk}")
            .content.decode()
        )
        self.assertIn("25% izi", body)
        far = (
            self.client_for(self.coordinator)
            .get(f"{PROFILE}?section=retake-desk&rt_tab=all&rt_student={self.far.pk}")
            .content.decode()
        )
        self.assertIn("əhatənizdə deyil", far)

    def test_accountant_sees_payment_queue_only_without_scores(self):
        """Sahibin qaydası (2026-10-18 mühasibat icmalı): mühasib bal / tarixçə / izi görmür."""
        self._apply()
        client = self.client_for(self.accountant)
        body = client.get(f"{PROFILE}?section=retake-desk").content.decode()
        self.assertIn("Ödənişi təsdiqlə", body)
        self.assertIn("menim-qebzim.pdf", body)
        self.assertNotIn("Əsas imtahan", body)
        self.assertNotIn("İmtahandan keçid balı toplanmayıb", body)
        self.assertNotIn("rt_tab=all", body)
        trail_param = client.get(
            f"{PROFILE}?section=retake-desk&rt_tab=all&rt_student={self.student.pk}"
        ).content.decode()
        self.assertNotIn("25% izi", trail_param)
        self.assertEqual(client.get(reverse("retake:trail", args=[self.student.pk])).status_code, 403)
        # qəbz faylı isə mühasibə açıqdır (ödəniş yoxlamasının özü)
        with bypass_rls():
            path = RetakeApplication.objects.get(student=self.student).current_receipt.file.name
        self.assertIn(client.get(f"/media/{path}").status_code, (200, 302))

    def test_trail_endpoint_scope(self):
        self._apply()
        ok = self.client_for(self.coordinator).get(reverse("retake:trail", args=[self.student.pk]))
        self.assertEqual(ok.status_code, 200)
        self.assertIn("25% izi", ok.content.decode())
        self.assertEqual(
            self.client_for(self.coordinator).get(reverse("retake:trail", args=[self.far.pk])).status_code, 404
        )
        self.assertEqual(
            self.client_for(self.teacher).get(reverse("retake:trail", args=[self.student.pk])).status_code, 403
        )
        self.assertEqual(
            self.client_for(self.dean).get(reverse("retake:trail", args=[self.student.pk])).status_code, 200
        )

    def test_results_and_journal_show_main_and_retake_scores(self):
        """«Nəticələrim» kartı + «Ümumi tədris məlumatı»: «Əsas imtahan: 10 → 25%: 45», yekun = son qüvvədə olan."""
        with bypass_rls():
            app = retake_services.apply(
                student=self.student,
                organization=self.org,
                enrollment_id=self.enrollment.id,
                kind="retake_25",
                receipt=pdf(),
            )
            retake_decisions.verify_payment(actor=self.accountant, organization=self.org, application_id=app.id)
            retake_decisions.admit(actor=self.dean, organization=self.org, application_id=app.id)
            retake_decisions.record_result(actor=self.dean, organization=self.org, application_id=app.id, score=45)
        client = self.client_for(self.student)
        results = client.get(f"{PROFILE}?section=my-results").content.decode()
        self.assertIn("Əsas imtahan: 10 → 25%: 45", results)
        overall = client.get(f"{PROFILE}?section=overall-academic").content.decode()
        self.assertIn("Əsas imtahan: 10 → 25%: 45", overall)
        from apps.registrar import transcript

        with bypass_rls():
            data = transcript.build_student_transcript(student=self.student, organization=self.org)
        row = data["semesters"][0]["rows"][0]
        self.assertEqual(str(row["result"]["effective_exam"]), "45.00")
        self.assertEqual(row["retake"]["text"], "Əsas imtahan: 10 → 25%: 45")

    def test_desk_hidden_without_keys(self):
        response = self.client_for(self.teacher).get(f"{PROFILE}?section=retake-desk")
        self.assertNotIn('data-profile-section-panel="retake-desk"', response.content.decode())


@override_settings(UNIVERSITY_MODE=True)
class RetakeQueryBudgetTest(RetakeBase):
    """Sorğu sayı müraciət sayından asılı deyil (desk və tələbə paneli)."""

    def _render_desk(self):
        client = self.client_for(self.accountant)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"{PROFILE}?section=retake-desk&rt_tab=all")
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def _add_app(self, student):
        enrollment = student.enrollments.get(offering__subject=self.subject)
        self.fail_exam(enrollment=enrollment)
        with bypass_rls():
            retake_services.apply(
                student=student, organization=self.org, enrollment_id=enrollment.id, kind="retake_25", receipt=pdf()
            )

    def test_desk_queries_constant(self):
        self._add_app(self.student)
        one = self._render_desk()
        for index in range(4):
            extra = self._student(f"rt_bulk{index}", self.group1)
            self._add_app(extra)
        many = self._render_desk()
        self.assertLessEqual(many, one + 2, f"{one} → {many}")

    def test_student_panel_queries_constant(self):
        self._add_app(self.student)
        client = self.client_for(self.student)
        with CaptureQueriesContext(connection) as first:
            client.get(f"{PROFILE}?section=my-retakes")
        with bypass_rls():
            app = RetakeApplication.objects.get(student=self.student)
            retake_services.withdraw(student=self.student, organization=self.org, application_id=app.id)
            retake_services.apply(
                student=self.student, organization=self.org, enrollment_id=self.enrollment.id, kind="subgroup"
            )
        with CaptureQueriesContext(connection) as second:
            client.get(f"{PROFILE}?section=my-retakes")
        self.assertLessEqual(len(second.captured_queries), len(first.captured_queries) + 2)
