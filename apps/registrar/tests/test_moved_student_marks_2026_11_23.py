"""MR-000710: ``copy_moved_student_marks_20261123`` — köhnə jurnaldakı xanalar və Midterm yeni jurnala (boş yerə)."""

from __future__ import annotations

import datetime
import pathlib
from collections import Counter
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.registrar import moved_student_marks_2026_11_23 as fixer
from apps.registrar.models import AssessmentComponent, ComponentScore, Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class SpecTest(SimpleTestCase):
    def test_fixed_ids(self):
        self.assertTrue(fixer.SOURCE_OFFERING.startswith("321772aa-"))
        self.assertTrue(fixer.TARGET_OFFERING.startswith("058265ab-"))
        self.assertEqual(fixer.STUDENT_ID, 2475)

    def test_workflow_runs_the_command(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - copy_moved_student_marks_20261123\n", text)
        self.assertIn("            copy_moved_student_marks_20261123)\n", text)
        self.assertIn("|mvmarks|", text)


class MovedStudentMarksTest(_GuestRosterBase):
    """Mənbə = alt qrupun (G2) öz Tarix jurnalı (``dropped``), hədəf = G1 Tarix jurnalı (``enrolled``)."""

    def setUp(self):
        scope = bypass_rls()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        self.admin = get_user_model().objects.create_superuser("mvm_admin", "mvm_admin@qku.edu.az", "pw")
        self.src = Enrollment.objects.get(student=self.guest, offering=self.other_offering)
        self.src.status = Enrollment.Status.DROPPED
        self.src.save(update_fields=["status"])
        self.dst = Enrollment.objects.create(organization=self.org, student=self.guest, offering=self.offering)
        day = datetime.date(2025, 10, 6)
        self.src_lessons = [
            Lesson.objects.create(
                organization=self.org,
                offering=self.other_offering,
                date=day + datetime.timedelta(days=i),
                kind="seminar",
                hours=2,
            )
            for i in range(3)
        ]
        # Hədəfdə yalnız ilk iki tarix var; ikincidə tələbənin xanası artıq doludur.
        self.dst_lessons = [
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=day + datetime.timedelta(days=i),
                kind="seminar",
                hours=2,
            )
            for i in range(2)
        ]
        LessonMark.objects.create(
            organization=self.org, lesson=self.src_lessons[0], enrollment=self.src, status="absent"
        )
        LessonMark.objects.create(
            organization=self.org, lesson=self.src_lessons[1], enrollment=self.src, status="present", score=8
        )
        LessonMark.objects.create(
            organization=self.org, lesson=self.src_lessons[2], enrollment=self.src, status="present"
        )
        LessonMark.objects.create(
            organization=self.org, lesson=self.dst_lessons[1], enrollment=self.dst, status="present"
        )
        src_mid = AssessmentComponent.objects.create(
            organization=self.org, offering=self.other_offering, name="Midterm", kind="kollokvium", max_score=30
        )
        AssessmentComponent.objects.create(
            organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
        )
        ComponentScore.objects.create(organization=self.org, component=src_mid, enrollment=self.src, score=30)
        for name, value in (
            ("SOURCE_OFFERING", str(self.other_offering.pk)),
            ("TARGET_OFFERING", str(self.offering.pk)),
            ("STUDENT_ID", self.guest.pk),
        ):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_fix(self):
        counts = Counter()
        batch = fixer.run(organization=self.org, actor=self.admin, counts=counts, batch="")
        return counts, batch

    def test_copies_into_empty_matching_cells_and_midterm_then_undo(self):
        counts, batch = self.run_fix()
        self.assertEqual(counts["marks_copied"], 1)
        self.assertEqual(counts["mark_target_filled"], 1)
        self.assertEqual(counts["mark_no_matching_lesson"], 1)
        self.assertEqual(counts["scores_copied"], 1)
        copied = LessonMark.objects.get(lesson=self.dst_lessons[0], enrollment=self.dst)
        self.assertEqual(copied.status, "absent")
        self.assertEqual(
            ComponentScore.objects.get(enrollment=self.dst, component__offering=self.offering).score, Decimal(30)
        )
        self.dst.refresh_from_db()
        self.assertEqual(self.dst.absence_hours, 2)
        again, _ = self.run_fix()
        self.assertEqual(again["nothing_to_copy"], 1)
        undone = Counter()
        fixer.undo(organization=self.org, actor=self.admin, counts=undone, batch=batch)
        self.assertEqual(undone["undo_marks_removed"], 1)
        self.assertEqual(undone["undo_scores_removed"], 1)
        self.assertFalse(LessonMark.objects.filter(lesson=self.dst_lessons[0], enrollment=self.dst).exists())
        self.assertEqual(LessonMark.objects.filter(enrollment=self.src).count(), 3)
