"""Sahib 2026-11-08: ana/alt qrup ailələri — dərslər eynidirsə birləşir, birləşmə dərsi pozarsa ana jurnal yığışdırılır.

Ailələr ``OrgUnit.parent`` üzrə tapılır; ana jurnalın qeydləri alt qrup jurnallarına YALNIZ boş xanaya kopyalanır, ana
jurnal passiv olur (silinmir); ``--undo`` qaytarır; stdout-da yalnız saylar.
"""

import datetime
import io
from unittest import mock

from django.core.management import call_command

from apps.organizations.models import OrgUnit
from apps.registrar import subgroup_family_resolve_2026_11_08 as resolve
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, LessonMark, StudentAcademicRecord
from apps.registrar.tests import test_subgroup_journal_merge_2026_11_08 as merge_tests
from apps.registrar.tests.test_lab_groups_2026_11_06 import User
from core.rls import bypass_rls

T0830 = datetime.time(8, 30)


class SubgroupFamilyResolveTest(merge_tests.SubgroupJournalMergeTest):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            OrgUnit.objects.filter(pk__in=[self.k1.pk, self.k2.pk]).update(parent=self.group)
        patch = mock.patch.object(resolve, "PLAN", ())
        patch.start()
        self.addCleanup(patch.stop)

    def _resolve(self, *extra):
        out = io.StringIO()
        call_command(
            "resolve_subgroup_families_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^subgroup_resolve: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line and "family=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("subgroup_resolve: ") :].split())
        return counts

    def _separate_classes(self):
        """Ana jurnal = alt qrupların cəmi; alt qrupların müəllimi fərqlidir (birləşmə mümkün deyil)."""
        with bypass_rls():
            other = User.objects.create_user("sgr_t2", "sgr_t2@x.test", "pw")
            self._member(other, "teacher", ["grade.input"])
            CourseOffering.objects.filter(pk=self.o2.pk).update(instructor=other)
            CourseOffering.objects.filter(pk=self.o1.pk).update(instructor=self.teacher)
            Enrollment.objects.filter(offering=self.offering).update(lab_group=None)
            program = StudentAcademicRecord.objects.filter(student=self.s3).first()
            for student, unit in ((self.students[1], self.k2), (self.students[2], self.k1)):
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    program=program.program,
                    curriculum=program.curriculum,
                    group=unit,
                    admission_year=2026,
                )
            lecture1 = Lesson.objects.get(offering=self.o1, kind=LessonKind.LECTURE)
            seminar1 = Lesson.objects.get(offering=self.o1, kind=LessonKind.SEMINAR)
            lecture2 = Lesson.objects.get(offering=self.o2, kind=LessonKind.LECTURE)
            o1_e2 = Enrollment.objects.create(organization=self.org, student=self.students[2], offering=self.o1)
            o2_e1 = Enrollment.objects.create(organization=self.org, student=self.students[1], offering=self.o2)
            for lesson, enrollment in ((lecture1, o1_e2), (seminar1, o1_e2), (lecture2, o2_e1)):
                LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status="present")
            extra = [
                Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
                for student in (self.s3, self.s4)
            ]
            day3 = self.today - datetime.timedelta(days=3)
            only_parent = self._lesson_at(self.offering, day3, LessonKind.LECTURE, T0830)
            for enrollment in (self.e1, self.e2, self.e0, *extra):
                LessonMark.objects.create(
                    organization=self.org, lesson=only_parent, enrollment=enrollment, status="present"
                )
            for enrollment in (self.e2, self.e0, *extra):
                LessonMark.objects.create(
                    organization=self.org, lesson=self.parent_lecture, enrollment=enrollment, status="present"
                )

    def test_same_lessons_merge_into_parent(self):
        counts = self._resolve("--apply")
        self.assertEqual(counts["families_found"], "1")
        self.assertEqual(counts["families_merged"], "1")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.o1.pk).is_active)
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)

    def test_separate_classes_retire_parent_and_undo(self):
        self._separate_classes()
        with bypass_rls():
            before = LessonMark.objects.filter(lesson__offering=self.offering).count()
        counts = self._resolve()
        self.assertEqual(counts["parents_retired"], "1", counts)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)  # dry-run
        counts = self._resolve("--apply")
        self.assertEqual(counts["family_instructors_differ"], "1")
        self.assertEqual(counts["lessons_created"], "2")  # yalnız anada olan 08:30 mühazirəsi → iki alt qrupa
        self.assertEqual(counts["marks_copied"], "5")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), before)  # silinmir
            self.assertEqual(
                LessonMark.objects.filter(lesson__offering__in=[self.o1, self.o2], lesson__start_time=T0830).count(), 5
            )
        self.assertEqual(self._resolve("--apply", "--undo")["parents_restored"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertFalse(Lesson.objects.filter(offering__in=[self.o1, self.o2], start_time=T0830).exists())
            self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 5)

    def test_unplaced_parent_student_blocks_split(self):
        self._separate_classes()
        with bypass_rls():
            StudentAcademicRecord.objects.filter(student=self.students[1]).delete()
            Enrollment.objects.filter(offering=self.o2, student=self.students[1]).delete()
        counts = self._resolve("--apply")
        self.assertEqual(counts["parent_student_unplaced"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
