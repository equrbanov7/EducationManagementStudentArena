"""Test formatlı midterm → jurnalın «Midterm» xanası (sahib 2026-10-21).

«Midterm test olaraq verənlərdə avtomatik olaraq jurnala da düşsün, tələbənin balı əl ilə doldurulmasın,
tələbədə görünsün». Bax ``apps/exams/services/midterm_journal_sync.py`` + ``apps/registrar/midterm_bridge.py``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.audit.models import AuditLog
from apps.exams import score_adjustments
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services import journal_sync, lifecycle, midterm_journal_sync
from apps.exams.tests.test_journal_bridge import _JournalBridgeSetup
from apps.organizations.models import AcademicPeriod
from apps.registrar import gradebook, interim_components, item_corrections
from apps.registrar.models import ComponentScore, CorrectionReason, FinalGrade, KollokviumWindow
from apps.registrar.public import build_student_journal_context
from core.rls import bypass_rls

_AUDIT_TYPE = "registrar.grade.midterm-auto"


class _MidtermSetup(_JournalBridgeSetup):
    """Bridge quraşdırması + dövr «2026/2027» (midterm rejimi)."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
            )
            self.period.refresh_from_db()
            self.offering.refresh_from_db()

    def _exam(self, *, questions=3, exam_type="test", category="midterm", title="MT Test", **fields):
        with bypass_rls():
            exam = Exam.objects.create(
                title=title,
                author=self.teacher,
                organization=self.org,
                subject=self.subject,
                exam_type=exam_type,
                exam_type_extended=category,
                is_active=True,
                **fields,
            )
            options = []
            for order in range(1, questions + 1):
                question = ExamQuestion.objects.create(exam=exam, order=order, text=f"Q{order}", points=1)
                correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
                wrong = ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
                options.append((question, correct, wrong))
        return exam, options

    def _finish(self, exam, options, *, correct, started_at=None, **attempt_fields):
        """``correct`` sual düzgün, qalanı səhv cavablanmış cəhdi bitir (jurnal körpüsü on_commit-də)."""
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", **attempt_fields)
            if started_at is not None:
                ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=started_at)
                attempt.refresh_from_db()
            for index, (question, right, wrong) in enumerate(options):
                answer = ExamAnswer.objects.create(attempt=attempt, question=question)
                answer.selected_options.add(right if index < correct else wrong)
            with self.captureOnCommitCallbacks(execute=True):
                attempt.mark_finished(status="submitted")
        return attempt

    def _midterm(self):
        with bypass_rls():
            return interim_components.ensure_kollokviums(self.offering)[0]

    def _score_row(self):
        with bypass_rls():
            return ComponentScore.objects.filter(component=self._midterm(), enrollment=self.enrollment).first()

    def _audit_count(self):
        with bypass_rls():
            return AuditLog.objects.filter(resource_type=_AUDIT_TYPE, resource_id=str(self.offering.pk)).count()

    def _resync(self, attempt, **kwargs):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            journal_sync.schedule_journal_sync(attempt, **kwargs)


