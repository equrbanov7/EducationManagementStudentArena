"""W3 `w3sweep` (2026-09-14): sınaq (`is_trial`) cəhdi apellyasiya olunmur.

Brauzer süpürgəsi (qa.teacher → «Sınaq keç» → nəticə): «Bu sınaq keçididir —
nəticə heç yerə yazılmır» yazısının yanında «Apellyasiya et» düyməsi çıxırdı və
POST real `Appeal` yaradırdı (imtahan mərkəzinin apellyasiya statistikasını
çirkləndirir).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

VALID_COMMENT = "y" * 40


def _assign(user, organization, profile_role, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=membership_role_name), "is_primary": True, "is_active": True},
    )


class TrialAttemptNotAppealableTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w3ap_teacher", "w3ap_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("w3ap_student", "w3ap_s@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="W3AP Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        _assign(self.student, self.org, ProfileRole.STUDENT, "student")
        self.exam = Exam.objects.create(
            title="W3AP Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Sual")
        self.wrong = ExamQuestionOption.objects.create(
            question=self.question, label="B", text="Yanlış", is_correct=False
        )
        ExamQuestionOption.objects.create(question=self.question, label="A", text="Düz", is_correct=True)

    def _attempt(self, user, *, is_trial, number=1):
        attempt = ExamAttempt.objects.create(
            user=user,
            exam=self.exam,
            status="submitted",
            finished_at=timezone.now(),
            is_trial=is_trial,
            attempt_number=number,
        )
        answer = ExamAnswer.objects.create(attempt=attempt, question=self.question, is_correct=False)
        answer.selected_options.add(self.wrong)
        return attempt

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _result(self, client, attempt):
        return client.get(reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id}))

    def test_student_real_attempt_is_appealable_but_trial_is_not(self):
        """Eyni tələbə, eyni imtahan — fərq yalnız `is_trial` bayrağıdır."""
        client = self._client(self.student)
        real = self._attempt(self.student, is_trial=False)
        trial = self._attempt(self.student, is_trial=True, number=2)

        real_page = self._result(client, real)
        self.assertEqual(real_page.status_code, 200)
        self.assertTrue(real_page.context["can_appeal"])
        self.assertContains(real_page, reverse("appeals:appeal_create", kwargs={"attempt_id": real.id}), html=False)

        trial_page = self._result(client, trial)
        self.assertEqual(trial_page.status_code, 200)
        self.assertFalse(trial_page.context["can_appeal"])
        self.assertNotContains(
            trial_page, reverse("appeals:appeal_create", kwargs={"attempt_id": trial.id}), html=False
        )

    def test_teacher_trial_result_hides_appeal_cta(self):
        """Süpürgədəki repro: müəllimin «Sınaq keç» nəticəsi."""
        attempt = self._attempt(self.teacher, is_trial=True)
        page = self._result(self._client(self.teacher), attempt)
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_appeal"])

    def test_crafted_post_does_not_create_appeal_for_trial(self):
        attempt = self._attempt(self.student, is_trial=True)
        response = self._client(self.student).post(
            reverse("appeals:appeal_create", args=[attempt.id]),
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )
        self.assertIn(response.status_code, (200, 302, 403))
        self.assertFalse(Appeal.objects.filter(attempt=attempt).exists())
