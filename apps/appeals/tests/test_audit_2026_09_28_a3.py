"""Audit 2026-09-28 — A3 iş paketi: apellyasiya qapıları, qərar bütövlüyü, cəhd tarixçəsi.

* EXA-02 — yoxlanmamış yazılı cəhdə apellyasiya yoxdur; pəncərə ``teacher_checked_at``-dan;
* EXA-03 — tarixçə: yalnız final, rəsmi faiz (bonus daxil), apellyasiya sətirləri,
  dekan/koordinator oxu icazəsi;
* EXA-05 — 5 dəqiqəlik yenidən redaktədə geri alma reviewer adına yazılır;
* EXA-06 — başlıq statusu state-machine ilə yoxlanır;
* EXA-07 — kateqoriya server tərəfdə (quiz/practice → yox);
* EXA-08 — yazılı clamp çatdırılan snapshot balından;
* EX28-11 — daxili qeyd tələbəyə görünmür; «artıq düzgündür» snapshot açarı ilə.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.appeals.constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_PENDING,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_TYPE_WRONG_ANSWER_KEY,
)
from apps.appeals.models import Appeal, AppealItem, ScoreAdjustment
from apps.appeals.services import (
    InvalidAppealTransition,
    accept_appeal_item,
    appeal_block_reason,
    appeal_deadline,
    can_view_appeal,
    create_appeal,
    is_within_appeal_window,
    recompute_appeal_status,
)
from apps.appeals.services.permissions import oversight_covers_student
from apps.appeals.services.scoring import _question_already_correct
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamGradeEvent, ExamQuestion, ExamQuestionOption
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import exam_attempt_history, services
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

COMMENT = "x" * 30


class _A3Setup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("a3_owner", "a3_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("a3_teacher", "a3_teacher@qku.edu.az", "pw")
        self.student = User.objects.create_user("a3_student", "a3_student@qku.edu.az", "pw")
        self.dean = User.objects.create_user("a3_dean", "a3_dean@qku.edu.az", "pw")
        self.other_dean = User.objects.create_user("a3_dean2", "a3_dean2@qku.edu.az", "pw")
        self.reviewer = User.objects.create_superuser("a3_reviewer", "a3_reviewer@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="A3 Univ",
                slug="a3-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="A3G1", slug="a3-g1", unit_type=OrgUnitType.GROUP
            )
            self.other_group = OrgUnit.objects.create(
                organization=self.org, name="A3G2", slug="a3-g2", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="CS", name="KE", absence_limit_percent=25)
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=self.subject, semester_number=1
            )
            for user, role_name in ((self.teacher, "teacher"), (self.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
            for user, unit in ((self.dean, self.group), (self.other_dean, self.other_group)):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name="dean"),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
            record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=self.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)

    # ── köməkçilər ────────────────────────────────────────────────────────────
    def _exam(self, *, exam_type="written", category="final", title="A3 Final"):
        return Exam.objects.create(
            title=title,
            author=self.teacher,
            organization=self.org,
            subject=self.subject,
            exam_type=exam_type,
            exam_type_extended=category,
            is_active=True,
        )

    def _written_attempt(
        self, *, checked, teacher_score, live_points=10, snapshot_points=None, finished_ago=0, checked_ago=0, exam=None
    ):
        exam = exam or self._exam()
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=live_points)
        now = timezone.now()
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
            finished_at=now - timedelta(days=finished_ago),
            checked_by_teacher=checked,
            teacher_checked_at=(now - timedelta(days=checked_ago)) if checked else None,
            teacher_score=teacher_score,
        )
        answer = ExamAnswer.objects.create(
            attempt=attempt,
            question=question,
            teacher_score=teacher_score,
            question_snapshot={"v": 2, "points": snapshot_points or live_points, "options": []},
        )
        return attempt, question, answer

    def _item(self, attempt, question, answer):
        appeal = Appeal.objects.create(attempt=attempt, exam=attempt.exam, student=self.student, organization=self.org)
        return AppealItem.objects.create(
            appeal=appeal, question=question, answer=answer, appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY, comment=COMMENT
        )

    def _request(self, user):
        return SimpleNamespace(user=user, organization=self.org)


class AppealGateTests(_A3Setup):
    """EXA-02 / EXA-07 — yaratma qapısı."""

    def test_unchecked_written_attempt_is_not_appealable(self):
        attempt, question, _answer = self._written_attempt(checked=False, teacher_score=None)
        self.assertEqual(appeal_block_reason(self._request(self.student), attempt), "not_graded")
        self.assertFalse(is_within_appeal_window(attempt))
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=attempt,
                student=self.student,
                items=[{"question_id": question.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": COMMENT}],
            )

    def test_window_starts_when_teacher_checks_the_work(self):
        # Bitib 10 gün əvvəl, yoxlanıb 1 gün əvvəl → pəncərə açıqdır (əvvəl finished_at-dan bağlı idi).
        attempt, _question, _answer = self._written_attempt(
            checked=True, teacher_score=6, finished_ago=10, checked_ago=1
        )
        self.assertTrue(is_within_appeal_window(attempt))
        checked_date = timezone.localtime(attempt.teacher_checked_at).date()
        self.assertEqual(timezone.localtime(appeal_deadline(attempt)).date(), checked_date + timedelta(days=3))

    def test_quiz_category_is_rejected_server_side(self):
        exam = self._exam(exam_type="test", category="quiz", title="A3 Quiz")
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now()
        )
        ExamAnswer.objects.create(attempt=attempt, question=question)
        self.assertEqual(appeal_block_reason(self._request(self.student), attempt), "category")
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=attempt,
                student=self.student,
                items=[{"question_id": question.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": COMMENT}],
            )

    def test_legacy_appeal_on_unchecked_attempt_cannot_be_accepted(self):
        attempt, question, answer = self._written_attempt(checked=False, teacher_score=None)
        item = self._item(attempt, question, answer)
        with self.assertRaises(ValidationError):
            accept_appeal_item(item, reviewer=self.reviewer, response_text="ok")
        answer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertIsNone(answer.teacher_score)
        self.assertIsNone(attempt.teacher_score)
        self.assertFalse(ScoreAdjustment.objects.filter(appeal_item=item).exists())


class AppealDecisionIntegrityTests(_A3Setup):
    """EXA-05 / EXA-06 / EXA-08 / EX28-11."""

    def test_written_clamp_uses_delivered_snapshot_points(self):
        # Canlı sual 10 bal, çatdırılan snapshot 2 bal; tələbə artıq 2/2 alıb → +1 tavanı keçə bilməz.
        attempt, question, answer = self._written_attempt(
            checked=True, teacher_score=2, live_points=10, snapshot_points=2
        )
        item = self._item(attempt, question, answer)
        accept_appeal_item(item, reviewer=self.reviewer, response_text="ok")
        answer.refresh_from_db()
        self.assertEqual(answer.teacher_score, 2)

    def test_already_correct_check_uses_delivered_key(self):
        exam = self._exam(exam_type="test")
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q", points=1)
        option_a = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=False)
        option_b = ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=True)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted")
        # Çatdırılan açar: A düzgün idi; müəllif SONRA açarı B-yə dəyişib.
        answer = ExamAnswer.objects.create(
            attempt=attempt,
            question=question,
            question_snapshot={
                "v": 2,
                "points": 1,
                "options": [{"id": option_a.id, "is_correct": True}, {"id": option_b.id, "is_correct": False}],
            },
            selected_option_ids_snapshot=[option_a.id],
        )
        answer.selected_options.add(option_a)
        self.assertTrue(_question_already_correct(answer, question))

    def test_re_edit_revert_is_attributed_to_reviewer_in_one_transaction(self):
        attempt, question, answer = self._written_attempt(checked=True, teacher_score=5)
        item = self._item(attempt, question, answer)
        self.client.force_login(self.reviewer)
        url = reverse("appeals:review_appeal", args=[item.appeal_id]) + "?fragment=1"
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        first = self.client.post(url, {f"decision_{item.id}": "accept", f"response_{item.id}": "Haqlıdır."}, **headers)
        self.assertEqual(first.status_code, 200)
        second = self.client.post(url, {f"decision_{item.id}": "reject", f"response_{item.id}": "Yenidən."}, **headers)
        self.assertEqual(second.status_code, 200)
        answer.refresh_from_db()
        self.assertEqual(answer.teacher_score, 5)
        events = ExamGradeEvent.objects.filter(attempt=attempt, question=question)
        self.assertGreaterEqual(events.count(), 2)
        self.assertFalse(events.filter(grader__isnull=True).exists())

    def test_header_status_goes_through_state_machine(self):
        attempt, question, answer = self._written_attempt(checked=True, teacher_score=5)
        item = self._item(attempt, question, answer)
        accept_appeal_item(item, reviewer=self.reviewer, response_text="ok")
        appeal = Appeal.objects.get(pk=item.appeal_id)
        self.assertEqual(appeal.status, APPEAL_STATUS_ACCEPTED)
        # Yekun → pending cədvəldə heç bir yolla icazəli deyil.
        AppealItem.objects.filter(pk=item.pk).update(status=APPEAL_ITEM_STATUS_PENDING)
        with self.assertRaises(InvalidAppealTransition):
            recompute_appeal_status(appeal)

    def test_internal_reviewer_note_hidden_from_student(self):
        attempt, question, answer = self._written_attempt(checked=True, teacher_score=5)
        item = self._item(attempt, question, answer)
        appeal = item.appeal
        appeal.reviewer_note = "DAXILI-QEYD-XYZ"
        base = {"appeal": appeal, "items": [], "item_stats": {}, "marked_question_by_qid": {}}
        owner_html = render_to_string("appeals/partials/_appeal_detail_body.html", {**base, "is_owner": True})
        staff_html = render_to_string("appeals/partials/_appeal_detail_body.html", {**base, "is_owner": False})
        self.assertNotIn("DAXILI-QEYD-XYZ", owner_html)
        self.assertIn("DAXILI-QEYD-XYZ", staff_html)


class AttemptHistoryTests(_A3Setup):
    """EXA-03 — sahibin memo-su: düzgün faiz, yalnız final, apellyasiya sətirləri, dekan oxu."""

    def test_written_final_percent_official_and_midterm_excluded(self):
        with bypass_rls():
            # 8/10 yoxlanmış yazılı final → 80 % (əvvəl correct/wrong-dan 0.0 idi).
            attempt, _q, _a = self._written_attempt(checked=True, teacher_score=8, finished_ago=2)
            # Sonrakı midterm tarixçəyə düşmür və «rəsmi» sayılmır.
            midterm = self._exam(exam_type="written", category="midterm", title="A3 Midterm")
            ExamAttempt.objects.create(user=self.student, exam=midterm, status="submitted", finished_at=timezone.now())
            rows = exam_attempt_history.attempt_rows_for_subject(
                student=self.student, subject_id=self.subject.id, organization=self.org
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attempt_id"], attempt.id)
        self.assertEqual(rows[0]["percent"], 80.0)
        self.assertTrue(rows[0]["is_official"])

    def test_latest_final_is_official_and_appeal_rows_attached(self):
        with bypass_rls():
            first, question, answer = self._written_attempt(checked=True, teacher_score=4, finished_ago=5)
            item = self._item(first, question, answer)
            accept_appeal_item(item, reviewer=self.reviewer, response_text="ok")
            resit_exam = self._exam(title="A3 Final 25%")
            second, _q2, _a2 = self._written_attempt(checked=True, teacher_score=7, finished_ago=1, exam=resit_exam)
            rows = exam_attempt_history.attempt_rows_for_subject(
                student=self.student, subject_id=self.subject.id, organization=self.org
            )
        self.assertEqual([row["attempt_id"] for row in rows], [first.id, second.id])
        self.assertEqual([row["is_official"] for row in rows], [False, True])
        self.assertEqual(rows[0]["percent"], 50.0)  # 4 + 1 (apellyasiya) / 10
        appeal_rows = rows[0]["appeals"]
        self.assertEqual(len(appeal_rows), 1)
        self.assertEqual(appeal_rows[0]["status"], APPEAL_STATUS_ACCEPTED)
        self.assertEqual(appeal_rows[0]["accepted_count"], 1)
        self.assertEqual(appeal_rows[0]["delta_points"], 1)
        self.assertTrue(appeal_rows[0]["reviewer_name"])
        self.assertEqual(rows[1]["appeals"], [])

    def test_test_final_percent_includes_appeal_bonus(self):
        with bypass_rls():
            exam = self._exam(exam_type="test")
            questions = []
            for order in (1, 2):
                question = ExamQuestion.objects.create(exam=exam, order=order, text=f"Q{order}", points=1)
                correct = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
                ExamQuestionOption.objects.create(question=question, label="B", text="b", is_correct=False)
                questions.append((question, correct))
            attempt = ExamAttempt.objects.create(
                user=self.student, exam=exam, status="submitted", finished_at=timezone.now()
            )
            answers = []
            for index, (question, correct) in enumerate(questions):
                answer = ExamAnswer.objects.create(attempt=attempt, question=question)
                if index == 0:
                    answer.selected_options.add(correct)
                answers.append(answer)
            item = self._item(attempt, questions[1][0], answers[1])
            accept_appeal_item(item, reviewer=self.reviewer, response_text="ok")
            rows = exam_attempt_history.attempt_rows_for_subject(
                student=self.student, subject_id=self.subject.id, organization=self.org
            )
        self.assertEqual(rows[0]["percent"], 100.0)
        self.assertEqual(AppealItem.objects.get(pk=item.pk).status, APPEAL_ITEM_STATUS_ACCEPTED)

    def test_dean_in_scope_can_view_appeal_read_only(self):
        attempt, question, answer = self._written_attempt(checked=True, teacher_score=5)
        appeal = self._item(attempt, question, answer).appeal
        with bypass_rls():
            self.assertTrue(oversight_covers_student(self.dean, self.org, self.student.id))
            self.assertFalse(oversight_covers_student(self.other_dean, self.org, self.student.id))
            self.assertFalse(oversight_covers_student(self.teacher, self.org, self.student.id))
            self.assertTrue(can_view_appeal(self._request(self.dean), appeal))
            self.assertFalse(can_view_appeal(self._request(self.other_dean), appeal))
