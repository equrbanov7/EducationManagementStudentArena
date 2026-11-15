"""Qiymətləndirilmiş nəticə tələbənin jurnalında / səhifəsində — audit + bərpa əmri (sahib 2026-11-16).

Bax ``apps/registrar/exam_result_gaps.py`` və ``apps/exams/management/commands/audit_exam_results_20261116.py``.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.exams.services import exam_journal_link
from apps.exams.tests.test_exam_journal_gaps_2026_10_27 import _GapSetup
from apps.organizations.models import OrgUnit
from apps.registrar import exam_result_gaps
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment
from core.constants import OrgUnitType
from core.rls import bypass_rls

COMMAND = "audit_exam_results_20261116"


class _AuditSetup(_GapSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            get_user_model().objects.filter(pk=self.owner.pk).update(is_superuser=True)

    def _run(self, *args):
        out = StringIO()
        call_command(COMMAND, "--org", self.org.slug, "--actor", self.owner.username, *args, stdout=out)
        return out.getvalue()

    def _exam_for(self, groups, *, title):
        exam, options = self._exam(title=title)
        with bypass_rls():
            exam.allowed_units.add(*groups)
            exam_journal_link.refresh_links(exam)
        return exam, options

    def _attempt_by(self, student, exam, options, *, correct=2):
        own = self.student
        self.student = student
        try:
            return self._finish(exam, options, correct=correct)
        finally:
            self.student = own

    def _family(self):
        """«536 MU» ana qrup + «536 MU1» alt qrup; fənnin jurnalı YALNIZ alt qrupdadır."""
        with bypass_rls():
            faculty = OrgUnit.objects.create(organization=self.org, name="Fak", slug="res-fak", unit_type="faculty")
            parent = OrgUnit.objects.create(
                organization=self.org, name="536 MU", slug="res-mu", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            sub = OrgUnit.objects.create(
                organization=self.org, name="536 MU1", slug="res-mu1", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=sub, instructor=self.teacher
            )
        return parent, sub, offering


class StatusCountTests(_AuditSetup):
    def test_score_present_is_unchanged_and_missing_cell_is_written_then_idempotent(self):
        exam, options = self._exam_for([self.group], title="Present")
        self._finish(exam, options, correct=3)
        out = self._run()
        self.assertIn("mode dry_run=1", out)
        self.assertIn("midterm_status unchanged=1", out)
        self.assertIn("midterm_visible=1", out)
        with bypass_rls():
            ComponentScore.objects.filter(enrollment=self.enrollment, exam_source__isnull=False).delete()
        self.assertIn("midterm_status written=1", self._run())
        self.assertIsNone(self._score_in(self.offering, self.enrollment))  # dry-run heç nə yazmadı
        self._run("--apply")
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("30"))
        self.assertIn("midterm_status unchanged=1", self._run())

    def test_output_has_no_personal_names(self):
        exam, options = self._exam_for([self.group], title="Names")
        self._finish(exam, options, correct=1)
        out = self._run()
        self.assertNotIn(self.student.username, out)
        for line in out.strip().splitlines():
            self.assertTrue(line.startswith("exam_results: "), line)

    def test_actor_must_be_superuser(self):
        with self.assertRaises(CommandError):
            call_command(COMMAND, "--org", self.org.slug, "--actor", self.teacher.username)


class ReasonTests(_AuditSetup):
    """Jurnalı olmayan tələbə: səbəb sayılır, əmr qeydiyyat YARATMIR (yerləşdirmə — ``takers`` addımı)."""

    def test_own_group_roster_gap_is_reported_and_nothing_is_enrolled(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).delete()
        exam, options = self._exam_for([self.group], title="Late")
        self._finish(exam, options, correct=2)
        out = self._run("--apply")
        self.assertIn("midterm_status no_enrollment=1", out)
        self.assertIn("midterm_no_enrollment_reason roster_gap=1", out)
        self.assertIn(f"gap kind=midterm exam={exam.pk} reason=roster_gap n=1", out)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.student).exists())

    def test_parent_group_student_with_single_subgroup_journal(self):
        parent, _sub, _offering = self._family()
        student = self._new_student("res_parent", parent)
        exam, options = self._exam_for([parent], title="Sub")
        self._attempt_by(student, exam, options, correct=1)
        self.assertIn("family_journal=1", self._run())

    def test_student_of_another_group_points_to_the_exam_groups_journal(self):
        """Sahib: «başqa qrupda tələbədirsə deməli o fəndə alt qrupdadır» — imtahan qrupunun TƏK jurnalı."""
        student = self._new_student("res_other", self.other_group)
        with bypass_rls():
            ctx = exam_result_gaps.context(self.org, self.period)
            gap = exam_result_gaps.classify_student(
                ctx, student_id=student.pk, subject_id=self.subject.pk, exam_group_ids=[self.group.pk]
            )
        self.assertEqual((gap.reason, gap.offering_id), (exam_result_gaps.OTHER_GROUP_JOURNAL, self.offering.pk))

    def test_two_subgroup_journals_are_ambiguous(self):
        parent, sub, _offering = self._family()
        with bypass_rls():
            sub2 = OrgUnit.objects.create(
                organization=self.org, name="536 MU2", slug="res-mu2", unit_type=OrgUnitType.GROUP, parent=sub.parent
            )
            CourseOffering.objects.create(organization=self.org, subject=self.subject, period=self.period, group=sub2)
        student = self._new_student("res_ambig", parent)
        exam, options = self._exam_for([parent], title="Ambig")
        self._attempt_by(student, exam, options)
        self.assertIn("family_ambiguous=1", self._run())

    def test_dropped_row_is_reported_not_restored(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
        exam, options = self._exam_for([self.group], title="Drop")
        self._finish(exam, options, correct=2)
        out = self._run("--apply")
        self.assertIn("dropped=1", out)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, "dropped")


class EnrollmentHookTests(_AuditSetup):
    """Kök səbəb: tələbə imtahandan SONRA jurnala düşəndə bal da o jurnala gəlir (``enrollment_result_sync``)."""

    def test_late_enrollment_pulls_the_finished_midterm_into_the_journal(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).delete()
        exam, options = self._exam_for([self.group], title="Hook")
        self._finish(exam, options, correct=2)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            enrollment = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.offering)
        self.assertEqual(self._score_in(self.offering, enrollment).score, Decimal("20"))

    def test_reactivated_row_pulls_the_score_and_unrelated_saves_are_silent(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
        exam, options = self._exam_for([self.group], title="Hook2")
        self._finish(exam, options, correct=3)
        self.assertIsNone(self._score_in(self.offering, self.enrollment))
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True) as callbacks:
            row = Enrollment.objects.get(pk=self.enrollment.pk)
            row.absence_hours = 2
            row.save(update_fields=["absence_hours"])
        self.assertEqual(len(callbacks), 0)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            row.status = "enrolled"
            row.save(update_fields=["status", "updated_at"])
        self.assertEqual(self._score_in(self.offering, row).score, Decimal("30"))

    def test_bulk_group_enrollment_also_pulls_the_score(self):
        from apps.registrar import services

        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).delete()
        exam, options = self._exam_for([self.group], title="Hook3")
        self._finish(exam, options, correct=1)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            report = services.enroll_group_students(offerings=[self.offering])
        self.assertGreaterEqual(report["created"], 1)
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=self.offering, student=self.student)
        self.assertEqual(self._score_in(self.offering, enrollment).score, Decimal("10"))


class ClassifyStudentTests(_AuditSetup):
    def test_duplicate_account_with_the_journal_is_left_to_the_merge(self):
        twin = self._new_student("res_dup", self.other_group)
        with bypass_rls():
            get_user_model().objects.filter(pk=twin.pk).update(
                first_name=self.student.first_name or "Ad", last_name=self.student.last_name or "Soyad"
            )
            get_user_model().objects.filter(pk=self.student.pk).update(
                first_name=self.student.first_name or "Ad", last_name=self.student.last_name or "Soyad"
            )
            ctx = exam_result_gaps.context(self.org, self.period)
            gap = exam_result_gaps.classify_student(ctx, student_id=twin.pk, subject_id=self.subject.pk)
        self.assertEqual(gap.reason, exam_result_gaps.DUPLICATE_ACCOUNT)
        self.assertIsNone(gap.offering_id)
