"""``purge_trial_exam`` — sınaq midterm-in hamıdan, nəticələrdən və jurnaldan silinməsi (sahib 2026-10-21).

«233IT ing üçün Cloud-dan sınaq midterm etdik, real deyildi — onu silmək lazımdır. Hamıdan, nəticədə, examdə
silinsin gərək». Bax ``apps/exams/services/trial_exam_purge.py`` + ``management/commands/purge_trial_exam.py``.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, override_settings

from apps.appeals.models import Appeal, AppealDecisionRecord, AppealItem
from apps.audit.models import AuditLog
from apps.exams.models import (
    Exam,
    ExamAnswer,
    ExamAttempt,
    ExamGradeEvent,
    ExamStudentPin,
    FinalExamTicket,
    ProctoringLog,
    SupervisionIncident,
)
from apps.exams.services import trial_exam_purge
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.exams.views.shared.tenant import tenant_scoped_exams
from apps.notifications.models import InAppNotification
from apps.registrar.models import ComponentScore, ExamChanceGrant
from core.rls import bypass_rls

TITLE = "Cloud Computing"
REASON = "Sınaq midterm-in silinməsi — sahibin 2026-10-21 tapşırığı"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class _PurgeSetup(_MidtermSetup):
    def setUp(self):
        self._media = tempfile.mkdtemp(prefix="purge-trial-")
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        media = override_settings(MEDIA_ROOT=self._media)
        media.enable()
        self.addCleanup(media.disable)
        super().setUp()
        self.exam, options = self._exam(title=TITLE)
        self.first = self._finish(self.exam, options, correct=1)
        self.second = self._finish(self.exam, options, correct=2, attempt_number=2)
        with bypass_rls():
            answer = ExamAnswer.objects.filter(attempt=self.second).order_by("pk").first()
            appeal = Appeal.objects.create(
                attempt=self.second,
                exam=self.exam,
                student=self.student,
                organization=self.org,
                status="rejected",
            )
            AppealItem.objects.create(
                appeal=appeal,
                question=answer.question,
                answer=answer,
                appeal_type="other",
                comment="x",
                status="rejected",
            )
            self.record = AppealDecisionRecord.objects.create(
                organization=self.org,
                appeal=appeal,
                decided_by_teacher=self.teacher,
                rejected_count=1,
                document=SimpleUploadedFile("qerar.pdf", PDF, content_type="application/pdf"),
                document_name="qerar.pdf",
            )
            FinalExamTicket.objects.create(organization=self.org, exam=self.exam, student=self.student)
            ExamStudentPin.objects.create(exam=self.exam, student=self.student, pin_hash="h")
            ProctoringLog.objects.create(exam_attempt=self.second, event_type="tab_switch")
            SupervisionIncident.objects.create(
                organization=self.org,
                exam=self.exam,
                attempt=self.second,
                student=self.student,
                event_type="tab_hidden",
            )
            InAppNotification.objects.create(
                recipient=self.student,
                organization=self.org,
                title="Apellyasiya",
                link=f"/exams/{self.exam.slug}/result/{self.second.pk}/",
                metadata={"appeal_id": appeal.pk, "exam_id": self.exam.pk},
            )
            InAppNotification.objects.create(
                recipient=self.student,
                organization=self.org,
                title="PIN",
                message=f"«{TITLE}» imtahanı üzrə sizə yenidən cəhd hüququ verildi.",
                # Zal xatırlatması / təyinat — ``org_scoped_link`` keçidi kodlayır (``?next=%2Fexams%2Fmidterm%2F``).
                link=f"/organizations/switch/{self.org.slug}/?next=%2Fexams%2Fmidterm%2F",
                notification_type="exam",
            )
            self.document_path = os.path.join(self._media, self.record.document.name)
        self._other_exam()

    def _other_exam(self):
        """Başqa imtahan — toxunulmamalıdır."""
        self.other, other_options = self._exam(title="Real Quiz", category="quiz")
        self.other_attempt = self._finish(self.other, other_options, correct=1)
        with bypass_rls():
            ExamStudentPin.objects.create(exam=self.other, student=self.student, pin_hash="h")
            self.other_note = InAppNotification.objects.create(
                recipient=self.student, organization=self.org, title="Other", metadata={"exam_id": self.other.pk}
            )

    def _call(self, *extra, title=TITLE, slug=None):
        out = StringIO()
        call_command(
            "purge_trial_exam",
            "--org",
            self.org.slug,
            "--slug",
            slug or self.exam.slug,
            "--expect-title",
            title,
            *extra,
            stdout=out,
        )
        return out.getvalue().strip()

    def _apply(self, *extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self._call("--apply", "--reason", REASON, "--i-know-this-is-production", *extra)

    @staticmethod
    def _counts(line):
        assert line.startswith("trial_exam_purge: "), line
        return dict(part.split("=", 1) for part in line.split(": ", 1)[1].split())


class PurgeTrialExamTests(_PurgeSetup):
    def test_dry_run_counts_and_writes_nothing(self):
        self.assertIsNotNone(self._score_row())
        counts = self._counts(self._call())
        self.assertEqual(counts["mode"], "DRY-RUN")
        self.assertEqual(counts["blocked"], "0")
        expected = {
            "exam_found": "1",
            "attempts": "2",
            "answers": "6",
            "appeals": "1",
            "appeal_items": "1",
            "appeal_decision_records": "1",
            "appeal_documents": "1",
            "tickets": "1",
            "pins": "1",
            "proctoring_logs": "1",
            "supervision_incidents": "1",
            "journal_component_scores_from_exam": "1",
            "journal_prior_values": "0",
            "final_grades_from_exam": "0",
            "grade_events": "0",
        }
        for key, value in expected.items():
            self.assertEqual(counts[key], value, key)
        # Bildirişlər: müəllimə 2 «Yeni imtahan cəhdi» (task metadata), 2 jurnal «Midterm balı yazıldı: N»,
        # apellyasiya (metadata), «yenidən cəhd» (ad + ümumi keçid). Başqa imtahanın bildirişləri sayılmır.
        self.assertEqual(counts["notifications"], "6")
        with bypass_rls():
            self.assertEqual(ExamAttempt.objects.filter(exam=self.exam).count(), 2)
            self.assertFalse(Exam.objects.get(pk=self.exam.pk).is_deleted)
            self.assertFalse(AuditLog.objects.filter(resource_type=trial_exam_purge.AUDIT_RESOURCE_TYPE).exists())
        self.assertIsNotNone(self._score_row())
        self.assertTrue(os.path.exists(self.document_path))

    def test_apply_removes_everything_and_hides_exam(self):
        counts = self._counts(self._apply())
        self.assertEqual(counts["mode"], "APPLY")
        with bypass_rls():
            exam = Exam.objects.get(pk=self.exam.pk)
            self.assertTrue(exam.is_deleted)
            self.assertFalse(exam.is_active)
            self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())
            self.assertFalse(ExamAnswer.objects.filter(attempt__exam=exam).exists())
            self.assertFalse(Appeal.objects.filter(exam=exam).exists())
            self.assertFalse(AppealDecisionRecord.objects.filter(pk=self.record.pk).exists())
            self.assertFalse(FinalExamTicket.objects.filter(exam=exam).exists())
            self.assertFalse(ExamStudentPin.objects.filter(exam=exam).exists())
            self.assertFalse(SupervisionIncident.objects.filter(exam=exam).exists())
            self.assertFalse(ProctoringLog.objects.filter(exam_attempt__exam=exam).exists())
            self.assertFalse(
                InAppNotification.objects.filter(recipient=self.student, metadata__exam_id=exam.pk).exists()
            )
            self.assertFalse(InAppNotification.objects.filter(message__contains=TITLE).exists())
            self.assertFalse(InAppNotification.objects.filter(metadata__event="journal_update").exists())
            # Siyahılar: tələbə / müəllim / imtahan mərkəzi.
            request = RequestFactory().get("/")
            request.user, request.organization = self.student, self.org
            self.assertFalse(tenant_scoped_exams(request).filter(pk=exam.pk).exists())
            self.assertFalse(Exam.objects.filter(author=self.teacher, is_deleted=False, pk=exam.pk).exists())
            self.assertFalse(Appeal.objects.filter(student=self.student).exists())
        self.assertIsNone(self._score_row())  # jurnal «Midterm» xanası boşaldı
        self.assertFalse(os.path.exists(self.document_path))  # sənəd commit-dən sonra silindi

    def test_apply_writes_one_audit_row_and_keeps_history(self):
        with bypass_rls():
            before = AuditLog.objects.count()
        self._apply()
        with bypass_rls():
            rows = AuditLog.objects.filter(resource_type=trial_exam_purge.AUDIT_RESOURCE_TYPE)
            self.assertEqual(rows.count(), 1)
            row = rows.get()
            # Mövcud audit izi (midterm-auto yazıları və s.) SAXLANILIR, yalnız +1 sətir.
            self.assertEqual(AuditLog.objects.count(), before + 1)
        self.assertEqual(row.reason, REASON)
        self.assertEqual(row.changes["counts"]["attempts"], 2)
        self.assertEqual(row.resource_id, str(self.exam.pk))

    def test_other_exam_data_untouched(self):
        self._apply()
        with bypass_rls():
            self.assertTrue(ExamAttempt.objects.filter(pk=self.other_attempt.pk).exists())
            self.assertTrue(ExamStudentPin.objects.filter(exam=self.other).exists())
            self.assertTrue(InAppNotification.objects.filter(pk=self.other_note.pk).exists())
            self.assertFalse(Exam.objects.get(pk=self.other.pk).is_deleted)

    def test_idempotent_second_run_finds_nothing(self):
        self._apply()
        counts = self._counts(self._apply())
        self.assertEqual(counts["mode"], "NOOP")
        self.assertEqual(counts["exam_deleted_before"], "1")
        for key in ("attempts", "appeals", "tickets", "pins", "notifications", "journal_component_scores_from_exam"):
            self.assertEqual(counts[key], "0", key)
        with bypass_rls():
            self.assertEqual(AuditLog.objects.filter(resource_type=trial_exam_purge.AUDIT_RESOURCE_TYPE).count(), 1)

    def test_wrong_expected_title_refuses(self):
        with self.assertRaisesMessage(CommandError, "trial_exam_title_mismatch"):
            self._call("--apply", "--reason", REASON, "--i-know-this-is-production", title="Cloud")
        with bypass_rls():
            self.assertEqual(ExamAttempt.objects.filter(exam=self.exam).count(), 2)

    def test_unknown_slug_and_short_reason_refuse(self):
        with self.assertRaisesMessage(CommandError, "trial_exam_not_found"):
            self._call(slug="cloud-computing-XXXXXX")
        with self.assertRaisesMessage(CommandError, "trial_exam_reason_too_short"):
            self._call("--apply", "--reason", "qısa", "--i-know-this-is-production")

    def test_grade_events_are_purged_with_narrow_trigger_exception(self):
        """2026-10-21 (sahib): qəbul olunmuş appelyasiyanın reyestr sətirləri də silinir (organizations 0071)."""
        with bypass_rls():
            answer = ExamAnswer.objects.filter(attempt=self.second).order_by("pk").first()
            event = ExamGradeEvent.objects.create(
                attempt=self.second, question=answer.question, old_score=0, new_score=1, max_points=1
            )
        out = self._call()
        self.assertIn("grade_events=1", out)
        self.assertIn("blocked=0", out)
        self._apply()
        with bypass_rls():
            self.assertFalse(ExamGradeEvent.objects.filter(pk=event.pk).exists())
            self.assertEqual(ExamAttempt.objects.filter(exam=self.exam).count(), 0)

    def test_grade_event_trigger_still_blocks_outside_purge(self):
        """İstisna dar qalır: imtahan silinməyibsə və ya bayraq yoxdursa reyestr silinmir."""
        from django.db import DatabaseError, connection, transaction

        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        with bypass_rls():
            answer = ExamAnswer.objects.filter(attempt=self.second).order_by("pk").first()
            event = ExamGradeEvent.objects.create(
                attempt=self.second, question=answer.question, old_score=0, new_score=1, max_points=1
            )
        for flag in ("off", "on"):  # «on» olsa da imtahan silinməyib → rədd
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = %s", [flag])
                cursor.execute("DELETE FROM exams_examgradeevent WHERE id = %s", [event.pk])
        with bypass_rls():
            self.assertTrue(ExamGradeEvent.objects.filter(pk=event.pk).exists())

    def test_loose_chance_grant_is_purged_with_exam(self):
        """2026-10-24 (sahib, «JS Loop»): müraciətə bağlı olmayan şans qeydi sınaq imtahanı ilə birlikdə silinir."""
        with bypass_rls():
            grant = ExamChanceGrant.objects.create(
                organization=self.org, student=self.student, exam_id=self.exam.pk, exam_title=TITLE, reason="technical"
            )
            other = ExamChanceGrant.objects.create(
                organization=self.org, student=self.student, exam_id=self.other.pk, reason="technical"
            )
        dry = self._counts(self._call())
        self.assertEqual(dry["chance_grants_deleted"], "1")
        self.assertEqual(dry["retake_links"], "0")
        self.assertEqual(dry["blocked"], "0")
        counts = self._counts(self._apply())
        self.assertEqual(counts["chance_grants_deleted"], "1")
        with bypass_rls():
            self.assertFalse(ExamAttempt.objects.filter(exam=self.exam).exists())
            self.assertFalse(ExamChanceGrant.objects.filter(pk=grant.pk).exists())
            self.assertTrue(ExamChanceGrant.objects.filter(pk=other.pk).exists())  # başqa imtahanın izi qalır

    def test_chance_grant_trigger_still_blocks_outside_purge(self):
        """İstisna dar qalır (registrar 0097): bayraq yoxdursa və ya imtahan silinməyibsə şans qeydi silinmir."""
        from django.db import DatabaseError, connection, transaction

        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        with bypass_rls():
            grant = ExamChanceGrant.objects.create(
                organization=self.org, student=self.student, exam_id=self.exam.pk, reason="technical"
            )
        for flag in ("off", "on"):  # «on» olsa da imtahan silinməyib → rədd
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.bypass_rls = 'on'")
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = %s", [flag])
                cursor.execute("DELETE FROM registrar_examchancegrant WHERE id = %s", [grant.pk])
        with bypass_rls():
            self.assertTrue(ExamChanceGrant.objects.filter(pk=grant.pk).exists())

    def test_final_exam_is_refused(self):
        final, options = self._exam(title="Final Sınaq", category="final")
        self._finish(final, options, correct=1)
        with self.assertRaisesMessage(CommandError, "trial_exam_refused: final_exam"):
            self._call(
                "--apply", "--reason", REASON, "--i-know-this-is-production", slug=final.slug, title="Final Sınaq"
            )
        with bypass_rls():
            self.assertTrue(ExamAttempt.objects.filter(exam=final).exists())

    def test_prior_value_reported_and_superseded_exam_restored(self):
        with bypass_rls():
            ComponentScore.objects.filter(pk=self._score_row().pk).delete()
            ComponentScore.objects.create(
                organization=self.org, component=self._midterm(), enrollment=self.enrollment, score=Decimal("12")
            )
        # Yeni sınaq imtahanı xananın üstünə avtomatik yazır (audit «old» = 12) və «Cloud Computing»-in
        # rəsmi cəhdini (20) əvəzləyir.
        exam, options = self._exam(title="Cloud Sınaq 2")
        self._finish(exam, options, correct=3)
        self.assertEqual(self._score_row().exam_source["exam_id"], exam.pk)
        args = ("--reason", REASON, "--i-know-this-is-production")
        counts = self._counts(self._call(slug=exam.slug, title="Cloud Sınaq 2"))
        self.assertEqual(counts["journal_component_scores_from_exam"], "1")
        self.assertEqual(counts["journal_prior_values"], "1")
        self.assertEqual(counts["journal_restored_from_other_exam"], "1")
        with self.captureOnCommitCallbacks(execute=True):
            counts = self._counts(self._call("--apply", *args, slug=exam.slug, title="Cloud Sınaq 2"))
        self.assertEqual(counts["journal_restored_from_other_exam"], "1")
        row = self._score_row()  # silinməyən imtahanın rəsmi cəhdi xanaya qayıtdı
        self.assertEqual(row.exam_source["exam_id"], self.exam.pk)
        self.assertEqual(row.score, Decimal("20"))
        # Əsas sınaq imtahanı da silinəndə xana tam boşalır (başqa mənbə yoxdur).
        self._apply()
        self.assertIsNone(self._score_row())


class PurgeTrialExamWorkflowTests(_PurgeSetup):
    """``prod-data-ops.yml`` ağ siyahısı + loga düşən sətrin süzgəci əmrin çıxışı ilə uyğun gəlir."""

    def test_workflow_whitelists_command_and_filters_counts_line(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - purge_trial_exam\n", text)
        self.assertIn("Sınaq midterm-in silinməsi — sahibin 2026-10-21 tapşırığı", text)
        pattern = re.search(r"grep -E '(\^trial_exam_purge: [^']+)'", text).group(1)
        line = self._call()
        self.assertRegex(line, pattern)
        self.assertNotIn(self.student.username, line)
        slug_pattern = re.search(r'match "\$TEACHER" \'(\^\[a-z0-9_-\][^\']+)\'', text).group(1)
        self.assertRegex(self.exam.slug, slug_pattern)
