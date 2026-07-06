"""Apellyasiya yaratma validasiya testləri."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_MIN_COMMENT_LENGTH, APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.services import create_appeal
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

VALID_COMMENT = "x" * APPEAL_MIN_COMMENT_LENGTH


def _assign_user_to_org(user, organization, profile_role, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


class AppealCreationTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("c_teacher", "c_t@example.com", "pw")
        self.student = User.objects.create_user("c_student", "c_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="C Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        self.exam = Exam.objects.create(
            title="C Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1")
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2")
        self.q_other = ExamQuestion.objects.create(exam=self.exam, order=3, text="Not delivered")
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        # Delivered set = q1, q2 (q_other NOT delivered).
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q1)
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q2)

    def _item(self, question, comment=VALID_COMMENT, appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY):
        return {"question_id": question.id, "appeal_type": appeal_type, "comment": comment}

    def test_create_single_item_appeal(self):
        appeal = create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1)])
        self.assertEqual(appeal.items.count(), 1)
        self.assertEqual(appeal.exam_id, self.exam.id)
        self.assertEqual(appeal.organization_id, self.org.id)

    def test_create_multi_item_appeal(self):
        appeal = create_appeal(
            attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q2)]
        )
        self.assertEqual(appeal.items.count(), 2)

    def test_empty_items_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[])

    def test_short_comment_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1, comment="too short")])

    def test_duplicate_question_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q1)])

    def test_question_not_in_attempt_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q_other)])

    def test_invalid_appeal_type_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=self.attempt,
                student=self.student,
                items=[self._item(self.q1, appeal_type="not_a_type")],
            )


class AppealCreateViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("cv_teacher", "cv_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("cv_student", "cv_s@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="CV Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        self.exam = Exam.objects.create(
            title="CV Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="GDPR sualı")
        self.correct = ExamQuestionOption.objects.create(
            question=self.question,
            label="A",
            text="Düzgün cavab",
            is_correct=True,
        )
        self.wrong = ExamQuestionOption.objects.create(
            question=self.question,
            label="B",
            text="Yanlış cavab",
            is_correct=False,
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            finished_at=timezone.now(),
        )
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question, is_correct=False)
        self.answer.selected_options.add(self.wrong)
        self.client = Client()
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_create_page_shows_student_and_correct_answer_and_search(self):
        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-appeal-search", html=False)
        self.assertContains(response, "Tələbənin cavabı")
        self.assertContains(response, "Yanlış cavab")
        self.assertContains(response, "Düzgün cavab")
        self.assertContains(response, "data-appeal-text=", html=False)

    def test_create_page_marked_button_can_switch_to_clear_state(self):
        self.attempt.marked_question_ids = [self.question.id]
        self.attempt.save(update_fields=["marked_question_ids"])

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-appeal-select-marked", html=False)
        self.assertContains(response, "data-label-clear=", html=False)
        self.assertContains(response, "İşarələnmişləri ləğv et")

    def test_final_exam_hides_my_appeals_link_and_returns_to_result_after_submit(self):
        self.exam.exam_type_extended = "final"
        self.exam.save(update_fields=["exam_type_extended"])

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "section=my-appeals", html=False)

        response = self.client.post(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:exam_result", args=[self.exam.slug, self.attempt.id]))


class AppealExamCenterRoutingTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("route_teacher", "route_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("route_student", "route_s@example.com", "StrongPass123!")
        self.exam_center = User.objects.create_user("route_center", "route_ec@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Route Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        _assign_user_to_org(self.exam_center, self.org, ProfileRole.MEMBER, "exam_center")
        self.exam = Exam.objects.create(
            title="Route Appeal Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Route sualı")
        ExamQuestionOption.objects.create(question=self.question, label="A", text="Düz cavab", is_correct=True)
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            finished_at=timezone.now(),
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.question)
        self.appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {
                    "question_id": self.question.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": VALID_COMMENT,
                }
            ],
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_teacher_cannot_manage_or_review_appeals(self):
        client = self._client_for(self.teacher)

        self.assertEqual(client.get(reverse("appeals:manage_appeals")).status_code, 403)
        self.assertEqual(client.get(reverse("appeals:review_appeal", args=[self.appeal.id])).status_code, 403)

    def test_exam_center_sees_all_org_appeals_and_can_review(self):
        client = self._client_for(self.exam_center)

        manage_response = client.get(reverse("appeals:manage_appeals"))
        self.assertEqual(manage_response.status_code, 200)
        self.assertContains(manage_response, "Route Appeal Exam")

        review_response = client.get(reverse("appeals:review_appeal", args=[self.appeal.id]))
        self.assertEqual(review_response.status_code, 200)
        self.assertContains(review_response, "Route sualı")
