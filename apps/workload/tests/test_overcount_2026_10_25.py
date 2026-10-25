"""Sahib 2026-10-25: «lazımından artıq çıxmasın ortaya — patok dərsi olanda 30 saat 2-yə vurulmur» + «seminarda da
patok ola bilər — 60 saatlıq fənn bir qrup kimi 60 saat».

``fix_workload_overcount``: dublikat sətirlər (eyni / oxşar fənn adı + kəsişən qrup) və SÜBUTLU birgə dərs (jurnalda
eyni tarix + saat + növ) bir dəfə sayılır; qərar tələb edən hallar dəyişmir; dry-run heç nə yazmır; idempotent;
``--undo`` snapshot-dan geri qaytarır; jurnal (açılışın saatı / sahibi) dəyişmir.
"""

from __future__ import annotations

import io
import os
import stat
import tempfile
from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Sum
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Lesson, Subject
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow, WorkloadAmendment
from apps.workload.services.overcount_detect import same_subject, subject_key
from apps.workload.services.overcount_fix import NOTE_PREFIX
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()
NINE = time(9, 0)
LOAD_NOTE = "Dərs yükü faylından əlavə olundu (Tədris şöbəsi)"


class SubjectKeyTests(SimpleTestCase):
    def test_english_title_in_parentheses_is_same_subject(self):
        self.assertEqual(
            subject_key("Rəqəmsal kriminalistikanın əsasları (Digital Forensics fudamentals"),
            subject_key("Rəqəmsal kriminalistikanın əsasları"),
        )

    def test_level_groups_stay_distinct(self):
        left = subject_key("Xarici dildə kommunikasiya-1(elementary)")
        right = subject_key("Xarici dildə kommunikasiya-1(intermediate)")
        self.assertNotEqual(left, right)
        self.assertFalse(same_subject(left, right))

    def test_similar_spelling_matches_but_numbers_must_agree(self):
        self.assertTrue(
            same_subject(subject_key("Verilənlər bazası sistemləri"), subject_key("Verilənlərin bazası sistemləri"))
        )
        self.assertFalse(
            same_subject(subject_key("Proqramlaşdırmanın əsasları -1"), subject_key("Proqramlaşdırmanın əsasları -2"))
        )


class OvercountCommandTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-overcount")
        self.stack = make_structure(self.org, code="OVC")
        self.group2 = OrgUnit.objects.create(
            organization=self.org,
            name="OVC-237",
            slug="wl-overcount-ovc-group2",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        self.admin = User.objects.create_user("oc_admin", "oc@x.test", "pw", is_superuser=True, is_staff=True)
        self.teacher = User.objects.create_user("oc_t", "t@x.test", "pw", first_name="Lalə", last_name="Testova")
        self.other = User.objects.create_user("oc_o", "o@x.test", "pw", first_name="Nərgiz", last_name="Başqa")
        for user in (self.teacher, self.other):
            activate_member(
                self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"],
                scope_type=RoleScopeType.COURSE,
            )  # fmt: skip
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED)

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _row(self, *, groups=None, lecture=30, seminar=30, teacher="t", subject=None, note=""):
        row = make_row(self.task, self.stack, lecture_total=lecture, seminar_total=seminar)
        if subject is not None:
            row.subject = subject
        row.note = note
        row.save()
        row.groups.set(groups or [self.stack["group"]])
        who = {"t": self.teacher, "o": self.other, "v": None}[teacher]
        for activity, hours in ((Activity.LECTURE, lecture), (Activity.SEMINAR, seminar)):
            if hours:
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=who, activity=activity, hours=hours
                )
        return row

    def _offering(self, group, *, hours=60):
        return CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=group,
            instructor=self.teacher,
            lesson_hours=hours,
        )

    def _lessons(self, offering, *, kind="lecture", start=NINE, days=(1, 8, 15), instructor=None):
        for day in days:
            Lesson.objects.create(
                organization=self.org,
                offering=offering,
                date=date(2026, 9, day),
                kind=kind,
                start_time=start,
                instructor=instructor,
            )

    def _run(self, *extra, report=""):
        out = io.StringIO()
        args = ["fix_workload_overcount", "--org", self.org.slug, "--year", YEAR, "--actor", "oc_admin", "--no-notify"]
        if report:
            args += ["--report", report]
        call_command(*args, *extra, stdout=out)
        return out.getvalue()

    def _total(self, user=None) -> int:
        return int(
            TeacherAssignment.objects.filter(teacher=user or self.teacher).aggregate(total=Sum("hours"))["total"] or 0
        )

    @staticmethod
    def _count(output: str, key: str) -> int:
        return int(output.split(f" {key}=")[1].split()[0])

    # ── dublikat ──────────────────────────────────────────────────────────
    def test_renamed_subject_repeat_removed_once_and_undo_restores(self):
        self._row()
        renamed = Subject.objects.create(organization=self.org, code="OVC102", name="Alqoritmlər (Algorithms)")
        repeat = self._row(subject=renamed, note=LOAD_NOTE)
        self.assertEqual(self._total(), 120)

        dry = self._run()
        self.assertEqual(self._count(dry, "rows_deleted_same_teacher_repeat"), 1)
        self.assertEqual(self._total(), 120)  # dry-run heç nə yazmır

        applied = self._run("--apply")
        self.assertEqual(self._count(applied, "rows_deleted_same_teacher_repeat"), 1)
        self.assertEqual(self._total(), 60)
        self.assertFalse(TeachingTaskRow.objects.filter(pk=repeat.pk).exists())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)  # yenidən təsdiqləndi
        amendment = WorkloadAmendment.objects.get(target_id=repeat.pk)
        self.assertIn(NOTE_PREFIX, amendment.note)
        self.assertEqual(len(amendment.new_values["before"]["assignments"]), 2)

        again = self._run("--apply")
        self.assertEqual(self._count(again, "rows_deleted_same_teacher_repeat"), 0)

        batch = applied.split("batch=")[1].split()[0]
        self._run("--undo", batch, "--apply")
        self.assertTrue(TeachingTaskRow.objects.filter(pk=repeat.pk).exists())
        self.assertEqual(self._total(), 120)
        self._run("--undo", batch, "--apply")  # idempotent
        self.assertEqual(self._total(), 120)

    def test_vacant_repeat_in_other_chair_removed_named_row_kept(self):
        kept = self._row()
        other_stack = make_structure(self.org, code="OV2")
        other_task = make_task(self.org, other_stack["chair"], status=TaskStatus.DISTRIBUTED)
        vacant = make_row(other_task, other_stack, lecture_total=30, seminar_total=30)
        vacant.groups.set([self.stack["group"]])
        for activity in (Activity.LECTURE, Activity.SEMINAR):
            TeacherAssignment.objects.create(
                organization=self.org, row=vacant, teacher=None, activity=activity, hours=30
            )
        output = self._run("--apply")
        self.assertEqual(self._count(output, "rows_deleted_vacant_repeat"), 1)
        self.assertFalse(TeachingTaskRow.objects.filter(pk=vacant.pk).exists())
        self.assertTrue(TeachingTaskRow.objects.filter(pk=kept.pk).exists())

    def test_duplicate_with_different_teachers_is_only_reported(self):
        self._row()
        self._row(teacher="o", note=LOAD_NOTE)
        output = self._run("--apply")
        self.assertEqual(self._count(output, "dup_decision_clusters"), 1)
        self.assertEqual((self._total(), self._total(self.other)), (60, 60))

    def test_official_stream_row_kept_group_repeats_removed(self):
        stream = self._row(groups=[self.stack["group"], self.group2])
        self._row(note=LOAD_NOTE)
        self._row(groups=[self.group2], note=LOAD_NOTE)
        self.assertEqual(self._total(), 180)
        output = self._run("--apply")
        self.assertEqual(self._count(output, "rows_deleted_repeat_of_stream_row"), 2)
        self.assertEqual(list(TeachingTaskRow.objects.filter(task=self.task).values_list("pk", flat=True)), [stream.pk])
        self.assertEqual(self._total(), 60)

    # ── birgə dərs (patok) ────────────────────────────────────────────────
    def test_joint_lecture_with_journal_evidence_counted_once(self):
        first = self._row()
        second = self._row(groups=[self.group2])
        off1, off2 = self._offering(self.stack["group"]), self._offering(self.group2)
        self._lessons(off1)
        self._lessons(off2)
        output = self._run("--apply")
        self.assertEqual(self._count(output, "rows_zeroed_lecture"), 1)
        self.assertEqual(self._total(), 90)  # mühazirə 30 bir dəfə + seminar 30 × 2
        zeroed = TeachingTaskRow.objects.get(pk=second.pk)
        self.assertEqual((zeroed.lecture_total, zeroed.union_count, zeroed.lecture_plan), (0, 0, 30))
        self.assertIn(NOTE_PREFIX, zeroed.note)
        self.assertEqual(TeachingTaskRow.objects.get(pk=first.pk).lecture_total, 30)
        for offering in (off1, off2):  # jurnal: saat və sahibi dəyişmir
            offering.refresh_from_db()
            self.assertEqual((offering.lesson_hours, offering.instructor_id), (60, self.teacher.pk))
        self.assertEqual(self._count(self._run("--apply"), "rows_zeroed_lecture"), 0)

    def test_joint_seminar_with_evidence_also_counted_once(self):
        self._row()
        self._row(groups=[self.group2])
        off1, off2 = self._offering(self.stack["group"]), self._offering(self.group2)
        for offering in (off1, off2):
            self._lessons(offering)
            self._lessons(offering, kind="seminar", start=time(11, 0))
        output = self._run("--apply")
        self.assertEqual(
            (self._count(output, "rows_zeroed_lecture"), self._count(output, "rows_zeroed_seminar")), (1, 1)
        )
        self.assertEqual(self._total(), 60)  # «60 saatlıq fənn — bir qrup kimi 60 saat»

    def test_lecture_stream_of_one_teacher_seminars_of_others_stay_per_group(self):
        """Sahib: «mühazirə bir müəllimdə, seminar digərində» — axın yalnız EYNİ növ + EYNİ müəllim arasında."""
        third = User.objects.create_user("oc_c", "c@x.test", "pw", first_name="Cavid", last_name="Üçüncü")
        activate_member(
            self.org, third, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"],
            scope_type=RoleScopeType.COURSE,
        )  # fmt: skip
        rows = []
        for group, seminar_teacher in ((self.stack["group"], self.other), (self.group2, third)):
            row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30)
            row.groups.set([group])
            TeacherAssignment.objects.create(
                organization=self.org, row=row, teacher=self.teacher, activity=Activity.LECTURE, hours=30
            )
            TeacherAssignment.objects.create(
                organization=self.org, row=row, teacher=seminar_teacher, activity=Activity.SEMINAR, hours=30
            )
            offering = self._offering(group)
            self._lessons(offering)  # mühazirə: eyni tarix + saat, açılışın müəllimi (A)
            # Seminarlar da EYNİ vaxtdadır, amma fərqli müəllimlər (B, C) — axın deyil.
            self._lessons(offering, kind="seminar", start=time(11, 0), instructor=seminar_teacher)
            rows.append(row)
        output = self._run("--apply")
        self.assertEqual(
            (self._count(output, "rows_zeroed_lecture"), self._count(output, "rows_zeroed_seminar")), (1, 0)
        )
        self.assertEqual((self._total(), self._total(self.other), self._total(third)), (30, 30, 30))
        self.assertEqual(
            sorted(TeachingTaskRow.objects.filter(pk__in=[r.pk for r in rows]).values_list("seminar_total", flat=True)),
            [30, 30],
        )

    def test_separate_rows_without_evidence_unchanged(self):
        self._row()
        self._row(groups=[self.group2])
        self._lessons(self._offering(self.stack["group"]), start=NINE)
        self._lessons(self._offering(self.group2), start=time(13, 0))
        output = self._run("--apply")
        self.assertEqual(self._count(output, "rows_zeroed_lecture"), 0)
        self.assertEqual(self._total(), 120)

    # ── hesabat ───────────────────────────────────────────────────────────
    def test_report_is_private_and_stdout_has_no_names(self):
        self._row()
        self._row(note=LOAD_NOTE)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overload_audit.md")
            output = self._run(report=path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        self.assertIn("Lalə Testova", text)
        self.assertIn("## 2. Müəllim yükləri", text)
        self.assertNotIn("Testova", output)


class OvercountWorkflowTests(SimpleTestCase):
    def test_prod_data_ops_whitelists_command_with_counts_only_log(self):
        import pathlib
        import re

        text = (pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          - fix_workload_overcount\n", text)
        block = text.split("            fix_workload_overcount)\n")[1].split(";;")[0]
        self.assertIn('--report "/tmp/overcount_report_${GITHUB_RUN_ID}.md"', block)
        self.assertIn("--undo", block)
        pattern = re.compile(r"^overcount: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
        self.assertIn(pattern.pattern, text.replace("'", ""))
        for line in (
            "overcount: mode=apply dup_clusters_fixed=3 hours_removed_named=120",
            "overcount: batch=overcount-20261025-170046-7f30",
        ):
            self.assertRegex(line, pattern)
        self.assertNotRegex("overcount: teacher=Lalə Testova", pattern)
