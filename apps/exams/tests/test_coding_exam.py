import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm
from apps.exams.models import CodingSubmission, CodingTestCase, Exam, ExamAnswer, ExamAttempt
from apps.exams.services.coding_definition import build_coding_payload_from_exam_form, upsert_coding_question
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def assign_user_to_org(user, organization, role):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    membership_role = "teacher" if role == ProfileRole.TEACHER else "student"
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role),
            "is_primary": True,
            "is_active": True,
        },
    )


class CodingExamFormTests(TestCase):
    def test_coding_exam_form_parses_coding_fields(self):
        form = ExamForm(
            data={
                "title": "Algorithms practical",
                "description": "",
                "exam_type": "coding",
                "is_active": "on",
                "random_question_count": "",
                "coding_language": "python",
                "coding_question_title": "Add numbers",
                "coding_problem_statement": "Read two numbers and print their sum.",
                "coding_time_limit_seconds": "2",
                "coding_memory_limit_mb": "128",
                "coding_max_score": "100",
                "coding_visible_test_cases": '[{"input":"2 3","expected":"5","points":40}]',
                "coding_hidden_test_cases": '[{"input":"10 15","expected":"25","points":60}]',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exam_type"], "coding")
        self.assertEqual(form.cleaned_data["random_question_count"], 0)
        self.assertEqual(len(form.cleaned_data["coding_visible_test_cases"]), 1)
        self.assertEqual(len(form.cleaned_data["coding_hidden_test_cases"]), 1)


class CodingExamDefinitionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("coding_teacher", "coding_teacher@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Coding Exam Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)

    def test_upsert_coding_question_creates_question_details_and_cases(self):
        exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="Coding Midterm",
            exam_type="coding",
            random_question_count=0,
        )
        form = ExamForm(
            data={
                "title": exam.title,
                "description": "",
                "exam_type": "coding",
                "random_question_count": "",
                "coding_language": "javascript",
                "coding_question_title": "Echo",
                "coding_problem_statement": "Print input.",
                "coding_time_limit_seconds": "2",
                "coding_memory_limit_mb": "128",
                "coding_max_score": "50",
                "coding_visible_test_cases": '[{"input":"a","expected":"a","points":20}]',
                "coding_hidden_test_cases": '[{"input":"b","expected":"b","points":30}]',
                "coding_enable_code_execution": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

        question, coding_question = upsert_coding_question(
            exam,
            payload=build_coding_payload_from_exam_form(form.cleaned_data),
            visible_cases=form.cleaned_data["coding_visible_test_cases"],
            hidden_cases=form.cleaned_data["coding_hidden_test_cases"],
        )

        self.assertEqual(question.text, "Echo")
        self.assertEqual(coding_question.language, "javascript")
        self.assertEqual(coding_question.max_score, 50)
        self.assertEqual(coding_question.test_cases.count(), 2)
        self.assertEqual(coding_question.test_cases.filter(visibility=CodingTestCase.VISIBILITY_HIDDEN).count(), 1)


class CodingExamSubmissionApiTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            "coding_api_teacher", "coding_api_teacher@example.com", "StrongPass123!"
        )
        self.student = User.objects.create_user(
            "coding_api_student", "coding_api_student@example.com", "StrongPass123!"
        )
        self.org = Organization.objects.create(
            name="Coding API Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)
        assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="Coding API Exam",
            exam_type="coding",
            random_question_count=0,
            is_active=True,
        )
        _, self.coding_question = upsert_coding_question(
            self.exam,
            payload={
                "language": "python",
                "title": "Hello",
                "problem_statement": "Print hello.",
                "input_description": "",
                "output_description": "",
                "example_input": "",
                "example_output": "hello",
                "time_limit_seconds": 2,
                "memory_limit_mb": 128,
                "max_score": 100,
                "starter_code": "print('hello')\n",
                "allow_file_creation": True,
                "allow_multiple_files": True,
                "enable_code_execution": False,
            },
            visible_cases=[],
            hidden_cases=[],
        )
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1)
        ExamAnswer.objects.create(attempt=self.attempt, question=self.coding_question.question)
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_autosave_and_submit_store_code_submission(self):
        payload = {
            "selected_language": "python",
            "files": [{"name": "main.py", "content": "print('hello')\n", "language": "python", "is_main": True}],
            "stdin": "",
        }

        autosave_response = self.client.post(
            reverse("exams:coding_autosave", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(autosave_response.status_code, 200)
        self.assertEqual(CodingSubmission.objects.filter(is_final=False).count(), 1)

        submit_response = self.client.post(
            reverse("exams:coding_submit", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(submit_response.status_code, 200)
        final_submission = CodingSubmission.objects.get(is_final=True)
        self.assertEqual(final_submission.submitted_code, "print('hello')\n")
        self.assertEqual(final_submission.execution_status, CodingSubmission.STATUS_SUBMITTED)
        self.assertEqual(final_submission.code_files.count(), 1)
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_finished)
