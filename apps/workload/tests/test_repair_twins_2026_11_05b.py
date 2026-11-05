"""Əkiz jurnallar 2026-11-05 (ikinci dəst): ``repair_twins_20261105b`` — sabit id-lər fixture obyektlərinə patch olunur.

A (MR-190 forması): köhnə fənn adındakı W — xanalar + imtahana bağlı Midterm balları; rəsmi T — müəllimin xanaları.
B (MR-161 forması): datalı D (köhnə fənn) + boş əkiz E (düzgün fənn) əvvəlcə ``twin_merge_empty`` ilə D-yə birləşib;
əmr E-ni manifestlə bərpa edir, datanı D → E köçürür, yük sətrinin fənnini dəyişir (və ya dublikat olacaqsa saxlayır).
"""

from __future__ import annotations

import datetime
import pathlib
import re
import uuid
from collections import Counter
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.registrar import midterm_bridge
from apps.registrar import twins_repair_2026_11_05b as dossier
from apps.registrar.interim_components import ensure_kollokviums
from apps.registrar.models import (
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
    ScheduleSlot,
    Subject,
)
from apps.registrar.twin_merge import Merger
from apps.workload.constants import TaskStatus
from apps.workload.management.commands import repair_twins_20261105b as command
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import bypass_rls

User = get_user_model()
D = datetime.date
T = datetime.time
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return {key: int(value) for key, value in out.items()}


def _absent() -> str:
    return str(uuid.uuid4())


class TwinRepairBase(TestCase):
    PREFIX = "tw5b"

    def setUp(self):
        p = self.PREFIX
        self.admin = User.objects.create_superuser(f"{p}_admin", f"{p}_admin@x.test", "pw")
        with bypass_rls():
            self.org = make_org(p, owner=self.admin)
            self.stack = make_structure(self.org, code=p.upper())
            self.period, self.group = self.stack["period"], self.stack["group"]
            self.teacher = User.objects.create_user(f"{p}_teacher", f"{p}_teacher@x.test", "pw")
            activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS)
            self.students = []
            for index in range(3):
                student = User.objects.create_user(f"{p}_st{index}", f"{p}_st{index}@x.test", "pw")
                activate_member(self.org, student, "student")
                self.students.append(student)
            self.old = self.stack["subject"]
            self.new = Subject.objects.create(organization=self.org, code=f"{p.upper()}NEW", name="Yeni ad", ects=6)
        patches = {
            "MR190_SOURCE": _absent(),
            "MR190_TARGET": _absent(),
            "MR161_DATA": _absent(),
            "MR161_TWIN": _absent(),
            "MR161_ROW": _absent(),
        }
        self.patch(patches)

    def patch(self, values: dict) -> None:
        for name, value in values.items():
            started = mock.patch.object(dossier, name, value)
            started.start()
            self.addCleanup(started.stop)

    def offering(self, subject, *students, status="enrolled"):
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=subject, period=self.period, group=self.group, instructor=self.teacher
            )
            for student in students:
                Enrollment.objects.create(organization=self.org, student=student, offering=offering, status=status)
        return offering

    def lesson(self, offering, day, *marks, kind="seminar"):
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org, offering=offering, date=day, start_time=T(10, 10), kind=kind
            )
            for student, status in marks:
                enrollment = Enrollment.objects.get(offering=offering, student=student)
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status=status)
        return lesson

    def call(self, *extra) -> dict:
        out = StringIO()
        call_command(
            "repair_twins_20261105b", "--org", self.org.slug, "--actor", self.admin.username, *extra, stdout=out
        )
        text = out.getvalue()
        self.assertTrue(text.startswith("twin_merge: mode="))
        return _counts(text)

    def fresh(self, offering):
        with bypass_rls():
            return CourseOffering.objects.get(pk=offering.pk)


