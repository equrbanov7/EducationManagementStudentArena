"""``move_psixologiya_rows_20261115`` — psixologiya fənləri Sosial iş tapşırığından Psixologiya kafedrasının yeni
tapşırığına (sahib 2026-11-15). Dry-run yazmır; apply tapşırığı + dilimi yaradır, yalnız ``row.task`` dəyişir,
sosial iş fənni və başqa kafedranın ümumi fənni qalır, patok ailəsi bölünmür, kənar müəllim ƏLAVƏ üzvlük alır;
təkrar qaçış boşdur; undo hamısını geri qaytarır."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import Subject
from apps.workload.constants import Activity, Season, SliceStatus, TaskStatus
from apps.workload.management.commands import move_psixologiya_rows_20261115 as command_module
from apps.workload.models import TaskFacultySlice, TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_structure, make_task
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


class MovePsixologiyaRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("mpsx")
            cls.stack = make_structure(cls.org, code="PSX")
            cls.sos_chair = OrgUnit.objects.create(
                id=command_module.SOSIAL_CHAIR,
                organization=cls.org,
                name="Sosial iş kafedrası",
                slug="mpsx-sos",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.stack["faculty"],
            )
            cls.psx_chair = OrgUnit.objects.create(
                id=command_module.PSIX_CHAIR,
                organization=cls.org,
                name="Psixologiya kafedrası",
                slug="mpsx-psx",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.stack["faculty"],
            )
            cls.actor = User.objects.create_superuser("mpsx_actor", "mpsx_actor@qku.edu.az", "pw")
            cls.psy_teacher = User.objects.create_user("mpsx_psy", "psy@qku.edu.az", "pw")
            cls.si_teacher = User.objects.create_user("mpsx_si", "si@qku.edu.az", "pw")
            for user, chair in ((cls.psy_teacher, cls.psx_chair), (cls.si_teacher, cls.sos_chair)):
                activate_member(
                    cls.org,
                    user,
                    "teacher",
                    permissions=TEACHER_PERMS,
                    scope_unit=chair,
                    scope_type=RoleScopeType.COURSE,
                )
            task = make_task(cls.org, cls.sos_chair, status=TaskStatus.DISTRIBUTED)
            TeachingTask.objects.filter(pk=task.pk).update(id=command_module.SOURCE_TASK)
            cls.source = TeachingTask.objects.get(pk=command_module.SOURCE_TASK)
            TaskFacultySlice.objects.create(
                organization=cls.org, task=cls.source, faculty=cls.stack["faculty"], status=SliceStatus.APPROVED
            )
            cls.psy_subject = cls._row("Ümumi psixologiya", cls.si_teacher)  # fənn adı → köçür
            cls.social = cls._row("Sosial işin əsasları", cls.psy_teacher)  # sosial iş fənni → qalır
            cls.pedagogy = cls._row("Pedaqogika", cls.psy_teacher)  # müəllimin ştatı Psixologiya → köçür
            cls.pedagogy_partner = cls._row("Pedaqogika", cls.si_teacher, partner=True)  # patok ailəsi → köçür
            cls.philosophy = cls._row("Fəlsəfə", cls.si_teacher)  # Sosial iş müəllimi → qalır

    @classmethod
    def _row(cls, subject_name, teacher, *, partner=False):
        subject = Subject.objects.filter(organization=cls.org, name=subject_name).first()
        if subject is None:
            count = Subject.objects.filter(organization=cls.org).count()
            subject = Subject.objects.create(organization=cls.org, code=f"MPSX{count}", name=subject_name, ects=5)
        row = TeachingTaskRow.objects.create(
            organization=cls.org,
            task=cls.source,
            season=Season.FALL,
            period=cls.stack["period"],
            subject=subject,
            specialty=cls.stack["specialty"],
            faculty=cls.stack["faculty"],
            student_count=20,
            lecture_plan=30,
            lecture_total=0 if partner else 30,
            seminar_plan=30,
            seminar_total=30,
            total_hours=30 if partner else 60,
            credits_value=5,
        )
        row.groups.set([cls.stack["group"]])
        TeacherAssignment.objects.create(
            organization=cls.org, row=row, teacher=teacher, activity=Activity.SEMINAR, hours=30
        )
        return row

    def _call(self, *, apply=False, undo=False):
        out = StringIO()
        call_command(
            "move_psixologiya_rows_20261115",
            org=self.org.slug,
            actor=self.actor.username,
            apply=apply,
            undo=undo,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertTrue(line.startswith(command_module.PREFIX))
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def _task_of(self, row):
        with bypass_rls():
            return str(TeachingTaskRow.objects.get(pk=row.pk).task.chair_id)

    def test_dry_run_counts_and_writes_nothing(self):
        counts = self._call()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["rows_to_move"], "3")
        self.assertEqual(
            (counts["rule_psy_subject"], counts["rule_psy_teachers"], counts["rule_social_subject"]), ("1", "1", "1")
        )
        self.assertEqual(counts["patok_rows_realigned"], "1")
        with bypass_rls():
            self.assertFalse(TeachingTask.objects.filter(chair=self.psx_chair).exists())
            self.assertEqual(TeachingTaskRow.objects.filter(task=self.source).count(), 5)

    def test_apply_moves_rows_keeps_assignments_then_undo(self):
        with bypass_rls():
            assignments_before = sorted(TeacherAssignment.objects.values_list("pk", "row_id", "teacher_id", "hours"))
        counts = self._call(apply=True)
        self.assertEqual((counts["mode"], counts["rows_moved"], counts["target_task_created"]), ("apply", "3", "1"))
        self.assertEqual((counts["slices_copied"], counts["memberships_added"]), ("1", "1"))
        with bypass_rls():
            target = TeachingTask.objects.get(chair=self.psx_chair, academic_year=self.source.academic_year)
            self.assertEqual((target.status, target.revision), (TaskStatus.DISTRIBUTED, self.source.revision))
            self.assertEqual(
                set(target.rows.values_list("pk", flat=True)),
                {self.psy_subject.pk, self.pedagogy.pk, self.pedagogy_partner.pk},
            )
            self.assertEqual(target.slices.get().status, SliceStatus.APPROVED)
            self.assertEqual(
                sorted(TeacherAssignment.objects.values_list("pk", "row_id", "teacher_id", "hours")), assignments_before
            )
            extra = Membership.objects.get(user=self.si_teacher, scope_unit=self.psx_chair)
            self.assertTrue(extra.is_active)
            self.assertFalse(extra.is_primary)
        self.assertEqual(self._task_of(self.social), command_module.SOSIAL_CHAIR)
        self.assertEqual(self._task_of(self.philosophy), command_module.SOSIAL_CHAIR)

        again = self._call(apply=True)
        self.assertEqual(again["rows_to_move"], "0")
        self.assertNotIn("rows_moved", again)

        back = self._call(apply=True, undo=True)
        self.assertEqual(back["mode"], "undo_apply")
        self.assertEqual((back["rows_returned"], back["target_task_deleted"]), ("3", "1"))
        with bypass_rls():
            self.assertEqual(TeachingTaskRow.objects.filter(task=self.source).count(), 5)
            self.assertFalse(TeachingTask.objects.filter(chair=self.psx_chair).exists())
            self.assertFalse(Membership.objects.get(user=self.si_teacher, scope_unit=self.psx_chair).is_active)
        self.assertEqual(self._call(apply=True, undo=True)["nothing_to_undo"], "1")

    def test_workflow_wiring(self):
        text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/prod-data-ops.yml").read_text()
        self.assertEqual(text.count("- move_psixologiya_rows_20261115"), 1)
        self.assertIn("psix_rows_move", text)
