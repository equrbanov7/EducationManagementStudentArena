import json
import subprocess
import zipfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm
from apps.exams.models import CodingFile, CodingSubmission, CodingTestCase, Exam, ExamAnswer, ExamAttempt
from apps.exams.services.coding_definition import build_coding_payload_from_exam_form, upsert_coding_question
from apps.exams.services.coding_runtime import (
    ExecutionResult,
    clean_docker_stderr,
    execute_code,
    execution_language_for_filename,
    mark_file_as_main,
    normalize_python_indentation,
    prepare_files_for_execution,
    run_visible_code,
    truncate_capture,
)
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class CodingRuntimeIndentationTests(SimpleTestCase):
    def test_execution_language_uses_file_extension(self):
        self.assertEqual(execution_language_for_filename("solution.cpp", "python"), "cpp")
        self.assertEqual(execution_language_for_filename("answer.py", "cpp"), "python")
        self.assertEqual(execution_language_for_filename("style.css", "python"), "html")

    def test_mark_file_as_main_switches_without_deleting_files(self):
        files = [
            {"name": "main.py", "content": "", "language": "python", "is_main": True},
            {"name": "solution.cpp", "content": "", "language": "cpp", "is_main": False},
        ]

        marked = mark_file_as_main(files, "solution.cpp")

        self.assertFalse(marked[0]["is_main"])
        self.assertTrue(marked[1]["is_main"])
        self.assertEqual([item["name"] for item in marked], ["main.py", "solution.cpp"])

    def test_python_loose_top_level_unindent_is_normalized(self):
        code = 'print("hello")\n\ndef greet(name):\n    print(f"hello {name}")\n\n greet("elvin")\n'

        normalized = normalize_python_indentation(code)

        self.assertIn('\ngreet("elvin")\n', normalized)
        self.assertNotIn('\n greet("elvin")\n', normalized)

    def test_python_valid_one_space_suite_indent_is_preserved(self):
        code = 'if True:\n print("ok")\n print("still ok")\n'

        self.assertEqual(normalize_python_indentation(code), code)

    def test_python_multiline_string_indentation_is_preserved(self):
        code = 'text = """\n  keep this spacing\n"""\n print(text)\n'

        normalized = normalize_python_indentation(code)

        self.assertIn("\n  keep this spacing\n", normalized)
        self.assertIn("\nprint(text)\n", normalized)

    @patch("apps.exams.services.coding_runtime.shutil.which", return_value="/usr/bin/docker")
    @patch("apps.exams.services.coding_runtime._ensure_docker_image", return_value="")
    @patch("apps.exams.services.coding_runtime.subprocess.run")
    def test_execute_code_keeps_stdin_open_for_docker(self, run_mock, _image_mock, _which_mock):
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="Salam, Elvin\n", stderr="")

        result = execute_code(
            language="python",
            files=[{"name": "main.py", "content": "name=input(); print(name)", "language": "python", "is_main": True}],
            stdin="Elvin\n",
            time_limit_seconds=2,
            memory_limit_mb=128,
        )

        docker_command = run_mock.call_args.args[0]
        self.assertIn("-i", docker_command)
        self.assertEqual(run_mock.call_args.kwargs["input"], "Elvin\n")
        self.assertEqual(result.output, "Salam, Elvin\n")


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
    def test_coding_exam_form_does_not_require_inline_coding_task_fields(self):
        form = ExamForm(
            data={
                "title": "Algorithms practical",
                "description": "",
                "exam_type": "coding",
                "is_active": "on",
                "random_question_count": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exam_type"], "coding")
        self.assertEqual(form.cleaned_data["random_question_count"], 10)

    def test_truncate_capture_accepts_timeout_bytes(self):
        self.assertEqual(truncate_capture(b"Execution timed out."), "Execution timed out.")

    def test_cpp_snippet_is_wrapped_for_execution(self):
        files = [{"name": "main.cpp", "content": 'cout << "ok";', "language": "cpp", "is_main": True}]

        prepared = prepare_files_for_execution("cpp", files)

        self.assertIn("#include <iostream>", prepared[0]["content"])
        self.assertIn("int main()", prepared[0]["content"])
        self.assertIn('cout << "ok";', prepared[0]["content"])
        self.assertEqual(files[0]["content"], 'cout << "ok";')

    def test_docker_pull_noise_is_removed_from_stderr(self):
        stderr = "\n".join(
            [
                "Unable to find image 'gcc:14' locally",
                "14: Pulling from library/gcc",
                "159f67d2ced1: Pulling fs layer",
                "159f67d2ced1: Download complete",
                "main.cpp:1:1: error: expected unqualified-id",
            ]
        )

        self.assertEqual(clean_docker_stderr(stderr), "main.cpp:1:1: error: expected unqualified-id")


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

    def test_take_coding_exam_includes_five_minute_warning_modal(self):
        self.exam.total_duration_minutes = 30
        self.exam.save(update_fields=["total_duration_minutes"])

        response = self.client.get(
            reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "examTimeWarningModal")
        self.assertContains(response, "exam_time_warning.js")
        self.assertContains(response, f'examId: "{self.exam.id}"')
        self.assertContains(response, f'attemptId: "{self.attempt.id}"')

    def test_run_uses_active_python_file_and_custom_stdin(self):
        self.coding_question.enable_code_execution = True
        self.coding_question.save(update_fields=["enable_code_execution"])
        CodingTestCase.objects.create(
            coding_question=self.coding_question,
            input_data="teacher case\n",
            expected_output="teacher output\n",
            visibility=CodingTestCase.VISIBILITY_VISIBLE,
        )
        payload = {
            "selected_language": "html",
            "active_file_name": "solution.py",
            "files": [
                {"name": "index.html", "content": "<h1>Preview</h1>", "language": "html", "is_main": False},
                {"name": "solution.py", "content": "name=input(); print(name)", "language": "python", "is_main": True},
            ],
            "stdin": "student input\n",
        }

        with patch("apps.exams.services.coding_runtime.execute_code") as execute_code:
            execute_code.return_value = ExecutionResult(
                status=CodingSubmission.STATUS_SUCCESS,
                output="student input\n",
                error="",
                execution_time_ms=12,
            )
            response = self.client.post(
                reverse("exams:coding_run", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        self.assertEqual(response.status_code, 200)
        execute_code.assert_called_once()
        call_kwargs = execute_code.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "python")
        self.assertEqual(call_kwargs["stdin"], "student input\n")
        self.assertEqual(call_kwargs["files"][0]["name"], "index.html")
        self.assertEqual(call_kwargs["files"][1]["name"], "solution.py")
        body = response.json()
        self.assertEqual(body["submission"]["output"], "student input\n")
        self.assertEqual(body["submission"]["test_results"], [])

    def test_run_visible_code_returns_output_for_supported_sandbox_languages(self):
        self.coding_question.enable_code_execution = True
        self.coding_question.save(update_fields=["enable_code_execution"])
        cases = [
            ("javascript", "main.js", "const fs=require('fs'); console.log(fs.readFileSync(0,'utf8'))"),
            ("python", "main.py", "print(input())"),
            ("cpp", "main.cpp", "#include <iostream>\nint main(){ std::string s; std::cin >> s; std::cout << s; }"),
            (
                "java",
                "Main.java",
                "import java.util.*; public class Main { public static void main(String[] args){ System.out.print(new Scanner(System.in).next()); }}",
            ),
        ]

        for language, filename, content in cases:
            with self.subTest(language=language):
                with patch("apps.exams.services.coding_runtime.execute_code") as execute_code:
                    execute_code.return_value = ExecutionResult(
                        status=CodingSubmission.STATUS_SUCCESS,
                        output=f"{language}: ok\n",
                        error="",
                    )
                    result = run_visible_code(
                        coding_question=self.coding_question,
                        selected_language=language,
                        files=[{"name": filename, "content": content, "language": language, "is_main": True}],
                        stdin="ok\n",
                    )

                self.assertEqual(result["status"], CodingSubmission.STATUS_SUCCESS)
                self.assertEqual(result["output"], f"{language}: ok\n")
                self.assertEqual(execute_code.call_args.kwargs["language"], language)
                self.assertEqual(execute_code.call_args.kwargs["stdin"], "ok\n")

    def test_submission_download_returns_all_code_files_as_zip(self):
        payload = {
            "selected_language": "html",
            "files": [
                {"name": "index.html", "content": "<h1>Hello</h1>", "language": "html", "is_main": True},
                {"name": "style.css", "content": "h1 { color: red; }", "language": "css", "is_main": False},
                {"name": "script.js", "content": "console.log('ok');", "language": "javascript", "is_main": False},
            ],
            "stdin": "",
        }

        submit_response = self.client.post(
            reverse("exams:coding_submit", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(submit_response.status_code, 200)
        submission = CodingSubmission.objects.get(is_final=True)

        download_url = reverse(
            "exams:coding_submission_download",
            kwargs={
                "slug": self.exam.slug,
                "attempt_id": self.attempt.id,
                "submission_id": submission.id,
            },
        )
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(set(archive.namelist()), {"index.html", "style.css", "script.js"})
            self.assertEqual(archive.read("index.html").decode(), "<h1>Hello</h1>")
            self.assertEqual(archive.read("script.js").decode(), "console.log('ok');")

        result_response = self.client.get(
            reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        )
        self.assertContains(result_response, pgettext("exams.template.coding_exam", "Download ZIP"))

        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        teacher_response = self.client.get(download_url)
        self.assertEqual(teacher_response.status_code, 200)

        teacher_view_response = self.client.get(
            reverse("exams:teacher_view_attempt", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        )
        self.assertContains(teacher_view_response, pgettext("exams.template.coding_exam", "Download ZIP"))

    def test_teacher_check_attempt_syncs_missing_coding_answers_from_final_submissions(self):
        _, second_coding_question = upsert_coding_question(
            self.exam,
            payload={
                "language": "html",
                "title": "Second page",
                "problem_statement": "Build the second page.",
                "input_description": "",
                "output_description": "",
                "example_input": "",
                "example_output": "",
                "time_limit_seconds": 2,
                "memory_limit_mb": 128,
                "max_score": 40,
                "starter_code": "",
                "allow_file_creation": True,
                "allow_multiple_files": True,
                "enable_code_execution": False,
            },
            visible_cases=[],
            hidden_cases=[],
        )
        self.assertEqual(self.attempt.answers.count(), 1)

        first_submission = CodingSubmission.objects.create(
            student=self.student,
            exam=self.exam,
            attempt=self.attempt,
            question=self.coding_question,
            selected_language="html",
            submitted_code="<h1>First</h1>",
            files=[
                {"name": "index.html", "content": "<h1>First</h1>", "language": "html", "is_main": True},
                {"name": "style.css", "content": "h1 { color: red; }", "language": "css", "is_main": False},
                {"name": "script.js", "content": "console.log('first');", "language": "javascript", "is_main": False},
            ],
            is_final=True,
            execution_status=CodingSubmission.STATUS_SUBMITTED,
        )
        for file_item in first_submission.files:
            CodingFile.objects.create(submission=first_submission, **file_item)

        second_submission = CodingSubmission.objects.create(
            student=self.student,
            exam=self.exam,
            attempt=self.attempt,
            question=second_coding_question,
            selected_language="html",
            submitted_code="<h1>Second</h1>",
            files=[
                {"name": "index.html", "content": "<h1>Second</h1>", "language": "html", "is_main": True},
                {"name": "style.css", "content": "h1 { color: blue; }", "language": "css", "is_main": False},
            ],
            is_final=True,
            execution_status=CodingSubmission.STATUS_SUBMITTED,
        )
        for file_item in second_submission.files:
            CodingFile.objects.create(submission=second_submission, **file_item)

        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = self.client.get(
            reverse("exams:teacher_check_attempt", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["qa_list"]), 2)
        self.assertTrue(
            ExamAnswer.objects.filter(attempt=self.attempt, question=second_coding_question.question).exists()
        )
        content = response.content.decode()
        self.assertIn("Second page", content)
        self.assertIn("style.css", content)
        self.assertIn("script.js", content)
        self.assertIn("console.log", content)
        self.assertEqual(content.count(f'name="score_{self.coding_question.question_id}"'), 1)
        self.assertEqual(content.count(f'name="score_{second_coding_question.question_id}"'), 1)