class ScoredTwinTests(TwinRepairBase):
    """A: W (köhnə ad, xanalar + Midterm + imtahan bağı) → T (rəsmi, müəllimin xanaları)."""

    PREFIX = "tw5a"

    def setUp(self):
        super().setUp()
        s0, s1, s2 = self.students
        self.w = self.offering(self.old, s0, s1)
        self.t = self.offering(self.new, s0, s1)
        with bypass_rls():
            Enrollment.objects.create(organization=self.org, student=s2, offering=self.t, status="suspended")
            self.lesson(self.w, D(2026, 10, 5), (s0, "absent"), (s1, "present"))
            self.lesson(self.t, D(2026, 10, 26), (s0, "present"), (s1, "present"))
            self.component = ensure_kollokviums(self.w)[0]
            Exam = django_apps.get_model("exams", "Exam")
            self.exam = Exam.objects.create(
                author=self.teacher, title="Midterm", organization=self.org, subject=self.old
            )
            self.exam.journal_offerings.add(self.w)
            self.sources = {}
            for index, (student, percent) in enumerate(((s0, 90), (s1, 80))):
                source = midterm_bridge._source_payload(
                    attempt_id=900 + index, exam_id=self.exam.pk, exam_title="Midterm", exam_slug="mt", percent=percent
                )
                self.sources[student.pk] = (source, percent)
                ComponentScore.objects.create(
                    organization=self.org,
                    component=self.component,
                    enrollment=Enrollment.objects.get(offering=self.w, student=student),
                    score=Decimal(percent * 30 // 100),
                    exam_source=source,
                )
        self.patch({"MR190_SOURCE": str(self.w.pk), "MR190_TARGET": str(self.t.pk)})

    def target_scores(self):
        with bypass_rls():
            return {
                row.enrollment.student_id: (row.score, row.exam_source, row.component.name)
                for row in ComponentScore.objects.filter(enrollment__offering=self.t).select_related(
                    "enrollment", "component"
                )
            }

    def test_dry_run_counts_and_writes_nothing(self):
        counts = self.call()
        self.assertEqual(counts["pairs_merged_scored"], 1)
        self.assertEqual(counts["scores_moved"], 2)
        self.assertEqual(counts["exam_links_repointed"], 1)
        self.assertEqual(counts["marks_moved"], 2)
        self.assertTrue(self.fresh(self.w).is_active)
        self.assertEqual(self.target_scores(), {})
        with bypass_rls():
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.w.pk])

    def test_apply_moves_scores_exam_link_and_marks_then_is_idempotent(self):
        counts = self.call("--apply")
        self.assertEqual(counts["pairs_merged_scored"], 1)
        self.assertFalse(self.fresh(self.w).is_active)
        s0, s1, _ = self.students
        scores = self.target_scores()
        self.assertEqual(scores[s0.pk], (Decimal("27"), self.sources[s0.pk][0], "Midterm"))
        self.assertEqual(scores[s1.pk], (Decimal("24"), self.sources[s1.pk][0], "Midterm"))
        with bypass_rls():
            self.assertFalse(ComponentScore.objects.filter(enrollment__offering=self.w).exists())
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.t.pk])
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.t).count(), 4)
            self.assertTrue(
                AuditLog.objects.filter(object_id=str(self.t.pk), changes__kind="twin_merge_scored").exists()
            )
            self.assertTrue(
                AuditLog.objects.filter(resource_type__endswith=".component", resource_id=str(self.t.pk)).exists()
            )
        again = self.call("--apply")
        self.assertEqual(again["already_merged"], 1)
        self.assertNotIn("scores_moved", again)
        self.assertEqual(self.target_scores(), scores)

    def test_exam_resync_after_merge_is_a_no_op_on_target(self):
        self.call("--apply")
        s0 = self.students[0]
        source, percent = self.sources[s0.pk]
        with bypass_rls():
            status, row = midterm_bridge.record_midterm_result(
                student=s0,
                subject_id=self.old.pk,
                organization=self.org,
                score_percent=percent,
                attempt_id=source["attempt_id"],
                exam_id=self.exam.pk,
                exam_title="Midterm",
                exam_slug="mt",
                notify=False,
                offering_ids=[self.t.pk],
            )
        self.assertEqual(status, midterm_bridge.UNCHANGED)
        self.assertEqual(row.enrollment.offering_id, self.t.pk)

    def test_different_score_on_target_refuses_whole_pair(self):
        s0 = self.students[0]
        with bypass_rls():
            ComponentScore.objects.create(
                organization=self.org,
                component=ensure_kollokviums(self.t)[0],
                enrollment=Enrollment.objects.get(offering=self.t, student=s0),
                score=Decimal("11"),
            )
        counts = self.call("--apply")
        self.assertEqual(counts["score_conflict_differs"], 1)
        self.assertEqual(counts["scored_pair_rolled_back"], 1)
        self.assertNotIn("pairs_merged", counts)
        self.assertTrue(self.fresh(self.w).is_active)
        with bypass_rls():
            self.assertEqual(ComponentScore.objects.filter(enrollment__offering=self.w).count(), 2)
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.w.pk])
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.w).count(), 2)

    def test_same_score_on_target_is_kept_not_duplicated(self):
        s0 = self.students[0]
        with bypass_rls():
            ComponentScore.objects.create(
                organization=self.org,
                component=ensure_kollokviums(self.t)[0],
                enrollment=Enrollment.objects.get(offering=self.t, student=s0),
                score=Decimal("27"),
            )
        counts = self.call("--apply")
        self.assertEqual(counts["scores_duplicate_on_target"], 1)
        self.assertEqual(counts["scores_moved"], 1)
        self.assertEqual(counts["pairs_merged_scored"], 1)
        with bypass_rls():
            self.assertEqual(ComponentScore.objects.filter(enrollment__offering=self.t).count(), 2)

    def test_final_grade_blocks_merge_and_rolls_back_moves(self):
        with bypass_rls():
            FinalGrade.objects.create(
                organization=self.org,
                enrollment=Enrollment.objects.get(offering=self.w, student=self.students[1]),
                exam_score=Decimal("40"),
            )
        counts = self.call("--apply")
        self.assertEqual(counts["merger_source_has_scores"], 1)
        self.assertNotIn("scores_moved", counts)
        self.assertTrue(self.fresh(self.w).is_active)
        self.assertEqual(self.target_scores(), {})
        with bypass_rls():
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.w.pk])


