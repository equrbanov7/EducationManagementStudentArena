"""``repair_applications_20261116`` — MR-000393 (seçmə fənn), MR-000395 (proqram), MR-000396 (jurnal köçürməsi)."""

from __future__ import annotations

import datetime
import pathlib
import re
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import OrgUnit
from apps.registrar import services as registrar_services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    GroupElectiveChoice,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests.subgroup_base import SubgroupFixture
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services import applications_repair_2026_11_16 as repair
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .factories import TEACHER_PERMS, activate_member, make_row, make_task
from .test_plan_offerings import PlanOfferingBase, User

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "apps16: "
COMMAND = "repair_applications_20261116"


def _parse(text: str) -> tuple[dict, str]:
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch


def _call(org, actor, *extra):
    out = StringIO()
    call_command(COMMAND, "--org", org.slug, "--actor", actor.username, *extra, stdout=out)
    for line in out.getvalue().splitlines():
        # prod-data-ops süzgəci: açar YALNIZ [a-z_], dəyər [0-9a-z_-].
        assert re.fullmatch(r"apps16: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*", line), line
    return _parse(out.getvalue())


class SpecTest(SimpleTestCase):
    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"          - {COMMAND}\n", text)
        self.assertIn(f"#   {COMMAND} — ", text)
        self.assertIn(f"            {COMMAND})\n", text)
        self.assertIn(f'[ "$COMMAND" = "{COMMAND}" ]', text)
        self.assertIn("|apps16|", text)
        self.assertIn("^apps16-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)

    def test_no_prod_ids_in_spec(self):
        source = pathlib.Path(repair.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", source))

    def test_failure_code_is_grep_friendly(self):
        from apps.workload.management.commands.repair_applications_20261116 import failure_code

        code = failure_code(ValueError("Boom 42!"))
        self.assertRegex(code, r"^[a-z_]+$")
        self.assertTrue(code.startswith("applications_repair_failed_valueerror_boom"))


class ElectiveAndProgramTest(PlanOfferingBase):
    """A (2132T seçmə bloku) + B (505/6 MB proqramı) — eyni təşkilatda, C atlanır."""

    code = "APS"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.root = User.objects.create_superuser("aps.root", "aps.root@x.test", "pw")
        cls.curriculum.status = "approved"
        cls.curriculum.save(update_fields=["status"])
        cls.group = cls.stack["group"]
        OrgUnit.objects.filter(pk=cls.group.pk).update(name="2132 T")
        cls.group.refresh_from_db()
        cls.gender = Subject.objects.create(organization=cls.org, code="APS-GEN", name="Genderin tarixi", ects=3)
        cls.social = Subject.objects.create(organization=cls.org, code="APS-SOS", name="Sosial tarix", ects=3)
        Subject.objects.create(organization=cls.org, code="APS-SOS2", name="Sosial tarix", ects=3)  # blokda deyil
        for subject in (cls.gender, cls.social):
            CurriculumSubject.objects.create(
                organization=cls.org,
                curriculum=cls.curriculum,
                subject=subject,
                semester_number=1,
                is_elective=True,
                elective_group="SB-1",
            )
        cls.teacher = User.objects.create_user("aps.teacher", "aps.teacher@x.test", "pw")
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.COURSE,
        )
        cls._program_world()

    @classmethod
    def _program_world(cls):
        unit = OrgUnit.objects.create
        chair = cls.stack["chair"]
        mb_unit = unit(
            organization=cls.org,
            name="Malekulyar biologiya",
            slug="aps-mb",
            unit_type=OrgUnitType.SPECIALTY,
            parent=chair,
        )
        gen_unit = unit(
            organization=cls.org, name="Genetika", slug="aps-gen", unit_type=OrgUnitType.SPECIALTY, parent=chair
        )
        cls.mb_group = unit(
            organization=cls.org, name="505/6 MB", slug="aps-5056", unit_type=OrgUnitType.GROUP, parent=mb_unit
        )
        peer = unit(organization=cls.org, name="505/5MB", slug="aps-5055", unit_type=OrgUnitType.GROUP, parent=mb_unit)
        cls.gen_program = Program.objects.create(
            organization=cls.org, code="APS-G", name="Genetika", degree_level="master", specialty_unit=gen_unit
        )
        cls.mb_program = Program.objects.create(
            organization=cls.org,
            code="APS-M",
            name="Malekulyar biologiya",
            degree_level="master",
            specialty_unit=mb_unit,
        )
        cls.gen_curriculum = Curriculum.objects.create(
            organization=cls.org, program=cls.gen_program, admission_year=2026
        )
        Curriculum.objects.create(organization=cls.org, program=cls.mb_program, admission_year=2026, status="draft")
        cls.mb_curriculum = Curriculum.objects.create(
            organization=cls.org, program=cls.mb_program, admission_year=2026, version=2, status="approved"
        )
        mb_2025 = Curriculum.objects.create(organization=cls.org, program=cls.mb_program, admission_year=2025)
        cls.moved = [cls._record(f"mv{n}", cls.mb_group, cls.gen_program, cls.gen_curriculum, 2026) for n in (1, 2)]
        old_year = Curriculum.objects.create(organization=cls.org, program=cls.gen_program, admission_year=2024)
        cls.no_plan = cls._record("np", cls.mb_group, cls.gen_program, old_year, 2024)
        cls._record("peer", peer, cls.mb_program, mb_2025, 2025)

    @classmethod
    def _record(cls, suffix, group, program, curriculum, year):
        user = User.objects.create_user(f"aps.b.{suffix}", f"aps{suffix}@x.test", "pw")
        activate_member(cls.org, user, "student", permissions=["course.view"], level=10)
        return StudentAcademicRecord.objects.create(
            organization=cls.org, student=user, program=program, curriculum=curriculum, group=group, admission_year=year
        )

    def setUp(self):
        patch = mock.patch.object(repair, "PERIOD", f"Payız {self.code} 2026/2027")
        patch.start()
        self.addCleanup(patch.stop)
        self.period = self.stack["period"]
        registrar_services.choose_group_elective(
            organization=self.org,
            group=self.group,
            curriculum=self.curriculum,
            period=self.period,
            elective_group="SB-1",
            subject=self.gender,
            enforce_window=False,
        )
        self.old_journal = CourseOffering.objects.get(subject=self.gender, group=self.group, period=self.period)
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED, created_by=self.office)
        self.row = make_row(task, {**self.stack, "subject": self.social}, lecture_total=30, seminar_total=0)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity=Activity.LECTURE, hours=30
        )

    def _choice(self):
        return GroupElectiveChoice.objects.get(organization=self.org, group=self.group, period=self.period)

    def _programs(self):
        return [StudentAcademicRecord.objects.get(pk=row.pk).program_id for row in [*self.moved, self.no_plan]]

    def test_dry_run_apply_rerun_and_undo(self):
        dry, batch = _call(self.org, self.root)
        self.assertEqual(batch, "")
        self.assertEqual(
            (dry["a_choice_switched"], dry["a_journal_created"], dry["a_old_journal_deactivated"]), ("1", "1", "1")
        )
        self.assertEqual(
            (dry["b_records_moved"], dry["b_curriculum_missing"], dry["b_genetika_records"]), ("2", "1", "3")
        )
        self.assertEqual((dry["c_skipped"], dry["c_student_unresolved"]), ("1", "1"))
        self.assertEqual(self._choice().chosen_subject_id, self.gender.pk)
        self.assertFalse(CourseOffering.objects.filter(subject=self.social).exists())
        self.assertEqual(set(self._programs()), {self.gen_program.pk})

        applied, batch = _call(self.org, self.root, "--apply")
        self.assertRegex(batch, r"^apps16-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(applied["a_students_enrolled"], "1")
        self.assertEqual(self._choice().chosen_subject_id, self.social.pk)
        journal = CourseOffering.objects.get(subject=self.social, group=self.group, period=self.period)
        self.assertEqual((journal.is_active, journal.instructor_id), (True, self.teacher.pk))
        self.assertTrue(Enrollment.objects.filter(offering=journal, student=self.student, status="enrolled").exists())
        self.old_journal.refresh_from_db()
        self.assertFalse(self.old_journal.is_active)
        self.assertFalse(Enrollment.objects.filter(offering=self.old_journal, status="enrolled").exists())
        moved = StudentAcademicRecord.objects.get(pk=self.moved[0].pk)
        self.assertEqual((moved.program_id, moved.curriculum_id), (self.mb_program.pk, self.mb_curriculum.pk))
        self.assertEqual(StudentAcademicRecord.objects.get(pk=self.no_plan.pk).program_id, self.gen_program.pk)

        again, _ = _call(self.org, self.root, "--apply")
        self.assertEqual((again["a_already_done"], again["b_already_done"]), ("1", "2"))
        self.assertNotIn("b_records_moved", again)

        undone, _ = _call(self.org, self.root, "--apply", "--undo", "--batch", batch)
        self.assertEqual((undone["a_undo_choice_restored"], undone["b_undo_restored"]), ("1", "2"))
        self.assertEqual(undone["a_undo_new_journal_deactivated"], "1")
        self.assertEqual(self._choice().chosen_subject_id, self.gender.pk)
        self.old_journal.refresh_from_db()
        self.assertTrue(self.old_journal.is_active)
        self.assertTrue(
            Enrollment.objects.filter(offering=self.old_journal, student=self.student, status="enrolled").exists()
        )
        journal.refresh_from_db()
        self.assertFalse(journal.is_active)
        self.assertEqual(set(self._programs()), {self.gen_program.pk})

    def test_plan_prep_adds_block_row_and_undo_removes_it(self):
        """Sahib 2026-11-17: «Sosial tarix» planın blokunda yoxdursa «Genderin tarixi» sətrindən köçürülür."""
        CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.social).delete()
        CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.gender).update(
            credits=5, lecture_hours=30
        )
        applied, batch = _call(self.org, self.root, "--apply")
        self.assertEqual((applied["pa_rows_added"], applied["a_choice_switched"]), ("1", "1"))
        added = CurriculumSubject.objects.get(curriculum=self.curriculum, subject=self.social)
        self.assertEqual(
            (added.elective_group, added.is_elective, added.credits, added.lecture_hours), ("SB-1", True, 5, 30)
        )
        again, _ = _call(self.org, self.root, "--apply")
        self.assertNotIn("pa_rows_added", again)
        undone, _ = _call(self.org, self.root, "--apply", "--undo", "--batch", batch)
        self.assertEqual((undone["a_undo_choice_restored"], undone["pa_undo_rows_deleted"]), ("1", "1"))
        self.assertFalse(CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.social).exists())

    def test_plan_prep_creates_missing_block_with_both_options(self):
        """Prod: planda cari semestrin bloku heç yoxdur — qərardakı blok iki variantla yaradılır."""
        CurriculumSubject.objects.filter(curriculum=self.curriculum, subject__in=[self.gender, self.social]).delete()
        applied, batch = _call(self.org, self.root, "--apply")
        self.assertEqual(
            (applied["pa_blocks_created"], applied["pa_rows_added"], applied["a_choice_switched"]), ("1", "2", "1")
        )
        block = CurriculumSubject.objects.filter(curriculum=self.curriculum, elective_group="SB-1", is_elective=True)
        self.assertEqual(set(block.values_list("subject_id", flat=True)), {self.gender.pk, self.social.pk})
        self.assertEqual(block.get(subject=self.social).credits, 3)
        undone, _ = _call(self.org, self.root, "--apply", "--undo", "--batch", batch)
        self.assertEqual((undone["a_undo_choice_restored"], undone["pa_undo_rows_deleted"]), ("1", "2"))
        self.assertFalse(block.exists())

    def test_plan_prep_clones_previous_year_plan(self):
        """Sahib 2026-11-17: hədəf proqramın qəbul ili planı yoxdursa əvvəlki ilin planı sətirləri ilə köçürülür."""
        Curriculum.objects.filter(program=self.mb_program, admission_year=2026).delete()
        source = Curriculum.objects.get(program=self.mb_program, admission_year=2025)
        Curriculum.objects.filter(pk=source.pk).update(status="approved")
        CurriculumSubject.objects.create(
            organization=self.org, curriculum=source, subject=self.gender, semester_number=2, credits=4
        )
        dry, _ = _call(self.org, self.root)
        self.assertEqual((dry["pb_plans_cloned"], dry["pb_rows_copied"], dry["b_records_moved"]), ("1", "1", "2"))
        self.assertEqual(dry["pb_source_plan_missing"], "1")  # 2024 qeydi — mənbə yoxdur, qalanı yenə hazırlanır
        self.assertFalse(Curriculum.objects.filter(program=self.mb_program, admission_year=2026).exists())
        applied, batch = _call(self.org, self.root, "--apply")
        clone = Curriculum.objects.get(program=self.mb_program, admission_year=2026)
        self.assertEqual(clone.status, "approved")
        self.assertEqual(
            list(
                CurriculumSubject.objects.filter(curriculum=clone).values_list(
                    "subject_id", "semester_number", "credits"
                )
            ),
            [(self.gender.pk, 2, 4)],
        )
        self.assertEqual(StudentAcademicRecord.objects.get(pk=self.moved[0].pk).curriculum_id, clone.pk)
        undone, _ = _call(self.org, self.root, "--apply", "--undo", "--batch", batch)
        self.assertEqual((undone["b_undo_restored"], undone["pb_undo_plans_deleted"]), ("2", "1"))
        self.assertFalse(Curriculum.objects.filter(pk=clone.pk).exists())

    def test_old_journal_with_lessons_stays_active(self):
        Lesson.objects.create(
            organization=self.org, offering=self.old_journal, date=datetime.date(2026, 9, 15), kind="lecture"
        )
        applied, _ = _call(self.org, self.root, "--apply")
        self.assertEqual((applied["a_choice_switched"], applied["a_old_journal_has_lessons_kept"]), ("1", "1"))
        self.old_journal.refresh_from_db()
        self.assertTrue(self.old_journal.is_active)

    def test_missing_teacher_skips_part_a_only(self):
        TeacherAssignment.objects.filter(row=self.row).delete()
        dry, _ = _call(self.org, self.root)
        self.assertEqual((dry["a_skipped"], dry["a_row_teacher_missing"], dry["b_records_moved"]), ("1", "1", "2"))
        self.assertNotIn("a_choice_switched", dry)

    def test_non_superuser_and_bad_batch_are_refused(self):
        with self.assertRaisesRegex(CommandError, "actor_must_be_active_superuser"):
            _call(self.org, self.teacher)
        with self.assertRaisesRegex(CommandError, "applications_repair_batch_invalid"):
            _call(self.org, self.root, "--undo", "--batch", "icarry-20261116-000000-abcd")
        with self.assertRaisesRegex(CommandError, "applications_repair_undo_needs_batch"):
            _call(self.org, self.root, "--undo")


