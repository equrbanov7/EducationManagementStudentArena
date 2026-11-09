"""``move_politologiya_rows_20261109`` — başqa kafedranın tapşırığına düşmüş Politologiya sətirləri öz tapşırığına
(sahib 2026-11-09). Plan sabit prod id-lərdir; test eyni id-lərlə qurur: dry-run yazmır, apply köçürür,
533DBİ sətri ML/MU/İ sətrinə qoşulub silinir, Heydərli bölgüləri saathesabı olur, təkrar qaçış idempotentdir."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.constants import Activity, Season, TaskStatus
from apps.workload.management.commands import move_politologiya_rows_20261109 as command_module
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.tests.factories import make_org, make_structure, make_task
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class MovePolitologiyaRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("mpr")
            cls.it = make_structure(cls.org, code="IT")
            cls.dz = make_structure(cls.org, code="DZ")
            cls.pol = make_structure(cls.org, code="POL")
            cls.actor = User.objects.create_superuser("mpr_actor", "mpr_actor@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("mpr_heyderli", "h@qku.edu.az", "pw")
            it_task = make_task(cls.org, cls.it["chair"], status=TaskStatus.AMENDED)
            TeachingTask.objects.filter(pk=it_task.pk).update(id=command_module.MOVES[0]["source_task"])
            dz_task = make_task(cls.org, cls.dz["chair"], status=TaskStatus.AMENDED)
            TeachingTask.objects.filter(pk=dz_task.pk).update(id=command_module.MOVES[3]["source_task"])
            pol_task = make_task(cls.org, cls.pol["chair"], status=TaskStatus.AMENDED)
            TeachingTask.objects.filter(pk=pol_task.pk).update(id=command_module.TARGET_TASK)
            cls.it_task = TeachingTask.objects.get(pk=command_module.MOVES[0]["source_task"])
            cls.dz_task = TeachingTask.objects.get(pk=command_module.MOVES[3]["source_task"])
            cls.pol_task = TeachingTask.objects.get(pk=command_module.TARGET_TASK)
            cls.dbi = OrgUnit.objects.create(
                organization=cls.org,
                name="533DBİ",
                slug="mpr-533dbi",
                unit_type=OrgUnitType.GROUP,
                parent=cls.it["specialty"],
            )
            OrgUnit.objects.filter(pk=cls.dbi.pk).update(id=command_module.MERGE["group"])
            for spec in command_module.MOVES:
                stack = cls.it if spec["source_task"] == str(cls.it_task.pk) else cls.dz
                task = cls.it_task if spec["source_task"] == str(cls.it_task.pk) else cls.dz_task
                cls._row(task, stack, spec["row"], lecture=15, seminar=15, groups_text="533ML, 533MU, 533İ")
                for activity in (Activity.LECTURE, Activity.SEMINAR):
                    TeacherAssignment.objects.create(
                        organization=cls.org, row_id=spec["row"], teacher=cls.teacher, activity=activity, hours=15
                    )
            cls._row(cls.it_task, cls.it, command_module.MERGE["row"], lecture=0, seminar=30, groups_text="533DBİ")
            TeacherAssignment.objects.create(
                organization=cls.org,
                row_id=command_module.MERGE["row"],
                teacher=cls.teacher,
                activity=Activity.SEMINAR,
                hours=30,
            )

    @classmethod
    def _row(cls, task, stack, row_id, *, lecture, seminar, groups_text):
        row = TeachingTaskRow.objects.create(
            id=row_id,
            organization=cls.org,
            task=task,
            season=Season.FALL,
            period=stack["period"],
            subject=stack["subject"],
            specialty=stack["specialty"],
            faculty=stack["faculty"],
            groups_text=groups_text,
            student_count=25,
            union_count=1,
            subgroup_count=1,
            lecture_plan=lecture,
            lecture_total=lecture,
            seminar_plan=seminar,
            seminar_total=seminar,
            total_hours=lecture + seminar,
            credits_value=6,
        )
        row.groups.set([stack["group"]])
        return row

    def _call(self, *, apply=False):
        out = StringIO()
        call_command(
            "move_politologiya_rows_20261109", org=self.org.slug, actor=self.actor.username, apply=apply, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def test_dry_run_counts_and_writes_nothing(self):
        counts = self._call()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual((counts["rows_moved"], counts["merged_rows_removed"]), ("5", "1"))
        with bypass_rls():
            self.assertEqual(TeachingTaskRow.objects.filter(task=self.pol_task).count(), 0)
            self.assertTrue(TeachingTaskRow.objects.filter(pk=command_module.MERGE["row"]).exists())

    def test_apply_moves_rows_merges_dbi_and_marks_hourly(self):
        counts = self._call(apply=True)
        self.assertEqual(counts["mode"], "apply")
        self.assertEqual(
            (counts["rows_moved"], counts["merged_rows_removed"], counts["merged_assignments_removed"]), ("5", "1", "1")
        )
        self.assertEqual(counts["assignments_hourly_set"], "6")  # Heydərlinin 3 sətri × 2 bölgü
        with bypass_rls():
            self.assertEqual(TeachingTaskRow.objects.filter(task=self.pol_task).count(), 5)
            self.assertEqual(TeachingTaskRow.objects.filter(task__in=[self.it_task, self.dz_task]).count(), 0)
            self.assertFalse(TeachingTaskRow.objects.filter(pk=command_module.MERGE["row"]).exists())
            into = TeachingTaskRow.objects.get(pk=command_module.MERGE["into_row"])
            self.assertEqual(into.groups_text, command_module.MERGE["groups_text"])
            self.assertTrue(into.groups.filter(pk=command_module.MERGE["group"]).exists())
            self.assertEqual(TeacherAssignment.objects.filter(row=into, is_hourly_paid=True).count(), 2)
            esgerov_rows = [spec["row"] for spec in command_module.MOVES if not spec["hourly"]]
            self.assertFalse(TeacherAssignment.objects.filter(row_id__in=esgerov_rows, is_hourly_paid=True).exists())
        again = self._call(apply=True)
        self.assertEqual((again["already_moved"], again["already_merged"]), ("5", "1"))
        self.assertNotIn("rows_moved", again)

    def test_workflow_wiring(self):
        from pathlib import Path

        text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/prod-data-ops.yml").read_text()
        self.assertEqual(text.count("- move_politologiya_rows_20261109"), 1)
        self.assertIn('[ "$COMMAND" = "move_politologiya_rows_20261109" ]', text)
        self.assertIn("|task_rows_move|", text)