class MidtermAutoWriteTests(_MidtermSetup):
    def test_finished_test_midterm_writes_scaled_score_on_30_scale(self):
        attempt = self._finish(*self._exam(), correct=2)  # 66.7% × 30 = 20
        row = self._score_row()
        self.assertIsNotNone(row)
        self.assertEqual(self._midterm().max_score, 30)
        self.assertEqual(row.score, Decimal("20"))
        self.assertIsNone(row.entered_by)  # sistem yazısı — tələbə deyil
        self.assertEqual(row.exam_source["attempt_id"], attempt.pk)
        self.assertEqual(row.exam_source["exam_title"], "MT Test")
        self.assertIsNone(self._final_grade())  # FinalGrade-ə toxunulmur

    @override_settings(ACADEMIC_SELFWORK_ENABLED=True)
    def test_selfwork_period_uses_20_scale_with_half_up_rounding(self):
        self._finish(*self._exam(), correct=1)  # 33.3% × 20 = 6.67 → 7
        self.assertEqual(self._midterm().max_score, 20)
        self.assertEqual(self._score_row().score, Decimal("7"))

    def test_half_up_rounding_matches_final_bridge(self):
        self._finish(*self._exam(questions=4), correct=1)  # 25% × 30 = 7.5 → 8 (ROUND_HALF_UP)
        self.assertEqual(self._score_row().score, Decimal("8"))

    def test_expelled_test_midterm_writes_zero(self):
        self._finish(*self._exam(), correct=3, supervision_status="removed")
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_trial_attempt_never_syncs(self):
        self._finish(*self._exam(), correct=3, is_trial=True)
        self.assertIsNone(self._score_row())

    def test_graded_written_midterm_is_written_since_2026_10_24(self):
        # Sahib 2026-10-24: yazılı midterm də yoxlanılandan sonra yazılır (əvvəl əl ilə idi) — bax
        # ``test_midterm_graded_journal_2026_10_24.py``.
        exam, _options = self._exam(exam_type="written", questions=1)
        with bypass_rls():
            attempt = ExamAttempt.objects.create(
                user=self.student, exam=exam, status="submitted", teacher_score=Decimal("1"), checked_by_teacher=True
            )
        self._resync(attempt, actor=self.teacher)
        self.assertEqual(self._score_row().score, Decimal("30"))

    def test_old_kollokvium_period_is_not_written(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(academic_year="2024/2025")
        self._finish(*self._exam(), correct=3)
        with bypass_rls():
            self.assertFalse(ComponentScore.objects.filter(enrollment=self.enrollment).exists())

    def test_idempotent_resync_writes_one_audit_row(self):
        attempt = self._finish(*self._exam(), correct=2)
        self.assertEqual(self._audit_count(), 1)
        self._resync(attempt)
        self._resync(attempt)
        self.assertEqual(self._audit_count(), 1)
        with bypass_rls():
            self.assertEqual(ComponentScore.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_appeal_adjustment_resyncs_the_score(self):
        attempt = self._finish(*self._exam(), correct=1)  # 33.3% → 10
        self.assertEqual(self._score_row().score, Decimal("10"))
        bonus = {"effective_test_score": lambda attempt, answers=None: {"effective_percentage": 100}}
        with mock.patch.dict(score_adjustments._HOOKS, bonus):
            self._resync(attempt, actor=self.teacher, appeal_id=77)
        row = self._score_row()
        self.assertEqual(row.score, Decimal("30"))
        self.assertEqual(row.entered_by, self.teacher)
        self.assertEqual(self._audit_count(), 2)
        with bypass_rls():
            last = AuditLog.objects.filter(resource_type=_AUDIT_TYPE).order_by("-created_at").first()
        self.assertEqual(last.changes[0]["appeal"], "77")
        self.assertEqual(last.changes[0]["source"], f"exam_attempt:{attempt.pk}")

    def test_later_attempt_supersedes_and_old_appeal_does_not_overwrite(self):
        exam, options = self._exam()
        now = timezone.now()
        first = self._finish(exam, options, correct=3, started_at=now - datetime.timedelta(hours=2))
        self.assertEqual(self._score_row().score, Decimal("30"))
        second = self._finish(exam, options, correct=0, started_at=now - datetime.timedelta(hours=1), attempt_number=2)
        row = self._score_row()
        self.assertEqual(row.score, Decimal("0"))
        self.assertEqual(row.exam_source["attempt_id"], second.pk)
        self._resync(first)  # köhnə cəhdin gecikmiş apellyasiyası
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_hidden_results_wait_until_published(self):
        exam, options = self._exam(results_hidden_from_students=True)
        self._finish(exam, options, correct=3)
        self.assertIsNone(self._score_row())
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(lifecycle.set_results_hidden(exam, False, by_user=self.teacher))
        self.assertEqual(self._score_row().score, Decimal("30"))

    def test_final_bridge_is_unchanged(self):
        exam, options = self._exam(category="final", title="Final")
        self._finish(exam, options, correct=3)
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))
        self.assertIsNone(self._score_row())