class MoveStudentTest(SubgroupFixture, TestCase):
    """C — tələbə öz qrupunun (935 BM) jurnalından «935 ing» jurnalına; xanalar mənbədə qalır."""

    PREFIX = "ap16c"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            OrgUnit.objects.filter(pk=cls.group2.pk).update(name="935 BM")
            OrgUnit.objects.filter(pk=cls.group1.pk).update(name="935 ing")
            role = cls.org.roles.get(name="teacher")
            cls.gunay = cls._member("ap16c_gunay", role)
            cls.aytac = cls._member("ap16c_aytac", role)
            User.objects.filter(pk=cls.gunay.pk).update(first_name="Günay", last_name="Əmirova")
            User.objects.filter(pk=cls.aytac.pk).update(first_name="Aytac", last_name="Salmanlı")
            User.objects.filter(pk=cls.student.pk).update(first_name="Mədinə", last_name="Kərimli")
            CourseOffering.objects.filter(pk=cls.own_history.pk).update(instructor=cls.gunay)
            CourseOffering.objects.filter(pk=cls.history_g1.pk).update(instructor=cls.aytac)

    def setUp(self):
        patch = mock.patch.object(repair, "PERIOD", "Payız 2025/2026")
        patch.start()
        self.addCleanup(patch.stop)
        with bypass_rls():
            self.source = Enrollment.objects.get(student=self.student, offering=self.own_history)
            for day, status in ((1, "present"), (2, "absent"), (3, "present")):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.own_history,
                    date=datetime.date(2025, 10, day),
                    kind="seminar",
                    start_time=datetime.time(9, 0),
                    end_time=datetime.time(10, 20),
                )
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.source, status=status)

    def test_move_keeps_cells_and_undo_restores(self):
        dry, _ = _call(self.org, self.owner)
        self.assertEqual((dry["c_moved"], dry["c_cells_kept"]), ("1", "3"))
        self.assertEqual((dry["a_group_unresolved"], dry["b_group_unresolved"]), ("1", "1"))
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=self.student, offering=self.history_g1).exists())

        applied, batch = _call(self.org, self.owner, "--apply")
        self.assertEqual((applied["c_moved"], applied["c_cells_kept"]), ("1", "3"))
        self.assertGreater(int(applied["c_absence_hours"]), 0)
        with bypass_rls():
            target = Enrollment.objects.get(student=self.student, offering=self.history_g1)
            self.source.refresh_from_db()
            self.assertEqual((target.status, target.source_group_id), ("enrolled", self.group2.pk))
            self.assertEqual((self.source.status, self.source.superseded_by_id), ("dropped", target.pk))
            self.assertEqual(LessonMark.objects.filter(enrollment=self.source).count(), 3)

        again, _ = _call(self.org, self.owner, "--apply")
        self.assertEqual(again["c_already_done"], "1")

        undone, _ = _call(self.org, self.owner, "--apply", "--undo", "--batch", batch)
        self.assertEqual(undone["c_undo_restored"], "1")
        with bypass_rls():
            self.source.refresh_from_db()
            target.refresh_from_db()
            self.assertEqual((self.source.status, self.source.superseded_by_id), ("enrolled", None))
            self.assertEqual(target.status, "dropped")
            self.assertEqual(LessonMark.objects.filter(enrollment=self.source).count(), 3)

    def test_other_teacher_target_is_not_guessed(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.history_g1.pk).update(instructor=self.teacher)
        dry, _ = _call(self.org, self.owner)
        self.assertEqual((dry["c_skipped"], dry["c_target_unresolved"]), ("1", "1"))
