"""Qəbul olunmuş apellyasiya → rəsmi qiymət zənciri (2026-08 auditi, G10).

Apellyasiya bal düzəlişi yalnız ``ScoreAdjustment``-da qalmamalıdır: qərar
imtahan ledger-inə (``ExamGradeEvent``) və elektron jurnala (``FinalGrade``)
çatmalıdır; revert isə audit izi qoymalıdır.
"""

from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal, AppealItem
from apps.appeals.services import accept_appeal_item, reject_appeal_item
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamGradeEvent, ExamQuestion, ExamQuestionOption
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


class _AppealJournalSetup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("ap_owner", "ap_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("ap_teacher", "ap_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("ap_student", "ap_student@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="AP Univ",
                slug="ap-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="APG1", slug="ap-g1", unit_type=OrgUnitType.GROUP
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

    def _final_grade(self):
        with bypass_rls():
            return FinalGrade.objects.filter(enrollment=self.enrollment).first()

    def _appeal_item(self, attempt, question, answer):
        appeal = Appeal.objects.create(attempt=attempt, exam=attempt.exam, student=self.student, organization=self.org)
        return AppealItem.objects.create(
            appeal=appeal,
            question=question,
            answer=answer,
            appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY,
            comment="x" * 30,
        )

    def _submitted_test_attempt(self):
        """2 suallı test; tələbə 1-ini düz edir → 50%."""
        exam = Exam.objects.create(
            title="AP Test",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="test",
            is_active=True,
        )
        questions = []
        for order in (1, 2):
            question = ExamQuestion.objects.create(exam=exam, order=order, text=f"Q{order}", points=1)
            correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
            ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
            questions.append((question, correct))
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        answers = []
        for index, (question, correct) in enumerate(questions):
            answer = ExamAnswer.objects.create(attempt=attempt, question=question)
            if index == 0:
                answer.selected_options.add(correct)
            answers.append(answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        return attempt, questions[1][0], answers[1]


class AcceptedAppealReachesJournalTests(_AppealJournalSetup):
    def test_accepted_appeal_updates_the_official_grade(self):
        attempt, question, answer = self._submitted_test_attempt()
        self.assertEqual(self._final_grade().exam_score, Decimal("25"))  # 50% × 50

        item = self._appeal_item(attempt, question, answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        final_grade = self._final_grade()
        self.assertEqual(final_grade.exam_score, Decimal("50"), "Qəbul olunan apellyasiya rəsmi qiymətə çatmadı.")
        self.assertEqual(final_grade.entered_by_id, self.teacher.id)

    def test_accepted_appeal_writes_a_grade_ledger_event(self):
        attempt, question, answer = self._submitted_test_attempt()
        item = self._appeal_item(attempt, question, answer)

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        events = list(ExamGradeEvent.objects.filter(attempt=attempt))
        self.assertEqual(len(events), 1, "Apellyasiya qərarı üçün ExamGradeEvent yazılmadı.")
        self.assertEqual(events[0].grader_id, self.teacher.id)
        self.assertEqual(events[0].question_id, question.id)
        self.assertEqual(events[0].old_score, 0)
        self.assertEqual(events[0].new_score, 1)

    def test_second_accept_is_idempotent(self):
        attempt, question, answer = self._submitted_test_attempt()
        item = self._appeal_item(attempt, question, answer)

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Təkrar")

        with bypass_rls():
            self.assertEqual(FinalGrade.objects.filter(enrollment=self.enrollment).count(), 1)
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))
        # İkinci qəbul yeni bal dəyişikliyi deyil → yeni ledger sətri yaranmır.
        self.assertEqual(ExamGradeEvent.objects.filter(attempt=attempt).count(), 1)

    def test_written_appeal_reaches_journal(self):
        exam = Exam.objects.create(
            title="AP Written",
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type="written",
            is_active=True,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Esse", points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="cavab")
        from apps.exams.services.manual_grading import apply_manual_grading

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(attempt_id=attempt.id, grader=self.teacher, payload={f"score_{question.id}": "5"})
        self.assertEqual(self._final_grade().exam_score, Decimal("25"))  # 50% × 50

        item = self._appeal_item(attempt, question, answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Yenidən baxıldı")

        # 6/10 = 60% → 30.
        self.assertEqual(self._final_grade().exam_score, Decimal("30"))


class RevertedAppealTests(_AppealJournalSetup):
    def test_reject_after_accept_restores_the_official_grade(self):
        attempt, question, answer = self._submitted_test_attempt()
        item = self._appeal_item(attempt, question, answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            reject_appeal_item(item, reviewer=self.teacher, response_text="Səhv qərar idi")

        self.assertEqual(self._final_grade().exam_score, Decimal("25"))

    def test_revert_is_audited(self):
        attempt, question, answer = self._submitted_test_attempt()
        item = self._appeal_item(attempt, question, answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        AuditLog = django_apps.get_model("audit", "AuditLog")
        with bypass_rls():
            before = AuditLog.objects.filter(resource_type="appeals.score_adjustment.revert").count()

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            reject_appeal_item(item, reviewer=self.teacher, response_text="Səhv qərar idi")

        with bypass_rls():
            rows = list(AuditLog.objects.filter(resource_type="appeals.score_adjustment.revert"))
        self.assertEqual(len(rows), before + 1, "Apellyasiya balının geri alınması auditsiz qaldı.")
        self.assertEqual(rows[-1].user_id, self.teacher.id)

    def test_revert_writes_a_reverse_ledger_event(self):
        attempt, question, answer = self._submitted_test_attempt()
        item = self._appeal_item(attempt, question, answer)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            reject_appeal_item(item, reviewer=self.teacher, response_text="Səhv qərar idi")

        events = list(ExamGradeEvent.objects.filter(attempt=attempt).order_by("created_at", "id"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].old_score, 1)
        self.assertEqual(events[-1].new_score, 0)
        self.assertEqual(events[-1].grader_id, self.teacher.id)


class UnlinkedExamAppealTests(_AppealJournalSetup):
    def test_appeal_on_unlinked_exam_touches_no_journal(self):
        """Reqressiya: jurnala bağlı olmayan imtahanda apellyasiya no-op qalır."""
        exam = Exam.objects.create(
            title="Sərbəst quiz", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q", points=1)
        ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question)
        item = self._appeal_item(attempt, question, answer)

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(item, reviewer=self.teacher, response_text="Açar səhv idi")

        self.assertIsNone(self._final_grade())