class MidtermManualLockTests(_MidtermSetup):
    def _open_window(self):
        today = timezone.localdate()
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=today - datetime.timedelta(days=1),
                closes_on=today + datetime.timedelta(days=5),
                is_active=True,
            )

    def _manual(self, score):
        entry = {"component_id": str(self._midterm().id), "enrollment_id": str(self.enrollment.id), "score": score}
        with bypass_rls():
            return gradebook.save_component_scores(
                offering=self.offering, entries=[entry], by_user=self.teacher, bypass_edit_window=True
            )

    def _grid_cell(self):
        with bypass_rls():
            grid = interim_components.get_kollokvium_grid(self.offering)
        return grid, grid["rows"][0]["cells"][0]

    def test_manual_entry_open_without_auto_attempt_then_auto_wins_and_locks(self):
        self._open_window()
        self.assertEqual(self._manual("12"), 1)  # avtomatik cəhd yoxdur — müəllim yaza bilir
        _grid, cell = self._grid_cell()
        self.assertTrue(cell["editable"])
        self._finish(*self._exam(), correct=2)
        self.assertEqual(self._score_row().score, Decimal("20"))  # avtomatik bal əl ilə yazılanı əvəz edir
        self.assertEqual(self._manual("5"), 0)  # indi kilidlidir
        self.assertEqual(self._score_row().score, Decimal("20"))
        grid, cell = self._grid_cell()
        self.assertFalse(cell["editable"])
        self.assertEqual(cell["auto"]["exam_title"], "MT Test")
        self.assertTrue(grid["any_auto"])

    def test_teacher_post_cannot_change_auto_score_and_page_shows_badge(self):
        self._open_window()
        attempt = self._finish(*self._exam(), correct=2)
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("registrar:journal_kollokvium_save", args=[self.offering.id])
        client.post(url, {f"kscore__{self._midterm().id}__{self.enrollment.id}": "3"})
        self.assertEqual(self._score_row().score, Decimal("20"))
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id]), {"jt": "kollokvium"})
        html = page.content.decode()
        self.assertEqual(page.status_code, 200)
        self.assertIn("data-jd-auto-source", html)
        self.assertIn(f"/attempt/{attempt.pk}/view/", html)
        self.assertNotIn(f'name="kscore__{self._midterm().id}__{self.enrollment.id}"', html)

    def test_documented_correction_is_the_only_override_and_survives_resync(self):
        attempt = self._finish(*self._exam(), correct=2)
        with bypass_rls():
            item_corrections.apply_component_correction(
                component=self._midterm(),
                enrollment=self.enrollment,
                new_score="25",
                reason=CorrectionReason.TECHNICAL,
                note="Protokol əsasında",
                document=SimpleUploadedFile("doc.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
                by_user=self.owner,
            )
        self.assertEqual(self._score_row().score, Decimal("25"))
        bonus = {"effective_test_score": lambda attempt, answers=None: {"effective_percentage": 100}}
        with mock.patch.dict(score_adjustments._HOOKS, bonus):
            self._resync(attempt, actor=self.teacher, appeal_id=5)
        self.assertEqual(self._score_row().score, Decimal("25"))


class MidtermStudentViewTests(_MidtermSetup):
    def test_student_sees_auto_midterm_score(self):
        self._finish(*self._exam(), correct=2)
        request = RequestFactory().get("/", {"subject": str(self.enrollment.id)})
        request.user = self.student
        with bypass_rls():
            section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
        midterm = section["detail"]["kollokviums"][0]
        self.assertEqual(midterm["score"], Decimal("20"))
        self.assertTrue(midterm["auto"])


class SyncMidtermScoresCommandTests(_MidtermSetup):
    def _seed_old_attempt(self):
        """Qaydadan əvvəl bitmiş cəhd — körpü işləməyib (bal jurnalda yoxdur)."""
        exam, options = self._exam()
        with mock.patch.object(midterm_journal_sync, "sync_midterm_attempt", return_value=("x", None)):
            self._finish(exam, options, correct=3)
        self.assertIsNone(self._score_row())

    def _run(self, *args):
        out = StringIO()
        call_command("sync_midterm_scores", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        self._seed_old_attempt()
        out = self._run("--org", self.org.slug)
        self.assertIn("DRY-RUN", out)
        self.assertIn("written 1", out)
        self.assertIsNone(self._score_row())
        self.assertIn("written 1", self._run("--org", self.org.slug, "--apply"))
        self.assertEqual(self._score_row().score, Decimal("30"))
        self.assertIn("unchanged 1", self._run("--org", self.org.slug, "--apply"))
        self.assertEqual(self._audit_count(), 1)

    def test_other_org_filter_touches_nothing(self):
        self._seed_old_attempt()
        self.assertIn("rəsmi midterm cəhdi 0", self._run("--org", "no-such-org", "--apply"))
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.exists())
        self.assertIsNone(self._score_row())


@pytest.mark.postgres
class MidtermSyncRestrictedRoleTests(_MidtermSetup):
    """İstehsal ssenarisi: NOBYPASSRLS rolu + tenant konteksti; köhnə (2 saatdan böyük) xananın UPDATE-i
    ``trg_journal_mark_guard``-a ilişmir (``journal_unlock``) və RLS sistem yazısını bloklamır."""

    def test_sync_updates_frozen_manual_row_under_rls_app_role(self):
        exam, options = self._exam()
        with bypass_rls():
            component = self._midterm()
            manual = ComponentScore.objects.create(
                organization=self.org, component=component, enrollment=self.enrollment, score=Decimal("12")
            )
            ComponentScore.objects.filter(pk=manual.pk).update(created_at=timezone.now() - datetime.timedelta(hours=5))
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
            for question, right, _wrong in options:
                ExamAnswer.objects.create(attempt=attempt, question=question).selected_options.add(right)
            ExamAttempt.objects.filter(pk=attempt.pk).update(status="submitted", finished_at=timezone.now())
            attempt.refresh_from_db()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            status, row = midterm_journal_sync.sync_midterm_attempt(ExamAttempt.objects.get(pk=attempt.pk))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.assertEqual(status, "written")
        self.assertEqual(row.pk, manual.pk)
        self.assertEqual(self._score_row().score, Decimal("30"))
