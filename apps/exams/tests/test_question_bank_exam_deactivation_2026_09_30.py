"""QB 2026-09-30 — sual bankı səhifəsi və tək sual silmə: «imtahan deaktiv edilsin?» axını.

* seçimin bir hissəsi → adi uğur;
* bütün aktiv suallar → AJAX-a 409 ``exam_deactivation_required`` (EMSConfirm mətnləri),
  JS-siz formaya server təsdiq səhifəsi; təsdiqlə imtahan deaktiv + suallar silinir;
* açıq cəhd / canlı sessiya → 409 ``exam_in_use`` (səbəb adlandırılır), heç nə dəyişmir;
* ``exam.edit`` icazəsi olmayana təsdiq təklif olunmur.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamQuestion
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.live_exam.models import LiveSession
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
CONFIRM_FIELD = "confirm_exam_deactivation"


class _BankViewFixture(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("qb_view_teacher", "qb_view_teacher@example.com", "pw")
        self.student = User.objects.create_user("qb_view_student", "qb_view_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="QB view org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)
        _login_with_org(self.client, self.teacher, self.org)
        self.exam = Exam.objects.create(
            title="Canlı imtahan",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
        )
        self.questions = [
            ExamQuestion.objects.create(exam=self.exam, order=index + 1, text=f"Sual {index + 1}", points=1)
            for index in range(10)
        ]
        self.url = reverse("exams:teacher_questions_bank", args=[self.exam.slug])

    def _ids(self, questions=None):
        return [str(question.pk) for question in (questions if questions is not None else self.questions)]

    def _post(self, action="delete", ids=None, *, ajax=True, confirm=False, **extra):
        data = {"bulk_action": action, "status": "all", "sort": "newest", "page": "1", **extra}
        if ids is not None:
            data["selected_question_ids"] = ids
        if confirm:
            data[CONFIRM_FIELD] = "1"
        return self.client.post(self.url, data, **(AJAX if ajax else {}))

    def _messages(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def _assert_untouched(self):
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)
        self.assertEqual(self.exam.questions.filter(is_active=True).count(), 10)


class QuestionBankBulkGuardViewTests(_BankViewFixture):
    def test_subset_delete_succeeds(self):
        response = self._post("delete", self._ids(self.questions[:4]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["redirect_url"].startswith(self.url))
        self.assertEqual(self.exam.questions.count(), 6)
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)

    def test_subset_delete_plain_form_still_redirects(self):
        response = self._post("delete", self._ids(self.questions[:4]), ajax=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.exam.questions.count(), 6)

    def test_selecting_all_active_questions_asks_for_exam_deactivation(self):
        response = self._post("delete", self._ids())

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "exam_deactivation_required")
        self.assertEqual(payload["confirm_field"], CONFIRM_FIELD)
        self.assertIn("imtahan deaktiv ediləcək", payload["confirm"]["body"])
        self.assertTrue(payload["confirm"]["title"])
        self.assertTrue(payload["confirm"]["confirm_label"])
        self._assert_untouched()

    def test_confirmed_delete_all_selected_deactivates_exam_and_deletes(self):
        response = self._post("delete", self._ids(), confirm=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)
        self.assertEqual(self.exam.questions.count(), 0)
        self.assertEqual(len(self._messages(response)), 2)  # «N sual silindi» + «imtahan deaktiv edildi»

    def test_confirmed_bulk_deactivate_all(self):
        response = self._post("deactivate", self._ids(), confirm=True)

        self.assertEqual(response.status_code, 200)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)
        self.assertEqual(self.exam.questions.filter(is_active=True).count(), 0)
        self.assertEqual(self.exam.questions.count(), 10)

    def test_delete_all_button_uses_same_confirmation_flow(self):
        first = self._post("delete_all")
        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.json()["code"], "exam_deactivation_required")
        self._assert_untouched()

        second = self._post("delete_all", confirm=True)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.exam.questions.count(), 0)

    def test_plain_form_gets_server_side_confirmation_page_and_replay_works(self):
        response = self._post("delete", self._ids(), ajax=False)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/teacher/confirm_delete.html")
        self.assertContains(response, f'name="{CONFIRM_FIELD}" value="1"', html=False)
        self.assertContains(response, 'name="bulk_action" value="delete"', html=False)
        self.assertContains(response, f'name="selected_question_ids" value="{self.questions[0].pk}"', html=False)
        self._assert_untouched()

        replay = self._post("delete", self._ids(), ajax=False, confirm=True)
        self.assertEqual(replay.status_code, 302)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)
        self.assertEqual(self.exam.questions.count(), 0)

    def test_in_progress_attempt_is_refused_with_reason(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=1)

        for confirm in (False, True):
            response = self._post("delete", self._ids(), confirm=confirm)
            self.assertEqual(response.status_code, 409)
            payload = response.json()
            self.assertEqual(payload["code"], "exam_in_use")
            self.assertIn("tələbə", payload["message"])
        self._assert_untouched()

    def test_running_live_session_is_refused_with_reason(self):
        session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher, state=LiveSession.STATE_QUESTION)

        response = self._post("delete", self._ids(), confirm=True)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "exam_in_use")
        self.assertIn(session.pin, response.json()["message"])
        self._assert_untouched()

    def test_finished_live_session_allows_cleanup(self):
        LiveSession.objects.create(exam=self.exam, host_user=self.teacher, state=LiveSession.STATE_FINISHED)

        response = self._post("delete", self._ids(), confirm=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exam.questions.count(), 0)

    def test_plain_form_refusal_shows_reason_toast(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=1)

        response = self._post("delete", self._ids(), ajax=False, confirm=True)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(any("tələbə" in text for text in self._messages(response)))
        self._assert_untouched()

    def test_without_exam_edit_permission_confirmation_is_not_offered(self):
        with patch("apps.exams.views.teacher.questions._mutations.request_has_permission", return_value=False):
            response = self._post("delete", self._ids(), confirm=True)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "active_exam_requires_question")
        self._assert_untouched()

    def test_page_marks_exam_context_and_loads_guard_script(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'data-qm-context="exam"', html=False)
        self.assertContains(response, "exams/js/teacher_questions_bank/guarded_submit.js", html=False)


class SingleQuestionDeleteGuardViewTests(_BankViewFixture):
    def setUp(self):
        super().setUp()
        ExamQuestion.objects.filter(pk__in=[question.pk for question in self.questions[1:]]).delete()
        self.question = self.questions[0]
        self.delete_url = reverse("exams:delete_exam_question", args=[self.exam.slug, self.question.pk])
        self.detail_url = reverse("exams:teacher_exam_detail", args=[self.exam.slug])

    def test_last_question_delete_renders_confirmation_page(self):
        response = self.client.post(self.delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/teacher/confirm_delete.html")
        self.assertContains(response, f'name="{CONFIRM_FIELD}" value="1"', html=False)
        self.assertTrue(ExamQuestion.objects.filter(pk=self.question.pk).exists())
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)

    def test_confirmed_last_question_delete_deactivates_exam(self):
        response = self.client.post(self.delete_url, {CONFIRM_FIELD: "1"})

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.assertFalse(ExamQuestion.objects.filter(pk=self.question.pk).exists())
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)

    def test_last_question_delete_ajax_returns_structured_confirmation(self):
        response = self.client.post(self.delete_url, **AJAX)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "exam_deactivation_required")

    def test_last_question_delete_refused_while_student_is_writing(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=1)

        response = self.client.post(self.delete_url, {CONFIRM_FIELD: "1"})

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.assertTrue(ExamQuestion.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(any("tələbə" in text for text in self._messages(response)))
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)

    def test_non_last_question_delete_is_unchanged(self):
        other = ExamQuestion.objects.create(exam=self.exam, order=2, text="Digər", points=1)

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.assertFalse(ExamQuestion.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(ExamQuestion.objects.filter(pk=other.pk).exists())
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)
