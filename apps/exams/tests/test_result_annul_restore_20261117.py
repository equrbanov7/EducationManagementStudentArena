"""Sahib 2026-11-17: ləğv edilən nəticənin bərpası + uzaqlaşdırılan tələbənin kabinetdə 0 balı.

* «Tələbə “Bitir” vurub çıxıbsa, sonradan köçürmə aşkarlanarsa nəticəsi ləğv edilsin — səbəb siyahıdan, izahat,
  tarix, istəyə görə sənəd; təsdiq pəncərəsi ilə. Səhv də ola bilər — bərpa olsun» (əvvəlki bal + jurnal qayıdır).
* «İmtahandan uzaqlaşdırılan tələbənin kabinetində nəticə 0 görünsün, səbəbi ilə».
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE, TICKET_STATUS_COMPLETED
from apps.exams.domain.result_annulment import ExamResultAnnulment
from apps.exams.models import Exam, ExamAttempt, FinalExamTicket, SupervisionIncident
from apps.exams.services.final_center import (
    TicketStateError,
    annul_attempt_result,
    is_annulled,
    remove_student,
    restore_attempt_result,
)
from apps.exams.services.supervision.interventions import attach_attempt_interventions, get_attempt_intervention
from core.rls import bypass_rls

from .test_final_center_flow import _FlowBase
from .test_journal_bridge import _JournalBridgeSetup
from .test_midterm_journal_sync_2026_10_21 import _MidtermSetup

_MEDIA = tempfile.mkdtemp(prefix="ems_annul_media_")


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def tearDownModule():
    shutil.rmtree(_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=_MEDIA)
class MidtermAnnulRestoreTests(_MidtermSetup):
    def test_annul_then_restore_brings_back_score_and_journal(self):
        attempt = self._finish(*self._exam(), correct=3)
        self.assertEqual(self._score_row().score, Decimal("30"))
        doc = SimpleUploadedFile("izahat.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        with bypass_rls():
            self.assertTrue(
                annul_attempt_result(
                    attempt,
                    self.teacher,
                    reason_key="cheating",
                    note="Telefondan köçürürdü",
                    incident_date="2026-11-15",
                    document=doc,
                )
            )
            attempt.refresh_from_db()
            row = ExamResultAnnulment.objects.get(attempt=attempt)
        self.assertEqual(self._score_row().score, Decimal("0"))
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertEqual(row.reason_key, "cheating")
        self.assertEqual(row.incident_date, datetime.date(2026, 11, 15))
        self.assertTrue(row.document.name.endswith(".pdf"))
        self.assertNotIn("izahat", row.document.name)  # fayl adı tələbə/izahat məlumatı daşımır
        self.assertEqual(row.previous_supervision_status, "active")
        with bypass_rls():
            self.assertTrue(get_attempt_intervention(attempt)["is_annulled"])
            listed = attach_attempt_interventions([ExamAttempt.objects.get(pk=attempt.pk)])[0]
        self.assertTrue(listed.exam_intervention["has_document"])
        self.assertEqual(listed.exam_intervention["annulment_id"], row.pk)

        with bypass_rls():
            self.assertTrue(restore_attempt_result(attempt, self.teacher, note="Səhv tələbə seçilmişdi"))
            attempt.refresh_from_db()
            row.refresh_from_db()
            intervention = get_attempt_intervention(attempt)
            restored_log = AuditLog.objects.filter(
                resource_id=str(attempt.pk), reason__startswith="exam_result_restored"
            ).exists()
            flipped = SupervisionIncident.objects.filter(
                attempt=attempt, teacher_action="result_annul_restored"
            ).count()
            marker = SupervisionIncident.objects.filter(attempt=attempt, teacher_action="result_annulled").count()
        self.assertEqual(attempt.supervision_status, "active")
        self.assertEqual(self._score_row().score, Decimal("30"))
        self.assertIsNotNone(row.restored_at)
        self.assertEqual(row.restored_by_id, self.teacher.pk)
        self.assertEqual(row.restore_note, "Səhv tələbə seçilmişdi")
        self.assertFalse(intervention["is_annulled"])
        self.assertTrue(restored_log)
        self.assertEqual((flipped, marker), (1, 0))
        with bypass_rls():
            self.assertFalse(is_annulled(attempt))
            self.assertFalse(restore_attempt_result(attempt, self.teacher, note="təkrar"))  # artıq bərpa olunub

        # Yenidən ləğv — yeni qeyd (tarixçə tam qalır).
        with bypass_rls():
            self.assertTrue(annul_attempt_result(attempt, self.teacher, reason_key="other", note="Yenidən baxıldı"))
            self.assertEqual(ExamResultAnnulment.objects.filter(attempt=attempt).count(), 2)
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_annulling_the_higher_of_two_midterm_attempts_writes_the_other_one(self):
        """Rəsmi = yüksək bal. Yüksək cəhd ləğv edilsə xanaya digər cəhdin balı yazılmalıdır, bərpada geri qayıtmalıdır."""
        exam, options = self._exam()
        now = timezone.now()
        high = self._finish(exam, options, correct=3, started_at=now - datetime.timedelta(hours=3), attempt_number=1)
        low = self._finish(exam, options, correct=1, started_at=now - datetime.timedelta(hours=1), attempt_number=2)
        self.assertEqual(self._score_row().score, Decimal("30"))
        with bypass_rls():
            annul_attempt_result(high, self.teacher, reason_key="cheating", note="Köçürmə sonradan aşkarlandı")
        self.assertEqual(self._score_row().score, Decimal("10"))
        with bypass_rls():
            restore_attempt_result(high, self.teacher, note="Səhv idi")
        self.assertEqual(self._score_row().score, Decimal("30"))
        self.assertTrue(low.pk)

    def test_document_content_must_match_its_extension(self):
        attempt = self._finish(*self._exam(), correct=3)
        fake_pdf = SimpleUploadedFile("akt.pdf", b"MZ\x90\x00 not a pdf", content_type="application/pdf")
        with bypass_rls():
            with self.assertRaises(TicketStateError):
                annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="x", document=fake_pdf)
            self.assertFalse(is_annulled(attempt))

    def test_restore_requires_note_and_validates_inputs(self):
        attempt = self._finish(*self._exam(), correct=3)
        with bypass_rls():
            with self.assertRaises(TicketStateError):
                annul_attempt_result(
                    attempt,
                    self.teacher,
                    reason_key="cheating",
                    note="x",
                    incident_date=timezone.localdate() + datetime.timedelta(days=2),
                )
            with self.assertRaises(TicketStateError):
                annul_attempt_result(
                    attempt,
                    self.teacher,
                    reason_key="cheating",
                    note="x",
                    document=SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"),
                )
            with self.assertRaises(TicketStateError):
                annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="x", incident_date="13/45")
            self.assertFalse(is_annulled(attempt))
            annul_attempt_result(attempt, self.teacher, reason_key="forbidden_device", note="Telefon")
            with self.assertRaises(TicketStateError):
                restore_attempt_result(attempt, self.teacher, note="  ")
            self.assertTrue(is_annulled(attempt))
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_restoring_annul_of_removed_student_keeps_removal_zero(self):
        attempt = self._finish(*self._exam(), correct=3, supervision_status="removed")
        self.assertEqual(self._score_row().score, Decimal("0"))
        with bypass_rls():
            annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="Köçürmə də olub")
            restore_attempt_result(attempt, self.teacher, note="Ləğv səhv idi")
            attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "removed")  # imtahan zamanı uzaqlaşdırma qalır
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_cabinet_results_show_zero_for_annulled_attempt(self):
        from apps.accounts.views._dashboard_helpers import results as results_mod

        attempt = self._finish(*self._exam(), correct=3)
        with bypass_rls():
            annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="Telefondan köçürürdü")
        request = RequestFactory().get("/accounts/profile/", {"section": "my-results"})
        request.user = self.student
        with (
            bypass_rls(),
            mock.patch.object(results_mod, "_tenant_scoped_exams", return_value=Exam.objects.all()),
            mock.patch.object(results_mod, "_tenant_scoped_courses", return_value=Exam.objects.none()),
        ):
            items, _counts = results_mod._collect_my_results(request, filter_type="exams")[:2]
        item = next(row for row in items if row.get("attempt_id") == attempt.pk)
        self.assertEqual(item["score"], "0")
        self.assertEqual(item["score_percent"], "0%")
        self.assertEqual(item["score_pct_value"], 0.0)
        self.assertTrue(item["result_annulled"])
        self.assertTrue(item["removed_from_exam"])
        self.assertIn("Telefondan köçürürdü", item["removal_reason"])
        self.assertIsNone(item["pending_score_attempt"])


class FinalAnnulRestoreTests(_JournalBridgeSetup):
    def test_final_exam_score_goes_to_zero_and_back(self):
        attempt = self._correct_test_attempt()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))
        with bypass_rls():
            annul_attempt_result(attempt, self.teacher, reason_key="impersonation", note="Başqası yazıb")
        self.assertEqual(self._final_grade().exam_score, Decimal("0"))
        with bypass_rls():
            restore_attempt_result(attempt, self.teacher, note="Şəxsiyyət təsdiqləndi")
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))


class RemovalOfFinishedAttemptTests(_FlowBase):
    """Tələbə «Bitir» vurub, bilet hələ «aktiv» ikən nəzarətçi onu uzaqlaşdırır → nəticə də 0 olmalıdır."""

    def _finished_on_active_ticket(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        attempt.mark_finished(status="submitted")
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(status=TICKET_STATUS_ACTIVE, attempt=attempt)
        self.ticket.refresh_from_db()
        return attempt

    def test_removed_action_annuls_finished_attempt(self):
        attempt = self._finished_on_active_ticket()
        self.assertTrue(remove_student(self.ticket, self.invigilator, action="removed", reason="Köçürürdü"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "removed")
        row = ExamResultAnnulment.objects.get(attempt=attempt, restored_at__isnull=True)
        self.assertEqual(row.reason_key, "removed")
        self.assertEqual(row.note, "Köçürürdü")
        self.assertTrue(get_attempt_intervention(attempt)["is_annulled"])

    def test_technical_stop_does_not_annul(self):
        attempt = self._finished_on_active_ticket()
        remove_student(self.ticket, self.invigilator, action="technical", reason="Kompüter xarab")
        attempt.refresh_from_db()
        self.assertNotEqual(attempt.supervision_status, "removed")
        self.assertFalse(ExamResultAnnulment.objects.filter(attempt=attempt).exists())


@override_settings(MEDIA_ROOT=_MEDIA)
class AnnulEndpointTests(_FlowBase):
    def _completed_attempt(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        attempt.mark_finished(status="submitted")
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(status=TICKET_STATUS_COMPLETED, attempt=attempt)
        return attempt

    def _annul_url(self, attempt):
        return reverse("exams:exam_center_attempt_annul", kwargs={"attempt_id": attempt.pk})

    def _restore_url(self, attempt):
        return reverse("exams:exam_center_attempt_restore", kwargs={"attempt_id": attempt.pk})

    def test_center_annuls_with_file_downloads_it_and_restores(self):
        attempt = self._completed_attempt()
        client = self._client_for(self.center)
        detail = reverse("exams:exam_center_session_detail", kwargs={"session_id": self.session.pk})
        response = client.post(
            self._annul_url(attempt),
            {
                "reason": "cheating",
                "note": "Bitir vurdu, sonra köçürmə aşkarlandı",
                "incident_date": timezone.localdate().isoformat(),
                "document": SimpleUploadedFile("akt.png", _png_bytes(), content_type="image/png"),
                "next": detail,
            },
        )
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.assertTrue(is_annulled(attempt))
        row = ExamResultAnnulment.objects.get(attempt=attempt)

        page = client.get(detail)
        self.assertContains(page, "Ləğvi bərpa et")
        self.assertContains(page, "xanRestoreDialog")

        download = client.get(reverse("exams:exam_center_annulment_document", kwargs={"annulment_id": row.pk}))
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(
            self._client_for(self.invigilator)
            .get(reverse("exams:exam_center_annulment_document", kwargs={"annulment_id": row.pk}))
            .status_code,
            403,
        )

        response = client.post(self._restore_url(attempt), {"note": "Səhv imiş", "next": "https://evil.example/x"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response["Location"])  # kənar `next` qəbul olunmur
        self.assertFalse(is_annulled(attempt))
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "active")

    def test_only_exam_center_can_annul_or_restore(self):
        attempt = self._completed_attempt()
        for user in (self.invigilator, self.teacher, self.student):
            response = self._client_for(user).post(self._annul_url(attempt), {"reason": "cheating", "note": "x"})
            self.assertIn(response.status_code, (302, 403, 404), user.username)
        self.assertFalse(is_annulled(attempt))
        annul_attempt_result(attempt, self.center, reason_key="cheating", note="x")
        for user in (self.invigilator, self.teacher):
            self._client_for(user).post(self._restore_url(attempt), {"note": "x"})
        self.assertTrue(is_annulled(attempt))
        self.assertEqual(self._client_for(self.center).get(self._annul_url(attempt)).status_code, 405)

    def test_missing_note_shows_error_and_changes_nothing(self):
        attempt = self._completed_attempt()
        response = self._client_for(self.center).post(self._annul_url(attempt), {"reason": "cheating", "note": ""})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(is_annulled(attempt))

    def test_results_list_shows_annul_button_only_to_center(self):
        self._completed_attempt()
        url = reverse("exams:teacher_exam_results", kwargs={"slug": self.exam.slug})
        page = self._client_for(self.center).get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-annul-open")
        self.assertContains(page, "xanAnnulDialog")


class IncidentCopyMigrationTests(_MidtermSetup):
    """0079: PR #366-dan qalan ``result_annulled`` hadisələri yeni cədvələ köçürülür."""

    def test_copy_function_creates_active_annulment(self):
        import importlib

        migration = importlib.import_module("apps.exams.migrations.0079_attempt_extra_time_result_annulment")
        attempt = self._finish(*self._exam(), correct=3)
        with bypass_rls():
            SupervisionIncident.objects.create(
                organization=self.org,
                exam=attempt.exam,
                attempt=attempt,
                student=self.student,
                event_type="auto_submitted",
                severity="critical",
                metadata={"reason_key": "cheating", "note": "köhnə", "previous_status": "active", "teacher_id": None},
                teacher_action="result_annulled",
            )
            migration._copy_incident_annulments(django_apps, SimpleNamespace(connection=SimpleNamespace(vendor="x")))
            row = ExamResultAnnulment.objects.get(attempt=attempt)
        self.assertEqual((row.reason_key, row.note, row.previous_supervision_status), ("cheating", "köhnə", "active"))
        self.assertIsNone(row.restored_at)