class SubjectTwinTests(TwinRepairBase):
    """B: D (köhnə fənn, data) + E (düzgün fənn, boş) — boş birləşmə tətbiq olunub; data E-yə keçməlidir."""

    PREFIX = "tw5c"

    def setUp(self):
        super().setUp()
        s0, s1, s2 = self.students
        self.d = self.offering(self.old, s0, s1, s2)
        self.e = self.offering(self.new, s0, s1)
        with bypass_rls():
            self.lesson(self.d, D(2026, 9, 21), (s0, "present"), (s1, "absent"), (s2, "present"))
            self.lesson(self.d, D(2026, 9, 28), (s0, "present"), (s1, "present"))
            self.slot = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.d,
                weekday=1,
                start_time=T(10, 10),
                end_time=T(11, 30),
                kind="seminar",
                week_type="all",
            )
            self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED)
            self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
            for activity, hours in (("lecture", 30), ("seminar", 15)):
                TeacherAssignment.objects.create(
                    organization=self.org, row=self.row, teacher=self.teacher, activity=activity, hours=hours
                )
            counts = Counter()
            Merger(organization=self.org, actor=self.admin, counts=counts).run(
                [{"source": str(self.e.pk), "target": str(self.d.pk)}]
            )
            assert counts["pairs_merged_empty_source"] == 1, counts
        self.patch({"MR161_DATA": str(self.d.pk), "MR161_TWIN": str(self.e.pk), "MR161_ROW": str(self.row.pk)})
        started = mock.patch.object(command, "MR161_OLD_SUBJECT", str(self.old.pk))
        started.start()
        self.addCleanup(started.stop)

    def group_offerings(self):
        with bypass_rls():
            return sorted(
                (str(pk), active)
                for pk, active in CourseOffering.objects.filter(period=self.period, group=self.group).values_list(
                    "pk", "is_active"
                )
            )

    def test_dry_run_writes_nothing(self):
        counts = self.call()
        self.assertEqual(counts["offerings_restored"], 1)
        self.assertEqual(counts["restore_enrollments"], 2)
        self.assertEqual(counts["pairs_merged_scored"], 1)
        self.assertEqual(counts["load_row_subject_changed"], 1)
        self.assertFalse(self.fresh(self.e).is_active)
        self.assertTrue(self.fresh(self.d).is_active)
        with bypass_rls():
            self.row.refresh_from_db()
        self.assertEqual(self.row.subject_id, self.old.pk)

    def test_apply_restores_twin_moves_data_switches_row_and_is_idempotent(self):
        before = self.group_offerings()
        counts = self.call("--apply")
        self.assertEqual(counts["pairs_merged_scored"], 1)
        self.assertEqual(counts["enrollments_created"], 1)  # s2 yalnız D-də idi
        self.assertEqual(counts["load_row_subject_changed"], 1)
        self.assertTrue(self.fresh(self.e).is_active)
        self.assertFalse(self.fresh(self.d).is_active)
        self.assertEqual(
            self.group_offerings(), sorted((pk, pk == str(self.e.pk)) for pk, _active in before)
        )  # yeni jurnal yaranmadı
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.e).count(), 5)
            self.assertFalse(Lesson.objects.filter(offering=self.d).exists())
            self.assertEqual(
                set(Enrollment.objects.filter(offering=self.e, status="enrolled").values_list("student_id", flat=True)),
                {student.pk for student in self.students},
            )
            self.assertTrue(ScheduleSlot.objects.filter(offering=self.e).exists())
            self.assertTrue(
                AuditLog.objects.filter(object_id=str(self.e.pk), changes__kind="twin_merge_empty_restore").exists()
            )
            self.row.refresh_from_db()
        self.assertEqual(self.row.subject_id, self.new.pk)
        again = self.call("--apply")
        self.assertEqual(again["restore_already_active"], 1)
        self.assertEqual(again["already_merged"], 1)
        self.assertEqual(again["load_row_already"], 1)
        self.assertNotIn("pairs_merged", again)

    def test_reviewed_row_on_target_subject_keeps_old_row(self):
        with bypass_rls():
            reviewed = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
            reviewed.subject = self.new
            reviewed.save(update_fields=["subject"])
        counts = self.call("--apply")
        self.assertEqual(counts["pairs_merged_scored"], 1)
        self.assertEqual(counts["load_row_target_exists"], 1)
        self.assertNotIn("load_row_subject_changed", counts)
        self.assertTrue(self.fresh(self.e).is_active)
        with bypass_rls():
            self.row.refresh_from_db()
        self.assertEqual(self.row.subject_id, self.old.pk)

    def test_manifest_for_other_journal_changes_nothing(self):
        """E-nin manifesti BAŞQA jurnala (D) aiddir — sabit cüt D2 ilə uyğun gəlmir → heç nə yazılmır."""
        with bypass_rls():
            third = Subject.objects.create(organization=self.org, code="TW5C3", name="Üçüncü", ects=6)
        other = self.offering(third, self.students[0])
        self.patch({"MR161_DATA": str(other.pk)})
        counts = self.call("--apply")
        self.assertEqual(counts["restore_manifest_missing"], 1)
        self.assertNotIn("pairs_merged", counts)
        self.assertFalse(self.fresh(self.e).is_active)
        self.assertTrue(self.fresh(self.d).is_active)
        self.assertTrue(self.fresh(other).is_active)

    def test_blocked_merge_rolls_back_restore(self):
        with bypass_rls():
            FinalGrade.objects.create(
                organization=self.org,
                enrollment=Enrollment.objects.get(offering=self.d, student=self.students[0]),
                exam_score=Decimal("40"),
            )
        counts = self.call("--apply")
        self.assertEqual(counts["merger_source_has_scores"], 1)
        self.assertEqual(counts["subject_twin_rolled_back"], 1)
        self.assertNotIn("offerings_restored", counts)
        self.assertFalse(self.fresh(self.e).is_active)
        self.assertTrue(self.fresh(self.d).is_active)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.filter(offering=self.e, status="enrolled").count(), 0)


class WorkflowWiringTest(TestCase):
    def test_workflow_whitelists_and_filters_counts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_twins_20261105b\n", text)
        self.assertIn("            repair_twins_20261105b)\n", text)
        self.assertRegex(text, r'elif [^\n]*\[ "\$COMMAND" = "repair_twins_20261105b" \][^\n]*; then')
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("twin_merge: pairs_merged_scored=1 scores_moved=18 load_row_target_exists=1", pattern)
