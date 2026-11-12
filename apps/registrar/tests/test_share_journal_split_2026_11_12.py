"""Sahib 2026-11-12 (MR-000188): ``split_share_journal_20261112`` — pay → ayrıca alt qrup jurnalı, undo, qoruyucular."""

from __future__ import annotations

import datetime
import pathlib
import re
from collections import Counter
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase

from apps.organizations.models import Membership
from apps.registrar import share_journal_split_2026_11_12 as split
from apps.registrar.management.commands.split_share_journal_20261112 import failure_code
from apps.registrar.models import (
    AssessmentComponent,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    JournalShare,
    Lesson,
    LessonMark,
)
from apps.registrar.share_journal_split_undo_2026_11_12 import undo
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
User = get_user_model()


class WiringTest(SimpleTestCase):
    def test_workflow_wiring_and_summary_keys(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - split_share_journal_20261112\n", text)
        self.assertRegex(text, r"\|split_share_journal_20261112[|)]")
        self.assertIn('[ "$COMMAND" = "split_share_journal_20261112" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("share_split: journals_split=1 marks_copied=3", pattern)
        self.assertRegex("share_split: batch=sharesplit-20261112-101500-ab12", pattern)

    def test_counter_keys_pass_the_log_filter(self):
        for module in (split, __import__("apps.registrar.share_journal_split_undo_2026_11_12", fromlist=["x"])):
            source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
            keys = re.findall(r'counts\["([^"]+)"\]', source)
            self.assertTrue(keys)
            self.assertTrue(all(re.fullmatch(r"[a-z_]+", key) for key in keys), keys)

    def test_fixed_spec_is_ids_only(self):
        self.assertEqual(len(set(split.STUDENTS)), 9)
        self.assertNotEqual(split.OWNER, split.TEACHER)

    def test_failure_code_is_sanitized(self):
        self.assertEqual(failure_code(split.Blocked("roster_changed")), "share_split_blocked_roster_changed")
        code = failure_code(ValueError("Bad «thing» 42"))
        self.assertRegex(code, r"^share_split_failed_[a-z0-9_]+$")


class SplitTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.partner = User.objects.create_user("gr_partner", "gr_partner@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.partner,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.mover_a = cls._make_student("gr_mover_a", cls.group1)
            cls.mover_b = cls._make_student("gr_mover_b", cls.group1)
            cls.admin = User.objects.create_superuser("gr_admin", "gr_admin@qku.edu.az", "pw")

    def setUp(self):
        with bypass_rls():
            self.rows = {
                row.student_id: row
                for row in Enrollment.objects.filter(offering=self.offering, status="enrolled").order_by("pk")
            }
            self.move = [self.rows[self.mover_a.pk], self.rows[self.mover_b.pk]]
            self.stay = self.rows[self.host.pk]
            self.partner_share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.partner, kinds=[]
            )
            self.partner_share.enrollments.set(self.move)
            self.owner_share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.teacher, kinds=[]
            )
            self.owner_share.enrollments.set([self.stay])
            day = datetime.date(2025, 10, 1)
            self.partner_lesson = self._lesson(day, self.partner)
            self.legacy_lesson = self._lesson(day + datetime.timedelta(days=1), None)
            self.owner_lesson = self._lesson(day + datetime.timedelta(days=2), self.teacher)
            for row in self.move:
                self._mark(self.partner_lesson, row, "absent")
            self._mark(self.legacy_lesson, self.move[0], "present", score=7)
            self._mark(self.legacy_lesson, self.stay, "present", score=9)
            self._mark(self.owner_lesson, self.move[0], "present")
            self._mark(self.owner_lesson, self.stay, "present")
            self.midterm = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            ComponentScore.objects.create(
                organization=self.org, component=self.midterm, enrollment=self.move[0], score=24
            )
            ComponentScore.objects.create(organization=self.org, component=self.midterm, enrollment=self.stay, score=20)
        self.spec = {
            "offering": str(self.offering.pk),
            "owner": self.teacher.pk,
            "teacher": self.partner.pk,
            "students": (self.mover_a.pk, self.mover_b.pk),
            "group_name": "G1-2",
        }

    def _lesson(self, day, instructor):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=day,
            kind="seminar",
            hours=2,
            start_time=datetime.time(10, 10),
            instructor=instructor,
        )

    def _mark(self, lesson, row, status, score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=row, status=status, score=score
        )

    def _run(self, spec=None):
        counts = Counter()
        splitter = split.Splitter(organization=self.org, actor=self.admin, counts=counts, spec=spec or self.spec)
        splitter.run()
        return counts, splitter

    def _target(self):
        return CourseOffering.objects.get(group__settings__share_split=split.MARKER, is_active=True)

    def test_split_moves_partner_students_lessons_and_scores(self):
        with bypass_rls():
            counts, splitter = self._run()
            target = self._target()
            self.assertTrue(splitter.batch.startswith("sharesplit-"))
            self.assertEqual(target.instructor_id, self.partner.pk)
            self.assertEqual(target.subject_id, self.offering.subject_id)
            self.assertEqual(target.group.settings["parent_group"], str(self.group1.pk))
            self.assertEqual(target.group.parent_id, self.group1.parent_id)
            rows = list(Enrollment.objects.filter(offering=target, status="enrolled"))
            self.assertEqual({row.student_id for row in rows}, {self.mover_a.pk, self.mover_b.pk})
            self.assertTrue(all(row.source_group_id == self.group1.pk for row in rows))
            # partner + legacy dərsləri köçür, sahibin dərsi köçmür.
            self.assertEqual(Lesson.objects.filter(offering=target).count(), 2)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=target).count(), 3)
            self.assertEqual(counts["marks_other_teacher_kept"], 1)
            # mənbədə partnyorun dərsi silinir, ortaq legacy dərs qalır (sahibin tələbəsi ilə).
            self.assertFalse(Lesson.objects.filter(pk=self.partner_lesson.pk).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.legacy_lesson.pk).exists())
            self.assertEqual(counts["source_lessons_deleted"], 1)
            self.assertEqual(counts["source_lessons_kept_shared"], 1)
            score = ComponentScore.objects.get(component__offering=target)
            self.assertEqual((score.component.name, int(score.score)), ("Midterm", 24))
            self.assertEqual(
                set(Enrollment.objects.filter(pk__in=[row.pk for row in self.move]).values_list("status", flat=True)),
                {"dropped"},
            )
            self.assertEqual(Enrollment.objects.get(pk=self.stay.pk).status, "enrolled")
            self.assertFalse(JournalShare.objects.filter(offering=self.offering, is_active=True).exists())
            again, _ = self._run()
            self.assertEqual(again["already_split"], 1)

    def test_undo_restores_source_exactly(self):
        with bypass_rls():
            original = set(LessonMark.objects.filter(lesson=self.partner_lesson).values_list("pk", "status"))
            self._run()
            target_id = self._target().pk
            counts = Counter()
            undo(organization=self.org, actor=self.admin, counts=counts)
            self.assertEqual(counts["undo_splits"], 1)
            self.assertFalse(CourseOffering.objects.filter(pk=target_id).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.partner_lesson.pk).exists())
            self.assertEqual(
                set(LessonMark.objects.filter(lesson_id=self.partner_lesson.pk).values_list("pk", "status")), original
            )
            self.assertEqual(
                set(Enrollment.objects.filter(pk__in=[row.pk for row in self.move]).values_list("status", flat=True)),
                {"enrolled"},
            )
            self.assertEqual(JournalShare.objects.filter(offering=self.offering, is_active=True).count(), 2)
            again = Counter()
            undo(organization=self.org, actor=self.admin, counts=again)
            self.assertEqual(again["undo_already_done"], 1)

    def test_undo_blocked_after_teacher_writes(self):
        with bypass_rls():
            self._run()
            target = self._target()
            Lesson.objects.create(
                organization=self.org, offering=target, date=datetime.date(2025, 11, 1), kind="seminar", hours=2
            )
            counts = Counter()
            undo(organization=self.org, actor=self.admin, counts=counts)
            self.assertEqual(counts["undo_blocked_post_split_data"], 1)
            self.assertTrue(CourseOffering.objects.filter(pk=target.pk, is_active=True).exists())

    def test_guards_block_without_writing(self):
        with bypass_rls():
            FinalGrade.objects.create(organization=self.org, enrollment=self.move[0], exam_score=40)
            with self.assertRaises(split.Blocked) as caught:
                self._run()
            self.assertEqual(caught.exception.code, "students_have_final_results")
            with self.assertRaises(split.Blocked) as changed:
                self._run({**self.spec, "owner": self.partner.pk})
            self.assertEqual(changed.exception.code, "source_owner_changed")
            with self.assertRaises(split.Blocked) as roster:
                self._run({**self.spec, "students": (self.mover_a.pk, self.far_student.pk)})
            self.assertEqual(roster.exception.code, "roster_changed")

    def test_command_dry_run_writes_nothing(self):
        out = StringIO()
        from unittest import mock

        with mock.patch.object(split, "_SPEC", self.spec):
            call_command("split_share_journal_20261112", org=self.org.slug, actor=self.admin.username, stdout=out)
        text = out.getvalue()
        self.assertIn("share_split: mode=dry_run", text)
        self.assertIn("journals_split=1", text)
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.filter(group__settings__share_split=split.MARKER).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.partner_lesson.pk).exists())
