"""``split_shared_fin_identity_20261109`` — eyni FİN-lə bir hesaba birləşmiş tələbənin ayrılması (sahib 2026-11-09)."""

import datetime
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt
from apps.registrar.models import AssessmentComponent, ComponentScore, Enrollment
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

User = get_user_model()
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class SplitSharedFinIdentityTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.actor = User.objects.create_superuser("split_actor", "split_actor@qku.edu.az", "pw")

    def _plan(self, cases):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "legacy-identity-split/1", "cases": cases}, ensure_ascii=False))
        return str(path)

    def _call(self, cases, *, apply=False):
        out = StringIO()
        call_command(
            "split_shared_fin_identity_20261109",
            org=self.org.slug,
            actor=self.actor.username,
            file=self._plan(cases),
            apply=apply,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def _holder_guest_enrollment(self):
        """Host-un (FİN sahibi) hesabında guest-in qrupunun (group2) jurnalına «alt qrupdan» düşmüş, azad edilmiş yazılış."""
        with bypass_rls():
            # Adamın hesabı yeni yaradılıb — həmin açılışda öz yazılışı yoxdur.
            self.guest.enrollments.filter(offering=self.other_offering).delete()
            return Enrollment.objects.create(
                organization=self.org,
                student=self.host,
                offering=self.other_offering,
                status=Enrollment.Status.DROPPED,
                source_group=self.group1,
                added_by=self.actor,
                added_at=timezone.now(),
            )

    def test_dry_run_moves_nothing(self):
        enrollment = self._holder_guest_enrollment()
        counts = self._call([{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [str(enrollment.pk)]}])
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts.get("enrollments_moved"), "1", counts)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=self.guest, offering=self.other_offering).exists())

    def test_apply_gives_person_an_own_enrollment_with_the_cells(self):
        from apps.registrar.models import Lesson, LessonMark

        enrollment = self._holder_guest_enrollment()
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.other_offering,
                kind="seminar",
                date=datetime.date(2026, 10, 1),
                hours=2,
            )
            LessonMark.objects.create(
                organization=self.org, enrollment=enrollment, lesson=lesson, status="present", score=7
            )
        counts = self._call(
            [{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [str(enrollment.pk)]}], apply=True
        )
        self.assertEqual(counts["mode"], "apply")
        self.assertEqual(counts["enrollments_moved"], "1")
        self.assertEqual(counts["marks_moved"], "1")
        with bypass_rls():
            target = Enrollment.objects.get(student=self.guest, offering=self.other_offering)
            self.assertEqual((target.status, target.source_group_id), ("enrolled", None))
            self.assertEqual(LessonMark.objects.get(lesson=lesson).enrollment_id, target.pk)
            enrollment.refresh_from_db()
            self.assertEqual((enrollment.student_id, enrollment.status), (self.host.pk, "dropped"))
        # Təkrar: adamın artıq öz yazılışı var → atlanır.
        again = self._call(
            [{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [str(enrollment.pk)]}], apply=True
        )
        self.assertEqual(again["skip_person_has_enrollment"], "1")

    def test_person_with_own_enrollment_is_skipped(self):
        with bypass_rls():
            enrollment = Enrollment.objects.create(
                organization=self.org,
                student=self.host,
                offering=self.other_offering,
                status=Enrollment.Status.DROPPED,
                source_group=self.group1,
            )
        counts = self._call(
            [{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [str(enrollment.pk)]}], apply=True
        )
        self.assertEqual(counts["skip_person_has_enrollment"], "1")
        with bypass_rls():
            enrollment.refresh_from_db()
            self.assertEqual(enrollment.student_id, self.host.pk)

    def test_midterm_attempt_moves_and_holder_auto_score_is_removed(self):
        with bypass_rls():
            exam = Exam.objects.create(
                title="Tarix — Midterm",
                author=self.teacher,
                organization=self.org,
                subject=self.history,
                exam_type="test",
                exam_type_extended="midterm",
                is_active=True,
            )
            finished = timezone.make_aware(datetime.datetime(2026, 11, 3, 12, 56))
            attempt = ExamAttempt.objects.create(user=self.host, exam=exam, status="submitted", finished_at=finished)
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            host_enrollment = self.host.enrollments.get(offering=self.offering)
            ComponentScore.objects.create(
                organization=self.org,
                component=component,
                enrollment=host_enrollment,
                score=16,
                exam_source={"attempt_id": attempt.pk, "exam_id": exam.pk, "percent": "53.3"},
            )
        spec = {"subject": "Tarix", "finished_on": "2026-11-03"}
        with mock.patch(
            "apps.exams.services.midterm_journal_sync.sync_midterm_attempt", return_value=("written", None)
        ) as sync:
            counts = self._call(
                [{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [], "attempts": [spec]}], apply=True
            )
        self.assertEqual(counts["attempts_moved"], "1")
        self.assertEqual(counts["holder_scores_removed"], "1")
        self.assertEqual(counts["attempt_sync_written"], "1")
        self.assertEqual(sync.call_args.args[0].pk, attempt.pk)
        with bypass_rls():
            attempt.refresh_from_db()
            self.assertEqual(attempt.user_id, self.guest.pk)
            self.assertFalse(ComponentScore.objects.filter(component=component, enrollment=host_enrollment).exists())
        # İkinci dəfə: holder-da cəhd qalmayıb → tapılmır, heç nə dəyişmir.
        again = self._call(
            [{"holder": self.host.pk, "person": self.guest.pk, "enrollments": [], "attempts": [spec]}], apply=True
        )
        self.assertEqual(again["skip_attempt_missing"], "1")

    def test_unexpected_failure_surfaces_as_command_error_code(self):
        from apps.exams.management.commands import split_shared_fin_identity_20261109 as command_module

        self.assertEqual(
            command_module.failure_code(RuntimeError("journal mark is frozen (15 min window elapsed)")),
            "legacy_split_failed_runtimeerror_journal_mark_is_frozen_15_min_window_elapsed",
        )
        with mock.patch.object(command_module, "run", side_effect=RuntimeError("boom x")):
            with self.assertRaises(CommandError) as ctx:
                self._call([{"holder": self.host.pk, "person": self.guest.pk, "enrollments": []}])
        self.assertEqual(str(ctx.exception), "legacy_split_failed_runtimeerror_boom_x")

    def test_bad_plan_is_refused(self):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "legacy-identity-split/1", "cases": [{"holder": 1, "person": 1}]}))
        with self.assertRaises(CommandError):
            call_command(
                "split_shared_fin_identity_20261109", org=self.org.slug, actor=self.actor.username, file=str(path)
            )

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - split_shared_fin_identity_20261109\n", text)
        self.assertIn('[ "$COMMAND" = "split_shared_fin_identity_20261109" ]', text)
        self.assertIn("\n            split_shared_fin_identity_20261109)\n", text)
        self.assertIn("^legacy-split-[0-9a-z-]+$", text)
        self.assertIn("|legacy_guests|legacy_split|", text)
