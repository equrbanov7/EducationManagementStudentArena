"""Sahib 2026-11-11 səhər, 2-ci dövrə: «birləşdirərsən onları … dublikat qalmamış olsun».

Tədris planında ikisi də olan kartlar birləşmir; adı fərqli (yoxlanmış) cüt birləşir; kredit fərqində qiymətlənmiş kart
saxlanılır, planın öz krediti dəyişmir; saxlanılan kartın adı düzəlir və geri qaytarılır; keçmiş dövrün boş qabığı passiv
olur; tələbənin eyni fəndən iki jurnalı bir karta enir (öz qrupu qalır, xanalar köçür, heç biri silinmir).
"""

import datetime
import io
import json
import pathlib
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar import duplicate_subjects_2026_11_11 as duplicates
from apps.registrar.models import (
    CourseOffering,
    CurriculumSubject,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
    Subject,
)
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
D1, D2, D3 = datetime.date(2026, 10, 5), datetime.date(2026, 10, 8), datetime.date(2026, 10, 12)
T1 = datetime.time(10, 10)


class RoundTwoTest(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.typo = Subject.objects.create(organization=self.org, code="QKU-77", name="Proqramlasdirmanin esaslari")
            self.source = CourseOffering.objects.create(
                organization=self.org, subject=self.typo, group=self.group, period=self.period, instructor=self.teacher
            )
            self.w1 = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.source)
            self._mark(self._lesson(self.source, D1, LessonKind.LECTURE), self.w1, "absent")
        self.plan = {
            "format": duplicates.FORMAT,
            "auto_catalogue": False,
            "groups": [
                {
                    "name": "typo",
                    "keeper": str(self.subject.pk),
                    "sources": [str(self.typo.pk)],
                    "reviewed": True,
                    "keeper_name": "Proqramlaşdırma (əsaslar)",
                    "pairs": [{"source": str(self.source.pk), "target": str(self.offering.pk)}],
                }
            ],
            "doubles": [],
        }
        patch = mock.patch.object(duplicates, "PLAN", self.plan)
        patch.start()
        self.addCleanup(patch.stop)

    # ── qurucular ─────────────────────────────────────────────────────────
    def _lesson(self, offering, day, kind):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day, kind=kind, hours=2, start_time=T1
        )

    def _mark(self, lesson, enrollment, status, score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )

    def _student(self, username, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=self.org, role=self.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program,
            curriculum=self.curriculum,
            group=group,
            admission_year=2024,
        )
        return user

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "merge_duplicate_subjects_20261111",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts, batch = {}, ""
        self.lines = out.getvalue().splitlines()
        for line in self.lines:
            self.assertRegex(line, r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if line.startswith(("twin_merge: pair=", "twin_merge: group=", "twin_merge: double=")):
                continue
            for item in line.split()[1:]:
                key, value = item.split("=")
                if key == "batch":
                    batch = value
                else:
                    counts[key] = value
        return counts, batch

    # ── tədris planı qoruyucusu ───────────────────────────────────────────
    def test_both_subjects_in_one_curriculum_are_never_merged(self):
        with bypass_rls():
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.typo, semester_number=2
            )
        counts, _ = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pair_curriculum_both"], "1")
        counts, _ = self._call("--only", "catalogue", "--apply")
        self.assertEqual(counts["catalogue_refused_curriculum_both"], "1")
        self.assertIn("twin_merge: group=typo catalogue=refused_curriculum_both", self.lines)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)

    # ── yoxlanmış ad fərqi + ad düzəlişi + kredit ─────────────────────────
    def test_reviewed_typo_pair_merges_keeper_is_renamed_and_undo_restores_the_name(self):
        counts, journals = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pairs_merged"], "1")
        counts, catalogue = self._call("--only", "catalogue", "--apply")
        self.assertEqual((counts["catalogue_groups_merged"], counts["catalogue_keeper_renamed"]), ("1", "1"))
        self.assertIn("twin_merge: group=typo catalogue=merged archived=1", self.lines)
        with bypass_rls():
            self.assertEqual(Subject.objects.get(pk=self.subject.pk).name, "Proqramlaşdırma (əsaslar)")
            self.assertTrue(Subject.objects.get(pk=self.typo.pk).is_archived)
            receipt = duplicates._model("AuditLog", "audit").objects.get(
                resource_type=duplicates.RESOURCE, resource_id=catalogue, changes__kind=duplicates.KIND
            )
            self.assertEqual(receipt.changes["renames"][0]["old"], "Proqramlaşdırma")
            self.assertEqual(receipt.changes["catalogue_groups"][0]["sources"][0]["ects"], self.typo.ects)
        self._call("--undo", "--batch", catalogue, "--apply")
        self._call("--undo", "--batch", journals, "--apply")
        with bypass_rls():
            self.assertEqual(Subject.objects.get(pk=self.subject.pk).name, "Proqramlaşdırma")
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)

    def test_credit_difference_keeps_graded_side_and_plan_row_credit(self):
        """Kredit fərqi: qiymətlənmiş kart saxlanılır; qiymətsiz kartın plan sətri öz krediti ilə köçür."""
        with bypass_rls():
            Subject.objects.filter(pk=self.typo.pk).update(ects=7)
            row = CurriculumSubject.objects.get(curriculum=self.curriculum, subject=self.subject)
            other_curriculum = type(self.curriculum).objects.create(
                organization=self.org, program=self.program, admission_year=2025
            )
            plan_row = CurriculumSubject.objects.create(
                organization=self.org, curriculum=other_curriculum, subject=self.typo, semester_number=1, credits=7
            )
            CourseOffering.objects.filter(pk=self.source.pk).delete()  # jurnal tərəfi bu testdə yoxdur
            self.plan["groups"][0]["pairs"] = []
        counts, _ = self._call("--only", "catalogue", "--apply")
        self.assertEqual(counts["catalogue_groups_merged"], "1")
        with bypass_rls():
            plan_row.refresh_from_db()
            self.assertEqual((plan_row.subject_id, plan_row.credits), (self.subject.pk, 7))  # planın krediti qalır
            self.assertEqual(Subject.objects.get(pk=self.subject.pk).ects, self.subject.ects)
            self.assertTrue(CurriculumSubject.objects.filter(pk=row.pk).exists())

    def test_credit_difference_with_graded_source_is_blocked(self):
        with bypass_rls():
            Subject.objects.filter(pk=self.typo.pk).update(ects=7)
            past = AcademicPeriod.objects.create(
                organization=self.org,
                name="Keçmiş",
                period_type=self.period.period_type,
                academic_year="2025/2026",
                start_date=datetime.date(2025, 9, 1),
                end_date=datetime.date(2026, 1, 31),
            )
            other = OrgUnit.objects.create(organization=self.org, name="R2X", slug="r2x", unit_type=OrgUnitType.GROUP)
            graded = CourseOffering.objects.create(organization=self.org, subject=self.typo, group=other, period=past)
            row = Enrollment.objects.create(organization=self.org, student=self.student, offering=graded)
            FinalGrade.objects.create(organization=self.org, enrollment=row, exam_score=Decimal("30"))
            CourseOffering.objects.filter(pk=self.source.pk).delete()
            self.plan["groups"][0]["pairs"] = []
        counts, _ = self._call("--only", "catalogue", "--apply")
        self.assertEqual(counts["catalogue_blocked_credit_mismatch"], "1")
        self.assertIn("twin_merge: group=typo catalogue=blocked reason=credit_mismatch", self.lines)
        with bypass_rls():
            self.assertFalse(Subject.objects.get(pk=self.typo.pk).is_archived)

    # ── keçmiş dövrün boş qabığı ──────────────────────────────────────────
    def test_past_period_empty_shell_is_retired_and_data_journal_untouched(self):
        with bypass_rls():
            past = AcademicPeriod.objects.create(
                organization=self.org,
                name="Keçmiş",
                period_type=self.period.period_type,
                academic_year="2025/2026",
                start_date=datetime.date(2025, 9, 1),
                end_date=datetime.date(2026, 1, 31),
            )
            shell = CourseOffering.objects.create(
                organization=self.org, subject=self.typo, group=self.group, period=past
            )
            kept = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, group=self.group, period=past
            )
            row = Enrollment.objects.create(organization=self.org, student=self.student, offering=kept)
            self._mark(self._lesson(kept, datetime.date(2025, 10, 1), LessonKind.LECTURE), row, "present")
            # keçmiş dövrdə HƏR İKİ tərəfi datalı qutu — toxunulmur
            other = OrgUnit.objects.create(organization=self.org, name="R2Y", slug="r2y", unit_type=OrgUnitType.GROUP)
            busy = [
                CourseOffering.objects.create(organization=self.org, subject=subject, group=other, period=past)
                for subject in (self.subject, self.typo)
            ]
            for offering in busy:
                Lesson.objects.create(
                    organization=self.org, offering=offering, date=datetime.date(2025, 10, 2), kind="lecture", hours=2
                )
        counts, _ = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pairs_merged"], "2")  # cari cüt + keçmiş boş qabıq
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=shell.pk).is_active)
            self.assertTrue(CourseOffering.objects.get(pk=kept.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=kept).count(), 1)
            self.assertEqual(CourseOffering.objects.filter(pk__in=[o.pk for o in busy], is_active=True).count(), 2)

    # ── tələbənin eyni fəndən iki jurnalı ─────────────────────────────────
    def _double(self):
        """Tələbə öz qrupunun (JBG1) jurnalında + qonaq kimi R2G jurnalında — fənn EYNİ."""
        other = OrgUnit.objects.create(organization=self.org, name="R2G", slug="r2g", unit_type=OrgUnitType.GROUP)
        guest = CourseOffering.objects.create(
            organization=self.org, subject=self.subject, group=other, period=self.period
        )
        row = Enrollment.objects.create(
            organization=self.org, student=self.student, offering=guest, source_group=self.group
        )
        own_lesson = self._lesson(self.offering, D2, LessonKind.SEMINAR)
        self._mark(own_lesson, self.enrollment, "present")
        guest_lesson = self._lesson(guest, D2, LessonKind.SEMINAR)
        moved = self._mark(guest_lesson, row, "present", 8)
        self.plan["doubles"] = [{"name": "test-double", "offerings": [str(self.offering.pk), str(guest.pk)]}]
        return guest, row, own_lesson, moved

    def test_student_double_keeps_own_group_journal_and_moves_marks(self):
        with bypass_rls():
            guest, row, own_lesson, moved = self._double()
        counts, batch = self._call("--only", "doubles", "--apply")
        self.assertEqual(counts["double_enrollments_dropped"], "1")
        self.assertEqual(counts["double_marks_score_filled"], "1")
        self.assertNotIn("double_empty_journals_retired", counts)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "dropped")
            self.assertTrue(LessonMark.objects.filter(pk=moved.pk).exists())  # mənbə xanası silinmir
            self.assertEqual(LessonMark.objects.get(lesson=own_lesson, enrollment=self.enrollment).score, Decimal("8"))
            self.assertTrue(CourseOffering.objects.get(pk=guest.pk).is_active)  # dərsi var — passiv edilmir
        self._call("--undo", "--batch", batch, "--apply")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "enrolled")
            self.assertIsNone(LessonMark.objects.get(lesson=own_lesson, enrollment=self.enrollment).score)

    def test_student_double_with_unmatched_marks_or_without_own_journal_is_left_alone(self):
        with bypass_rls():
            guest, row, _own_lesson, _moved = self._double()
            self._mark(self._lesson(guest, D3, LessonKind.LECTURE), row, "present")  # öz jurnalında bu dərs yoxdur
        counts, _ = self._call("--only", "doubles", "--apply")
        self.assertEqual(counts["double_unmatched_marks"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "enrolled")
            third = OrgUnit.objects.create(organization=self.org, name="R2Z", slug="r2z", unit_type=OrgUnitType.GROUP)
            stranger = self._student("r2_stranger", third)  # heç biri öz qrupu deyil, ikisində də data var
            for offering in (self.offering, guest):
                extra = Enrollment.objects.create(
                    organization=self.org, student=stranger, offering=offering, source_group=third
                )
                self._mark(Lesson.objects.filter(offering=offering, date=D2).first(), extra, "present")
        counts, _ = self._call("--only", "doubles", "--apply")
        self.assertEqual((counts["double_unmatched_marks"], counts["double_keep_ambiguous"]), ("1", "1"))

    def test_empty_twin_journal_is_retired_after_its_students_are_released(self):
        with bypass_rls():
            other = OrgUnit.objects.create(
                organization=self.org, name="JBG1x", slug="jbg1x", unit_type=OrgUnitType.GROUP
            )
            empty = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, group=other, period=self.period
            )
            row = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=empty, source_group=other
            )
            self.plan["doubles"] = [{"name": "empty", "offerings": [str(empty.pk), str(self.offering.pk)]}]
        counts, _ = self._call("--only", "doubles", "--apply")
        self.assertEqual((counts["double_enrollments_dropped"], counts["double_empty_journals_retired"]), ("1", "1"))
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "dropped")
            self.assertFalse(CourseOffering.objects.get(pk=empty.pk).is_active)
            self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, "enrolled")

    def test_parent_and_subgroup_journals_are_not_treated_as_doubles(self):
        with bypass_rls():
            child = OrgUnit.objects.create(
                organization=self.org, name="JBG1-1", slug="jbg1-1", unit_type=OrgUnitType.GROUP, parent=self.group
            )
            sub = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, group=child, period=self.period
            )
            Enrollment.objects.create(organization=self.org, student=self.student, offering=sub)
            self.plan["doubles"] = [{"name": "family", "offerings": [str(self.offering.pk), str(sub.pk)]}]
        counts, _ = self._call("--only", "doubles", "--apply")
        self.assertEqual(counts["double_parent_subgroup"], "1")

    # ── plan faylı ────────────────────────────────────────────────────────
    def test_repo_plan_is_consistent(self):
        real = json.loads(pathlib.Path(duplicates.__file__).with_suffix(".json").read_text(encoding="utf-8"))
        grouped = {pk for group in real["groups"] for pk in (group["keeper"], *group["sources"])}
        refused = {pk for item in real["refused"] for pk in item["subjects"]}
        self.assertFalse(grouped & refused)  # rədd edilmiş kart heç bir qrupda deyil
        self.assertEqual(len(grouped), sum(1 + len(group["sources"]) for group in real["groups"]))  # kart təkrarlanmır
        self.assertIs(real["auto_catalogue"], False)
        for group in real["groups"]:
            self.assertTrue(group["name"] and group["keeper"] and group["sources"])
        for item in real["doubles"]:
            self.assertEqual(len(set(item["offerings"])), 2)
