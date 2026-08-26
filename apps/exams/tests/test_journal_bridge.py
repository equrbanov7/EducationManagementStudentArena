"""İmtahan mərkəzi → elektron jurnal körpüsünün UCDAN-UCA testləri (2026-08 auditi).

Bu fayl körpünün REAL çağırış zəncirini yoxlayır (servis funksiyasının özünü
yox): tələbə imtahanı bitirir / müəllim yazılını yoxlayır → ``FinalGrade``
yaranır, düzgün bal yazılır və audit izində AKTOR tələbə OLMUR.

Xarakterizasiya testləri (auditin G7/G8/G9 tapıntıları):
* ``test_student_submission_creates_final_grade`` — G9,
* ``test_manual_grading_ui_path_reaches_journal`` — G8,
* ``test_entered_by_is_never_the_student`` — G7.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    FinalGrade,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _JournalBridgeSetup(TestCase):
    """Jurnala bağlı (subject FK-lı) imtahan + real qeydiyyat quraşdırması."""

    def setUp(self):
        self.owner = User.objects.create_user("jb_owner", "jb_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("jb_teacher", "jb_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("jb_student", "jb_student@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="JB Univ",
                slug="jb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="JBG1", slug="jb-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            for user, role_name in ((self.teacher, "teacher"), (self.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
            Membership.objects.create(
                user=self.owner, organization=self.org, role=self.org.roles.get(name="rector"), is_active=True
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=self.record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.lesson_hours = 60
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()

    # -- imtahan qurucuları ------------------------------------------------
    def _test_exam(self):
        exam = Exam.objects.create(
            title="JB Test",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="test",
            is_active=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
        correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
        ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
        return exam, question, correct

    def _written_exam(self, points=10):
        exam = Exam.objects.create(
            title="JB Written",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="written",
            is_active=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Esse", points=points)
        return exam, question

    def _correct_test_attempt(self):
        exam, question, correct = self._test_exam()
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_options.add(correct)
        return attempt

    def _final_grade(self):
        with bypass_rls():
            return FinalGrade.objects.filter(enrollment=self.enrollment).first()


class StudentSubmissionBridgeTests(_JournalBridgeSetup):
    """G9 — tələbənin NORMAL təhvili (``mark_finished``) jurnala düşməlidir."""

    def test_student_submission_creates_final_grade(self):
        attempt = self._correct_test_attempt()

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade, "Tələbənin təhvili jurnala çatmadı (FinalGrade yaranmadı).")
        # 100% × 50 (exam_score_max) = 50.
        self.assertEqual(final_grade.exam_score, Decimal("50"))

    def test_expired_attempt_also_reaches_journal(self):
        attempt = self._correct_test_attempt()

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="expired")

        self.assertIsNotNone(self._final_grade())

    def test_repeat_sync_is_idempotent(self):
        from apps.exams.services.journal_sync import sync_attempt_to_journal

        attempt = self._correct_test_attempt()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        with bypass_rls():
            sync_attempt_to_journal(attempt)
            sync_attempt_to_journal(attempt)
            self.assertEqual(FinalGrade.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_written_attempt_waits_for_grading(self):
        """Yazılı imtahan bitəndə hələ bal yoxdur — jurnal yazısı GÖZLƏYİR."""
        exam, _question = self._written_exam()
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        self.assertIsNone(self._final_grade())

    def test_trial_run_stays_out_of_journal(self):
        """Müəllimin "Sınaq keç" cəhdi rəsmi qiymətə toxunmur (reqressiya)."""
        attempt = self._correct_test_attempt()
        attempt.is_trial = True
        attempt.save(update_fields=["is_trial"])

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        self.assertIsNone(self._final_grade())

    def test_unlinked_exam_stays_out_of_journal(self):
        """Jurnal fənninə bağlı olmayan imtahan körpünü işə salmır (reqressiya)."""
        exam = Exam.objects.create(
            title="Sərbəst quiz",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q", points=1)
        correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_options.add(correct)

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        self.assertIsNone(self._final_grade())


class JournalActorTests(_JournalBridgeSetup):
    """G7 — jurnal yazısının aktoru HEÇ VAXT imtahan verən tələbə olmamalıdır."""

    def test_entered_by_is_never_the_student(self):
        attempt = self._correct_test_attempt()

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade)
        self.assertNotEqual(
            final_grade.entered_by_id,
            self.student.id,
            "İmtahan qiyməti tələbənin öz adına yazılıb (entered_by == tələbə).",
        )
        # Avtomatik qiymətləndirmə → aktor SİSTEMdir (NULL), müəllim deyil.
        self.assertIsNone(final_grade.entered_by_id)

    def test_audit_trail_actor_is_not_the_student(self):
        from django.apps import apps as django_apps

        attempt = self._correct_test_attempt()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        AuditLog = django_apps.get_model("audit", "AuditLog")
        with bypass_rls():
            rows = list(AuditLog.objects.filter(resource_type="registrar.grade.final"))
        self.assertTrue(rows, "İmtahan nəticəsi üçün audit izi yazılmadı.")
        for row in rows:
            self.assertNotEqual(row.user_id, self.student.id)
        # Avtomatik yazı auditdə "avtomatik" kimi görünməlidir.
        self.assertTrue(any("avtomatik" in str(change.get("item", "")) for change in (rows[0].changes or [])))

    def test_expelled_student_gets_zero_without_student_actor(self):
        attempt = self._correct_test_attempt()
        attempt.supervision_status = "removed"
        attempt.save(update_fields=["supervision_status"])

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade)
        self.assertEqual(final_grade.exam_score, Decimal("0"))
        self.assertNotEqual(final_grade.entered_by_id, self.student.id)


class ManualGradingBridgeTests(_JournalBridgeSetup):
    """G8 — müəllimin əsas yoxlama UI axını (``apply_manual_grading``) jurnala çatmalıdır."""

    def _graded_written_attempt(self, score="8"):
        from apps.exams.services.manual_grading import apply_manual_grading

        exam, question = self._written_exam(points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="cavab")
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(
                attempt_id=attempt.id,
                grader=self.teacher,
                payload={f"score_{question.id}": score},
            )
        return attempt

    def test_manual_grading_ui_path_reaches_journal(self):
        self._graded_written_attempt(score="8")

        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade, "Müəllimin verdiyi bal jurnala sync olmadı.")
        # 8/10 = 80% → 80% × 50 = 40.
        self.assertEqual(final_grade.exam_score, Decimal("40"))

    def test_manual_grading_actor_is_the_grading_teacher(self):
        self._graded_written_attempt(score="8")

        final_grade = self._final_grade()
        self.assertEqual(final_grade.entered_by_id, self.teacher.id)

    def test_regrading_updates_the_same_final_grade(self):
        from apps.exams.services.manual_grading import apply_manual_grading

        attempt = self._graded_written_attempt(score="8")
        question = attempt.exam.questions.get()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(
                attempt_id=attempt.id,
                grader=self.teacher,
                payload={f"score_{question.id}": "10"},
            )

        with bypass_rls():
            grades = list(FinalGrade.objects.filter(enrollment=self.enrollment))
        self.assertEqual(len(grades), 1)
        self.assertEqual(grades[0].exam_score, Decimal("50"))

    def test_percent_uses_the_delivered_question_set_not_the_whole_bank(self):
        """Randomizer bankın alt-dəstini çatdırır → məxrəc ÇATDIRILAN dəstdir."""
        from apps.exams.services.manual_grading import apply_manual_grading

        exam = Exam.objects.create(
            title="JB Bank",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="written",
            is_active=True,
            random_question_count=1,
        )
        delivered = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=10)
        ExamQuestion.objects.create(exam=exam, order=2, text="Q2 (çatdırılmayıb)", points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        ExamAnswer.objects.create(attempt=attempt, question=delivered, text_answer="cavab")

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(
                attempt_id=attempt.id,
                grader=self.teacher,
                payload={f"score_{delivered.id}": "10"},
            )

        # 10/10 = 100% → 50 (bank üzrə hesablansaydı 10/20 = 50% → 25 olardı).
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))

    def test_single_answer_grading_still_reaches_journal(self):
        """Reqressiya: köhnə (tək cavab) yoxlama yolu da işləməyə davam edir."""
        from apps.exams.services.manual_grading import apply_single_answer_grade

        exam, question = self._written_exam(points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="cavab")
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_single_answer_grade(answer_id=answer.id, score=5, grader=self.teacher)

        final_grade = self._final_grade()
        self.assertIsNotNone(final_grade)
        self.assertEqual(final_grade.exam_score, Decimal("25"))
        self.assertEqual(final_grade.entered_by_id, self.teacher.id)


class LockedJournalTests(_JournalBridgeSetup):
    """Kilidli jurnal: körpü SƏSSİZCƏ yazmır (rəsmiləşmiş nəticə qorunur)."""

    def test_published_journal_is_not_overwritten(self):
        from apps.registrar import gradebook

        attempt = self._correct_test_attempt()
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            scheme.approval_status = "approved"
            scheme.is_published = True
            scheme.save(update_fields=["approval_status", "is_published"])

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")

        self.assertIsNone(self._final_grade())
