"""Sahib 2026-11-12 (MR-000317): ``split_group_journal_20261112`` — birləşmiş qrup jurnalı → qrupun öz jurnalı."""

from __future__ import annotations

import datetime
import pathlib
import re
from collections import Counter
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.registrar import group_journal_split_2026_11_12 as split
from apps.registrar import group_journal_split_undo_2026_11_12 as split_undo
from apps.registrar.management.commands.split_group_journal_20261112 import failure_code
from apps.registrar.models import (
    AssessmentComponent,
    ComponentScore,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
    ScheduleSlot,
)
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class WiringTest(SimpleTestCase):
    def test_workflow_wiring_and_summary_keys(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - split_group_journal_20261112\n", text)
        self.assertRegex(text, r"\|split_group_journal_20261112[|)]")
        self.assertIn('[ "$COMMAND" = "split_group_journal_20261112" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("group_split: journals_split=1 marks_copied=3", pattern)
        self.assertRegex("group_split: batch=groupsplit-20261112-101500-ab12", pattern)

    def test_counter_keys_pass_the_log_filter(self):
        for module in (split, split_undo):
            source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
            keys = re.findall(r'counts\["([^"]+)"\]', source)
            self.assertTrue(keys)
            self.assertTrue(all(re.fullmatch(r"[a-z_]+", key) for key in keys), keys)

    def test_failure_code_is_sanitized(self):
        self.assertEqual(failure_code(split.Blocked("target_has_lessons")), "group_split_blocked_target_has_lessons")
        self.assertRegex(failure_code(ValueError("Bad «thing» 42")), r"^group_split_failed_[a-z0-9_]+$")


class GroupSplitTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.guest_b = cls._make_student("gr_guest_b", cls.group2)

    def setUp(self):
        self._drop_own_history(self.guest)  # hədəfdə dropped yazılış → yenidən aktivləşir
        with bypass_rls():
            Enrollment.objects.filter(offering=self.other_offering, student=self.guest_b).delete()  # → yaradılır
            self.src = {}
            for student in (self.guest, self.guest_b):
                self.src[student.pk] = Enrollment.objects.create(
                    organization=self.org, offering=self.offering, student=student, status="enrolled"
                )
            self.host_row = Enrollment.objects.get(offering=self.offering, student=self.host)
            g, gb, h = self.src[self.guest.pk], self.src[self.guest_b.pk], self.host_row
            day = datetime.date(2025, 10, 6)
            self.lecture = self._lesson(day, "lecture", 15)
            self.own_seminar = self._lesson(day, "seminar", 17)  # yalnız G2 → köçür və mənbədən silinir
            self.mixed_seminar = self._lesson(day + datetime.timedelta(days=7), "seminar", 17)  # G2 çoxluq + G1
            self.g1_seminar = self._lesson(day, "seminar", 15)  # G1 çoxluq — G2 xanası köçmür
            for row in (g, gb, h):
                self._mark(self.lecture, row, "present")
            self._mark(self.own_seminar, g, "present", 7)
            self._mark(self.own_seminar, gb, "absent")
            self._mark(self.mixed_seminar, g, "present", 8)
            self._mark(self.mixed_seminar, gb, "present", 6)
            self._mark(self.mixed_seminar, h, "absent")
            self._mark(self.g1_seminar, h, "present", 9)
            self._mark(self.g1_seminar, self.extra_g1(), "present", 5)
            self._mark(self.g1_seminar, g, "absent")
            midterm = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            ComponentScore.objects.create(organization=self.org, component=midterm, enrollment=g, score=22)
            for kind, start in (("lecture", 15), ("seminar", 15)):
                ScheduleSlot.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    weekday=1,
                    start_time=datetime.time(start, 15),
                    end_time=datetime.time(start + 1, 45),
                    kind=kind,
                )
            Lesson.objects.filter(offering=self.other_offering).delete()
        self.spec = {
            "source": str(self.offering.pk),
            "target": str(self.other_offering.pk),
            "group": str(self.group2.pk),
        }

    def extra_g1(self):
        if not hasattr(self, "_extra"):
            student = self._make_student(f"gr_g1_{id(self)}", self.group1)
            self._extra = Enrollment.objects.get(offering=self.offering, student=student)
        return self._extra

    def _lesson(self, day, kind, hour):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=day,
            kind=kind,
            hours=2,
            start_time=datetime.time(hour, 15),
            instructor=self.teacher,
        )

    def _mark(self, lesson, row, status, score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=row, status=status, score=score
        )

    def _run(self, **spec):
        counts = Counter()
        splitter = split.GroupSplitter(organization=self.org, actor=self.owner, counts=counts, **{**self.spec, **spec})
        splitter.run()
        return counts, splitter

    def test_split_moves_group_students_lessons_scores(self):
        with bypass_rls():
            counts, splitter = self._run()
            self.assertTrue(splitter.batch.startswith("groupsplit-"))
            target = self.other_offering
            rows = Enrollment.objects.filter(offering=target, status="enrolled")
            self.assertEqual({row.student_id for row in rows}, {self.guest.pk, self.guest_b.pk})
            self.assertEqual((counts["target_enrollments_created"], counts["target_enrollments_reactivated"]), (1, 1))
            self.assertEqual(counts["lessons_shared_created"], 1)
            self.assertEqual(counts["lessons_moved_created"], 2)
            self.assertEqual(counts["marks_copied"], 2 + 2 + 2)
            self.assertEqual(counts["marks_minority_kept"], 1)
            # yalnız G2 seminarı mənbədən silinir; qarışıq seminar və mühazirə qalır.
            self.assertFalse(Lesson.objects.filter(pk=self.own_seminar.pk).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.mixed_seminar.pk).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.lecture.pk).exists())
            self.assertEqual((counts["source_lessons_deleted"], counts["source_lessons_kept_shared"]), (1, 1))
            self.assertEqual(
                sorted(Lesson.objects.filter(offering=target).values_list("kind", flat=True)),
                ["lecture", "seminar", "seminar"],
            )
            score = ComponentScore.objects.get(component__offering=target)
            self.assertEqual((score.component.name, int(score.score)), ("Midterm", 22))
            self.assertEqual(
                set(
                    Enrollment.objects.filter(pk__in=[r.pk for r in self.src.values()]).values_list("status", flat=True)
                ),
                {"dropped"},
            )
            self.assertEqual(Enrollment.objects.get(pk=self.host_row.pk).status, "enrolled")
            # mühazirə slotu hədəfə kopyalanır, seminar slotu yox.
            self.assertEqual(
                list(ScheduleSlot.objects.filter(offering=target).values_list("kind", flat=True)), ["lecture"]
            )
            again, _ = self._run()
            self.assertEqual(again["already_split"], 1)

    def test_undo_restores_source_exactly(self):
        with bypass_rls():
            before = set(LessonMark.objects.filter(lesson=self.own_seminar).values_list("pk", "status", "score"))
            self._run()
            counts = Counter()
            split_undo.undo(organization=self.org, actor=self.owner, counts=counts, **self.spec)
            self.assertEqual(counts["undo_splits"], 1)
            self.assertEqual(
                set(LessonMark.objects.filter(lesson_id=self.own_seminar.pk).values_list("pk", "status", "score")),
                before,
            )
            self.assertEqual(
                set(
                    Enrollment.objects.filter(pk__in=[r.pk for r in self.src.values()]).values_list("status", flat=True)
                ),
                {"enrolled"},
            )
            target_rows = Enrollment.objects.filter(offering=self.other_offering)
            self.assertFalse(target_rows.filter(student=self.guest_b).exists())
            self.assertEqual(target_rows.get(student=self.guest).status, "dropped")
            self.assertFalse(Lesson.objects.filter(offering=self.other_offering).exists())
            self.assertFalse(ScheduleSlot.all_objects.filter(offering=self.other_offering).exists())
            again = Counter()
            split_undo.undo(organization=self.org, actor=self.owner, counts=again, **self.spec)
            self.assertEqual(again["undo_already_done"], 1)
            # geri qaytarılandan sonra yenidən tətbiq oluna bilir.
            redo, _ = self._run()
            self.assertEqual(redo["journals_split"], 1)

    def test_undo_blocked_after_teacher_writes(self):
        with bypass_rls():
            self._run()
            Lesson.objects.create(
                organization=self.org,
                offering=self.other_offering,
                date=datetime.date(2025, 11, 3),
                kind="seminar",
                hours=2,
            )
            counts = Counter()
            split_undo.undo(organization=self.org, actor=self.owner, counts=counts, **self.spec)
            self.assertEqual(counts["undo_blocked_post_split_data"], 1)
            self.assertEqual(Enrollment.objects.filter(offering=self.other_offering, status="enrolled").count(), 2)

    def test_guards_block_without_writing(self):
        with bypass_rls():
            FinalGrade.objects.create(organization=self.org, enrollment=self.src[self.guest.pk], exam_score=40)
            with self.assertRaises(split.Blocked) as caught:
                self._run()
            self.assertEqual(caught.exception.code, "students_have_final_results")
            with self.assertRaises(split.Blocked) as mismatch:
                self._run(group=str(self.group1.pk))
            self.assertEqual(mismatch.exception.code, "target_group_mismatch")
            FinalGrade.objects.all().delete()
            Lesson.objects.create(
                organization=self.org, offering=self.other_offering, date=datetime.date(2025, 9, 1), kind="lecture"
            )
            with self.assertRaises(split.Blocked) as busy:
                self._run()
            self.assertEqual(busy.exception.code, "target_has_lessons")
            self.assertFalse(AuditLog.objects.filter(resource_type=split.RESOURCE).exists())

    def test_command_dry_run_writes_nothing(self):
        out = StringIO()
        call_command(
            "split_group_journal_20261112", org=self.org.slug, actor=self._admin().username, stdout=out, **self.spec
        )
        text = out.getvalue()
        self.assertIn("group_split: mode=dry_run", text)
        self.assertIn("journals_split=1", text)
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.own_seminar.pk).exists())
            self.assertFalse(Lesson.objects.filter(offering=self.other_offering).exists())

    def _admin(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_superuser("gs_admin", "gs_admin@qku.edu.az", "pw")
