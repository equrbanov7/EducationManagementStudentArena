"""URL auditi (sahib 2026-10-10) — exams: silinən ölü marşrutlar + praktiki imtahan kilidi.

* A12 — `center/pin-lookup/` səhifəsi, `<slug>/available-question-count/`, `pending-work/`,
  `deleted/`, `groups/<gid>/students/<sid>/remove|add/` artıq YOXDUR (reverse → NoReverseMatch).
* §4 — `assigned/` kabinetin `?section=assigned-exams` bölməsinə yönləndirir.
* Praktiki (coding) imtahanlar «hələlik gizli qalsın»: ``PRACTICAL_EXAMS_ENABLED=False`` olanda
  coding marşrutları heç nə icra etmir və müəllim UI-ı coding imtahan yaratmağı TƏKLİF ETMİR.
  Bu, funksional dəyişiklik deyil — mövcud davranışın kilid testidir.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm
from apps.exams.models import CodingSubmission, Exam, ExamAnswer, ExamAttempt
from apps.exams.services.coding_definition import upsert_coding_question
from apps.exams.tests.test_coding_exam import assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

REMOVED_ROUTES = (
    ("exams:exam_center_pin_lookup", []),
    ("exams:exam_available_question_count", ["some-exam"]),
    ("exams:teacher_pending_attempts", []),
    ("exams:deleted_exams_list", []),
    ("exams:teacher_remove_student_from_group", [1, 2]),
    ("exams:teacher_add_student_to_group", [1, 2]),
)


class RemovedExamRoutesTests(SimpleTestCase):
    def test_removed_routes_do_not_reverse(self):
        for name, args in REMOVED_ROUTES:
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name, args=args)

    def test_kept_neighbour_routes_still_reverse(self):
        # PIN axtarışının AJAX son nöqtələri, qrup siyahısı və sual-göndərişi gələnlər qutusu QALIR.
        reverse("exams:exam_center_pin_search")
        reverse("exams:exam_center_student_pins", kwargs={"student_id": 1})
        reverse("exams:teacher_group_list")
        reverse("exams:assigned_exam_list")


def _modal_html(form):
    return render_to_string(
        "exams/teacher/partials/_create_exam_modal_form.html",
        {
            "form": form,
            "is_editing": False,
            "exam": None,
            "linked_course": None,
            "selected_allowed_groups": [],
            "selected_allowed_users": [],
            "selected_excluded_users": [],
            "supervision_config": None,
        },
    )


class PracticalExamsHiddenLockTests(TestCase):
    """Sahib 2026-10-10: «hələlik gizli qalsın» — bayraq söndürülü ikən coding axını bağlıdır."""

    def setUp(self):
        self.teacher = User.objects.create_user("wp9b_coding_teacher", "wp9b_ct@example.com", "StrongPass123!")
        self.student = User.objects.create_user("wp9b_coding_student", "wp9b_cs@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="WP9b Coding Org",
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
            title="WP9b Coding Exam",
            exam_type="coding",
            random_question_count=0,
            is_active=True,
        )
        _, coding_question = upsert_coding_question(
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
                "enable_code_execution": True,
            },
            visible_cases=[],
            hidden_cases=[],
        )
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=1)
        ExamAnswer.objects.create(attempt=self.attempt, question=coding_question.question)
        self.submission = CodingSubmission.objects.create(
            student=self.student,
            exam=self.exam,
            attempt=self.attempt,
            question=coding_question,
            selected_language="python",
            files=[{"name": "main.py", "content": "print('hello')\n"}],
            is_final=True,
        )
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _kwargs(self):
        return {"slug": self.exam.slug, "attempt_id": self.attempt.id}

    @override_settings(PRACTICAL_EXAMS_ENABLED=False)
    def test_coding_write_routes_refuse_and_never_execute_code(self):
        payload = json.dumps(
            {
                "selected_language": "python",
                "files": [{"name": "main.py", "content": "print(1)\n", "language": "python", "is_main": True}],
                "stdin": "",
            }
        )
        with patch("apps.exams.services.coding_runtime.execute_code") as execute_code:
            for name in ("exams:coding_autosave", "exams:coding_run", "exams:coding_submit"):
                with self.subTest(route=name):
                    response = self.client.post(
                        reverse(name, kwargs=self._kwargs()),
                        data=payload,
                        content_type="application/json",
                        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                    )
                    # Mövcud davranış: JSON 403 «Praktiki imtahan … deaktivdir» (404 deyil).
                    self.assertEqual(response.status_code, 403)
                    self.assertFalse(response.json().get("success", False))
            execute_code.assert_not_called()

    @override_settings(PRACTICAL_EXAMS_ENABLED=False)
    def test_coding_submission_download_is_404(self):
        url = reverse(
            "exams:coding_submission_download", kwargs={**self._kwargs(), "submission_id": self.submission.id}
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(PRACTICAL_EXAMS_ENABLED=False)
    def test_teacher_ui_does_not_offer_coding_exam(self):
        form = ExamForm(user=self.teacher, organization=self.org)
        self.assertNotIn("coding", [value for value, _label in form.fields["exam_type"].choices])
        self.assertNotIn('value="coding"', _modal_html(form))

    @override_settings(PRACTICAL_EXAMS_ENABLED=True)
    def test_flag_on_offers_coding_again(self):
        # Geri dönüş: bayraq yandırılanda seçim yenidən görünür (kod silinməyib).
        form = ExamForm(user=self.teacher, organization=self.org)
        self.assertIn("coding", [value for value, _label in form.fields["exam_type"].choices])
        self.assertIn('value="coding"', _modal_html(form))
