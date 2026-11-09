"""``fix_azdili_load_20261110`` — Azərbaycan dili və ədəbiyyatı kafedrasının yükü rəsmi fayla (sahib 2026-11-10).
Plan sabit prod id-lərdir; test eyni id-lərlə qurur: dry-run yazmır, apply 8 sətri İngilis / Sosial iş tapşırığına
köçürür, bölgüsüz 136 Si-2 sətrini silir, saathesabı bayrağını qoyur, axın ortağını bağlayır; təkrar qaçış idempotentdir.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.workload.constants import Activity, Season, TaskStatus
from apps.workload.management.commands import fix_azdili_load_20261110 as command_module
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.tests.factories import make_org, make_structure, make_task
from core.rls import bypass_rls

User = get_user_model()


class FixAzdiliLoadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("azd")
            cls.az = make_structure(cls.org, code="AZD")
            cls.en = make_structure(cls.org, code="ENG")
            cls.so = make_structure(cls.org, code="SOS")
            cls.actor = User.objects.create_superuser("azd_actor", "azd_actor@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("azd_teacher", "t@qku.edu.az", "pw")
            tasks = {}
            for stack, pk in (
                (cls.az, command_module.SOURCE_TASK),
                (cls.en, command_module.ENGLISH_TASK),
                (cls.so, command_module.SOSIAL_TASK),
            ):
                task = make_task(cls.org, stack["chair"], status=TaskStatus.AMENDED)
                TeachingTask.objects.filter(pk=task.pk).update(id=pk)
                tasks[pk] = TeachingTask.objects.get(pk=pk)
            cls.tasks = tasks
            source = tasks[command_module.SOURCE_TASK]
            for pk, _target in command_module.MOVES:
                cls._row(source, pk, lecture=15, seminar=15)
                TeacherAssignment.objects.create(
                    organization=cls.org, row_id=pk, teacher=cls.teacher, activity=Activity.SEMINAR, hours=15
                )
            for pk in command_module.DELETE_ROWS:
                cls._row(source, pk, lecture=0, seminar=45)
                TeacherAssignment.objects.create(
                    organization=cls.org, row_id=pk, teacher=None, activity=Activity.SEMINAR, hours=45
                )
            for pk in command_module.HOURLY_ROWS:
                cls._row(source, pk, lecture=15, seminar=45)
                for activity in (Activity.LECTURE, Activity.SEMINAR):
                    TeacherAssignment.objects.create(
                        organization=cls.org, row_id=pk, teacher=cls.teacher, activity=activity, hours=15
                    )
            for partner, lead in command_module.PATOK:
                cls._row(source, lead, lecture=15, seminar=30)
                cls._row(source, partner, lecture=0, seminar=30)

    @classmethod
    def _row(cls, task, row_id, *, lecture, seminar):
        stack = cls.az
        row = TeachingTaskRow.objects.create(
            id=row_id,
            organization=cls.org,
            task=task,
            season=Season.FALL,
            period=stack["period"],
            subject=stack["subject"],
            specialty=stack["specialty"],
            faculty=stack["faculty"],
            groups_text="3/334F1",
            student_count=25,
            union_count=1,
            subgroup_count=1,
            lecture_plan=lecture,
            lecture_total=lecture,
            seminar_plan=seminar,
            seminar_total=seminar,
            total_hours=lecture + seminar,
            credits_value=5,
        )
        row.groups.set([stack["group"]])
        return row

    def _call(self, *, apply=False):
        out = StringIO()
        call_command("fix_azdili_load_20261110", org=self.org.slug, actor=self.actor.username, apply=apply, stdout=out)
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def test_dry_run_writes_nothing(self):
        counts = self._call()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual((counts["rows_moved"], counts["rows_deleted"], counts["patok_linked"]), ("8", "1", "1"))
        with bypass_rls():
            self.assertEqual(TeachingTaskRow.objects.filter(task_id=command_module.SOURCE_TASK).count(), 17)
            self.assertFalse(TeacherAssignment.objects.filter(is_hourly_paid=True).exists())

    def test_apply_then_idempotent(self):
        counts = self._call(apply=True)
        self.assertEqual(counts["hourly_set"], "12")
        with bypass_rls():
            self.assertEqual(TeachingTaskRow.objects.filter(task_id=command_module.ENGLISH_TASK).count(), 4)
            self.assertEqual(TeachingTaskRow.objects.filter(task_id=command_module.SOSIAL_TASK).count(), 4)
            self.assertFalse(TeachingTaskRow.objects.filter(pk__in=command_module.DELETE_ROWS).exists())
            partner, lead = command_module.PATOK[0]
            self.assertEqual(str(TeachingTaskRow.objects.get(pk=partner).patok_lead_id), lead)
        again = self._call(apply=True)
        self.assertEqual((again["already_moved"], again["already_deleted"], again["already_patok"]), ("8", "1", "1"))
        self.assertNotIn("hourly_set", {k for k, v in again.items() if v != "0"})

    def test_assigned_row_is_not_deleted(self):
        with bypass_rls():
            TeacherAssignment.objects.filter(row_id__in=command_module.DELETE_ROWS).update(teacher=self.teacher)
        counts = self._call(apply=True)
        self.assertEqual(counts["delete_skipped_assigned"], "1")

    def test_failure_code_is_sanitized(self):
        code = command_module.failure_code(ValueError("Bad Thing: x/y"))
        self.assertRegex(code, r"^[a-z0-9_]+$")

    def test_workflow_wiring(self):
        from pathlib import Path

        text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/prod-data-ops.yml").read_text()
        self.assertEqual(text.count("- fix_azdili_load_20261110"), 1)
        self.assertIn('[ "$COMMAND" = "fix_azdili_load_20261110" ]', text)
