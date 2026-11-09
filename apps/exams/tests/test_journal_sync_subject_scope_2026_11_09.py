"""R06: stale explicit journal links cannot override the exam's subject identity."""

from decimal import Decimal

from apps.exams.services.journal_sync_scope import target_identity
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.registrar import exam_bridge
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, FinalGrade, Subject
from core.rls import bypass_rls


class StaleJournalSubjectTests(_MidtermSetup):
    def wrong_subject_offering(self):
        with bypass_rls():
            subject = Subject.objects.create(organization=self.org, code="OTHER-SCOPE", name="Other subject")
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                group=self.group,
                period=self.period,
                instructor=self.teacher,
            )
            enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=self.student)
        return offering, enrollment

    def test_wrong_subject_link_uses_correct_subject_fallback_for_final_and_target_key(self):
        wrong, wrong_enrollment = self.wrong_subject_offering()
        exam, options = self._exam(category="final")
        with bypass_rls():
            exam.journal_offerings.add(wrong)
        attempt = self._finish(exam, options, correct=3)
        with bypass_rls():
            self.assertEqual(target_identity(attempt), ("enrollment", self.enrollment.pk))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("50"))
            self.assertFalse(FinalGrade.objects.filter(enrollment=wrong_enrollment).exists())

    def test_wrong_subject_link_never_writes_midterm_to_other_subject(self):
        wrong, wrong_enrollment = self.wrong_subject_offering()
        exam, options = self._exam(category="midterm")
        with bypass_rls():
            exam.journal_offerings.add(wrong)
        attempt = self._finish(exam, options, correct=3)
        with bypass_rls():
            self.assertEqual(target_identity(attempt), ("enrollment", self.enrollment.pk))
            self.assertEqual(ComponentScore.objects.get(enrollment=self.enrollment).score, Decimal("30"))
            self.assertFalse(ComponentScore.objects.filter(enrollment=wrong_enrollment).exists())

    def test_stale_link_without_correct_subject_enrollment_returns_no_target(self):
        wrong, _ = self.wrong_subject_offering()
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status="dropped")
            self.assertIsNone(
                exam_bridge.resolve_enrollment(
                    student=self.student,
                    subject_id=self.subject.pk,
                    organization=self.org,
                    offering_ids=[wrong.pk],
                )
            )
            self.assertIsNone(
                exam_bridge.resolve_exam_result_target(
                    student=self.student,
                    subject_id=self.subject.pk,
                    organization=self.org,
                    offering_ids=[wrong.pk],
                )
            )

    def test_exam_subject_change_does_not_reuse_the_old_subject_journal(self):
        with bypass_rls():
            exam, _ = self._exam(category="final")
            exam.journal_offerings.add(self.offering)
            other = Subject.objects.create(organization=self.org, code="REPAIRED", name="Repaired subject")
            exam.subject = other
            exam.save(update_fields=["subject"])
            self.assertIsNone(
                exam_bridge.resolve_enrollment(
                    student=self.student,
                    subject_id=other.pk,
                    organization=self.org,
                    offering_ids=[self.offering.pk],
                )
            )

    def test_language_final_keeps_current_main_seventy_point_scale_and_summary(self):
        with bypass_rls():
            self.subject.name = "Xarici dil-1 (Elementary)"
            self.subject.save(update_fields=["name"])
        exam, options = self._exam(category="final")
        self._finish(exam, options, correct=3)
        with bypass_rls():
            summary = exam_bridge.exam_result_summary(
                student=self.student, subject_id=self.subject.pk, organization=self.org
            )
            self.assertEqual(summary["exam_score_max"], 70)
            self.assertEqual(summary["exam_score"], Decimal("70"))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal("70"))
