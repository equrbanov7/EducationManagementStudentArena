"""Sahib 2026-11-08: alt qrup jurnalları ana qrupun jurnalına — mühazirədə bir jurnal, seminarda alt qruplar.

Xanalar KOPYALANIR (alt qrup jurnalı passiv olur, xanaları silinmir); eyni tarix + saat + növ → bir dərs; ana jurnalda
dolu xana qalır; bir alt qrupun seminarı həmin seminar alt qrupuna bağlanır; defolt dry-run, idempotent, ``--undo``
geri qaytarır; stdout-da yalnız saylar; prod-data-ops-a qoşulub.
"""

import datetime
import io
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar import services as registrar_services
from apps.registrar import subgroup_journal_merge_2026_11_08 as merge
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    SeminarGroup,
    StudentAcademicRecord,
)
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, User, _LabWorld
from core.constants import OrgUnitType
from core.rls import bypass_rls

T1010, T1150 = datetime.time(10, 10), datetime.time(11, 50)


class SubgroupJournalMergeTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            program = Program.objects.create(organization=self.org, code="SGM", name="Sgm")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2026)
            self.k1, self.k2 = (
                OrgUnit.objects.create(
                    organization=self.org, name=f"LAB-G1 K{n}", slug=f"lab-g1-k{n}", unit_type=OrgUnitType.GROUP
                )
                for n in (1, 2)
            )
            self.s3 = User.objects.create_user("sgm_s3", "sgm_s3@x.test", "pw")
            self.s4 = User.objects.create_user("sgm_s4", "sgm_s4@x.test", "pw")
            for student in (self.s3, self.s4):
                self._member(student, "student", [])
            for student, unit in ((self.students[0], self.k1), (self.s3, self.k1), (self.s4, self.k2)):
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    program=program,
                    curriculum=curriculum,
                    group=unit,
                    admission_year=2026,
                )
            self.o1, self.o2 = (
                registrar_services.get_or_create_offering(
                    organization=self.org, subject=self.offering.subject, period=self.period, group=unit
                )
                for unit in (self.k1, self.k2)
            )
            day, day2 = self.today - datetime.timedelta(days=7), self.today - datetime.timedelta(days=6)
            self.parent_lecture = self._lesson_at(self.offering, day, LessonKind.LECTURE, T1010)
            LessonMark.objects.create(
                organization=self.org, lesson=self.parent_lecture, enrollment=self.e1, status="absent"
            )
            o1_e3 = Enrollment.objects.create(organization=self.org, student=self.s3, offering=self.o1)
            o1_e0 = Enrollment.objects.create(organization=self.org, student=self.students[0], offering=self.o1)
            o2_e4 = Enrollment.objects.create(organization=self.org, student=self.s4, offering=self.o2)
            lecture1 = self._lesson_at(self.o1, day, LessonKind.LECTURE, T1010)
            seminar1 = self._lesson_at(self.o1, day2, LessonKind.SEMINAR, T1150)
            lecture2 = self._lesson_at(self.o2, day, LessonKind.LECTURE, T1010)
            for lesson, enrollment in (
                (lecture1, o1_e3),
                (lecture1, o1_e0),
                (seminar1, o1_e3),
                (seminar1, o1_e0),
                (lecture2, o2_e4),
            ):
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status="present")
        plan = ({"name": "test", "target": str(self.offering.pk), "sources": (str(self.o1.pk), str(self.o2.pk))},)
        patch = mock.patch.object(merge, "PLAN", plan)
        patch.start()
        self.addCleanup(patch.stop)

    def _lesson_at(self, offering, day, kind, start):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day, kind=kind, hours=2, start_time=start
        )

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "merge_subgroup_journals_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^subgroup_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("subgroup_merge: ") :].split())
        counts.pop("family", None)  # ailə başına sətir — cəmlə eyni saylar
        return counts

    def _parent_marks(self):
        with bypass_rls():
            return sorted(
                (mark.lesson.kind, mark.enrollment.student.username, mark.status)
                for mark in LessonMark.objects.filter(lesson__offering=self.offering).select_related(
                    "lesson", "enrollment__student"
                )
            )

    def test_dry_run_apply_idempotent_undo(self):
        before = self._parent_marks()
        counts = self._call()
        self.assertEqual(counts.get("families_merged"), "1", counts)
        self.assertEqual(self._parent_marks(), before)  # dry-run
        counts = self._call("--apply")
        self.assertEqual(counts["enrollments_created"], "2")
        self.assertEqual(counts["lessons_matched"], "2")  # iki alt qrupun 10:10 mühazirəsi → ananın dərsi
        self.assertEqual(counts["lessons_created"], "1")
        self.assertEqual(counts["marks_copied"], "4")
        self.assertEqual(counts["marks_target_kept"], "1")  # ananın «q/b» xanası qalır
        self.assertEqual(counts["seminar_lessons_tagged"], "1")
        self.assertEqual(counts["sources_retired"], "2")
        with bypass_rls():
            lecture = Lesson.objects.filter(offering=self.offering, kind=LessonKind.LECTURE)
            self.assertEqual(lecture.count(), 1)
            seminar = Lesson.objects.get(offering=self.offering, kind=LessonKind.SEMINAR)
            self.assertEqual(seminar.seminar_group, 1)
            self.assertEqual(
                dict(SeminarGroup.objects.filter(offering=self.offering).values_list("number", "name")),
                {1: "LAB-G1 K1", 2: "LAB-G1 K2"},
            )
            groups = dict(
                Enrollment.objects.filter(offering=self.offering).values_list("student__username", "seminar_group")
            )
            self.assertEqual(
                (groups["lab_st0"], groups["sgm_s3"], groups["sgm_s4"], groups["lab_st1"]), (1, 1, 2, None)
            )
            self.assertFalse(CourseOffering.objects.get(pk=self.o1.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.o1).count(), 4)  # silinmir
            self.assertEqual(
                LessonMark.objects.get(
                    lesson__offering=self.offering, enrollment=self.e1, lesson__kind="lecture"
                ).status,
                "absent",
            )
        self.assertEqual(self._call("--apply"), {"already_merged": "1"})
        counts = self._call("--apply", "--undo")
        self.assertEqual(counts["undo_families"], "1")
        self.assertEqual(self._parent_marks(), before)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.o1.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.o2, status="enrolled").count(), 1)
            self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())

    def test_separate_lectures_block_family(self):
        day = self.today - datetime.timedelta(days=3)
        with bypass_rls():
            o1_e3 = Enrollment.objects.get(offering=self.o1, student=self.s3)
            o2_e4 = Enrollment.objects.get(offering=self.o2, student=self.s4)
            own1 = self._lesson_at(self.o1, day, LessonKind.LECTURE, T1010)
            own2 = self._lesson_at(self.o2, day, LessonKind.LECTURE, T1150)  # ayrı saat — patok deyil
            for lesson, enrollment in ((own1, o1_e3), (own2, o2_e4)):
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status="present")
        self.assertEqual(self._call("--apply"), {"family_lectures_separate": "1"})
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.o1.pk).is_active)
            self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())

    def test_merge_that_adds_empty_cells_is_blocked(self):
        with bypass_rls():
            o1_e3 = Enrollment.objects.get(offering=self.o1, student=self.s3)
            for days in (4, 3, 2):  # K1-in K2-də olmayan 3 mühazirəsi → K2 tələbəsinə boş xana
                lesson = self._lesson_at(self.o1, self.today - datetime.timedelta(days=days), LessonKind.LECTURE, T1010)
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=o1_e3, status="present")
        self.assertEqual(self._call("--apply"), {"family_adds_empty_cells": "1"})
        with bypass_rls():
            before = LessonMark.objects.filter(enrollment__student=self.s3).count()
        plan = ({**merge.PLAN[0], "allow_empty_cells": True},)
        with mock.patch.object(merge, "PLAN", plan):
            counts = self._call("--apply")
        self.assertEqual(counts.get("families_merged"), "1", counts)
        with bypass_rls():
            self.assertEqual(
                LessonMark.objects.filter(lesson__offering=self.offering, enrollment__student=self.s3).count(), before
            )

    def test_component_scores_copied_and_final_grade_blocks(self):
        from apps.registrar.models import AssessmentComponent, ComponentScore

        with bypass_rls():
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.o1, name="Midterm", max_score=30
            )
            ComponentScore.objects.create(
                organization=self.org,
                component=component,
                enrollment=Enrollment.objects.get(offering=self.o1, student=self.s3),
                score=17,
            )
        counts = self._call("--apply")
        self.assertEqual((counts["scores_copied"], counts["components_created"]), ("1", "1"))
        with bypass_rls():
            copied = ComponentScore.objects.get(component__offering=self.offering)
            self.assertEqual(
                (copied.component.name, copied.score, copied.enrollment.student_id), ("Midterm", 17, self.s3.pk)
            )
        self.assertEqual(self._call("--apply", "--undo")["undo_scores_deleted"], "1")

    def test_dropped_parent_row_is_reactivated_and_restored_on_undo(self):
        with bypass_rls():
            o1_e0 = Enrollment.objects.get(offering=self.o1, student=self.students[0])
            Enrollment.objects.filter(pk=self.e1.pk).update(status="dropped", superseded_by=o1_e0)
        counts = self._call("--apply")
        self.assertEqual(counts["enrollments_reactivated"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).status, "enrolled")
        self._call("--apply", "--undo")
        with bypass_rls():
            row = Enrollment.objects.get(pk=self.e1.pk)
            self.assertEqual((row.status, row.superseded_by_id), ("dropped", o1_e0.pk))

    def test_seminar_default_puts_parent_own_students_into_subgroup(self):
        """536 Bİ: ana qrupun öz tələbələri (reyestrdə alt qrupu yoxdur) Bi 1 alt qrupudur."""
        with bypass_rls():
            Enrollment.objects.filter(pk=self.e0.pk).update(status="dropped")
            row = Enrollment.objects.create(organization=self.org, student=self.students[1], offering=self.o1)
            for lesson in Lesson.objects.filter(offering=self.o1):
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=row, status="present")
        plan = ({**merge.PLAN[0], "seminar_default_source": str(self.o1.pk)},)
        with mock.patch.object(merge, "PLAN", plan):
            counts = self._call("--apply")
        self.assertEqual(counts.get("families_merged"), "1", counts)
        with bypass_rls():
            number = SeminarGroup.objects.get(offering=self.offering, unit=self.k1).number
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).seminar_group, number)
            self.assertFalse(
                Enrollment.objects.filter(
                    offering=self.offering, status="enrolled", seminar_group__isnull=True
                ).exists()
            )
        with mock.patch.object(merge, "PLAN", plan):
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertIsNone(Enrollment.objects.get(pk=self.e2.pk).seminar_group)

    def test_student_alias_writes_duplicate_marks_to_main_account_row(self):
        """536 Bİ: bloklanmış dublikat hesabın alt qrup xanaları əsas hesabın ana jurnal sətrinə."""
        with bypass_rls():
            duplicate = User.objects.create_user("sgm_dup", "sgm_dup@x.test", "pw")
            self._member(duplicate, "student", [])
            row = Enrollment.objects.create(organization=self.org, student=duplicate, offering=self.o2)
            lecture2 = Lesson.objects.get(offering=self.o2, kind=LessonKind.LECTURE)
            LessonMark.objects.create(organization=self.org, lesson=lecture2, enrollment=row, status="excused")
            Enrollment.objects.filter(pk=self.e2.pk).update(lab_group=None)
        plan = ({**merge.PLAN[0], "student_alias": {str(duplicate.pk): self.students[1].pk}},)
        with mock.patch.object(merge, "PLAN", plan):
            counts = self._call("--apply")
        self.assertEqual(counts.get("families_merged"), "1", counts)
        self.assertEqual(counts["student_alias_mapped"], "1")
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=duplicate).exists())
            self.assertEqual(
                LessonMark.objects.get(
                    lesson__offering=self.offering, lesson__kind="lecture", enrollment=self.e2
                ).status,
                "excused",
            )
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "dropped")

    def test_no_seminar_groups_merges_without_subgroup_rows(self):
        """536 Bİ: hər iki alt qrupun eyni günlü seminarı var — bir jurnal, alt qrup sətri yoxdur."""
        with bypass_rls():
            Enrollment.objects.filter(pk__in=[self.e2.pk, self.e0.pk]).update(status="dropped")
            day2 = self.today - datetime.timedelta(days=6)
            seminar2 = self._lesson_at(self.o2, day2, LessonKind.SEMINAR, T1150)
            LessonMark.objects.create(
                organization=self.org,
                lesson=seminar2,
                enrollment=Enrollment.objects.get(offering=self.o2, student=self.s4),
                status="present",
            )
        plan = ({**merge.PLAN[0], "no_seminar_groups": True},)
        with mock.patch.object(merge, "PLAN", plan):
            counts = self._call("--apply")
        self.assertEqual(counts.get("families_merged"), "1", counts)
        self.assertNotIn("seminar_groups_created", counts)
        with bypass_rls():
            self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
            self.assertFalse(Lesson.objects.filter(offering=self.offering, seminar_group__isnull=False).exists())

    def test_source_shares_retired_only_when_teacher_has_target_access(self):
        from apps.registrar.models import JournalShare

        with bypass_rls():
            CourseOffering.objects.filter(pk__in=[self.o1.pk, self.o2.pk, self.offering.pk]).update(
                instructor=self.teacher
            )
            other = User.objects.create_user("sgm_sh", "sgm_sh@x.test", "pw")
            self._member(other, "teacher", ["grade.input"])
            share = JournalShare.objects.create(
                organization=self.org, offering=self.o1, teacher=other, kinds=["seminar"], source="workload"
            )
        self.assertEqual(self._call("--apply"), {"source_has_shares": "1"})
        plan = ({**merge.PLAN[0], "retire_source_shares": True},)
        with mock.patch.object(merge, "PLAN", plan):
            self.assertEqual(self._call("--apply"), {"source_has_shares": "1"})  # ana jurnalda girişi yoxdur
            with bypass_rls():
                JournalShare.objects.create(
                    organization=self.org, offering=self.offering, teacher=other, kinds=["seminar"], source="workload"
                )
            counts = self._call("--apply")
            self.assertEqual(counts.get("source_shares_retired"), "1", counts)
            with bypass_rls():
                self.assertFalse(JournalShare.objects.get(pk=share.pk).is_active)
            self._call("--apply", "--undo")
        with bypass_rls():
            self.assertTrue(JournalShare.objects.get(pk=share.pk).is_active)

    def test_blocked_enrollment_is_reported_by_id(self):
        def boom(*args, **kwargs):
            raise merge.IntegrityError("x")

        with mock.patch.object(Enrollment.objects, "create", side_effect=boom):
            counts = self._call("--apply")
        self.assertEqual(counts["target_enrollment_blocked"], "1")
        self.assertRegex(counts["blocked_enrollment"], r"^[0-9a-f]{8}$")
        self.assertEqual(counts["blocked_rule"], "unknown")

    def test_different_teachers_block_family(self):
        with bypass_rls():
            other = User.objects.create_user("sgm_t2", "sgm_t2@x.test", "pw")
            self._member(other, "teacher", ["grade.input"])
            CourseOffering.objects.filter(pk=self.o2.pk).update(instructor=other)
            CourseOffering.objects.filter(pk=self.o1.pk).update(instructor=self.teacher)
        self.assertEqual(self._call("--apply"), {"family_instructors_differ": "1"})

    def test_undo_blocked_after_teacher_writes(self):
        self._call("--apply")
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org, offering=self.offering, date=self.today, kind=LessonKind.LECTURE, hours=2
            )
        self.assertEqual(self._call("--apply", "--undo"), {"undo_blocked_post_merge_data": "1"})
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.o1.pk).is_active)

    def test_subgroup_syllabus_is_shared_to_parent(self):
        from apps.syllabus.models import Syllabus, SyllabusShare

        with bypass_rls():
            CourseOffering.objects.filter(pk__in=[self.o1.pk, self.o2.pk, self.offering.pk]).update(
                instructor=self.teacher
            )
            Syllabus.objects.create(
                organization=self.org,
                subject=self.offering.subject,
                period=self.period,
                offering=self.o1,
                author=self.teacher,
            )
        self.assertEqual(self._call("--apply")["syllabus_shared"], "1")
        with bypass_rls():
            self.assertTrue(SyllabusShare.objects.filter(offering=self.offering).exists())
        self._call("--apply", "--undo")
        with bypass_rls():
            self.assertFalse(SyllabusShare.objects.filter(offering=self.offering).exists())

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - merge_subgroup_journals_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "merge_subgroup_journals_20261108" ]', text)
        self.assertIn("|subgroup_merge|", text)
