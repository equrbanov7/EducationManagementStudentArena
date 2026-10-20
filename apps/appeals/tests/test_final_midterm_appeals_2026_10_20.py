"""2026-10-20 (sahib) — final/midterm apellyasiyası: «imtahan sonunda» / «sonradan» rejimləri.

Sahib: «Midterm və final üçün də apellyasiya prosesi aktiv olmalıdır. Tələbə apellyasiyanı imtahan
bitən kimi verirsə düzgün cavabları da görür; sonradan (evdən) verirsə YALNIZ sualları görür — nə
düzgün cavabı, nə də digər variantları».

* pəncərə (N gün) final/midterm üçün bal məlum olan an açılır — cavab açarı kilidli olsa belə;
* «imtahan sonunda» = təhvildən sonrakı nəticə ekranını görmüş sessiya + universitet şəbəkəsi +
  ``exam.appeal_onsite_minutes`` müddəti → forma variantları, seçimi və düzgün cavabı göstərir;
* qalan hallarda forma YALNIZ sual gövdəsini göstərir (HTML və kontekstdə variant/açar yoxdur);
* rejim yaradılma anında ``Appeal.filed_onsite``-a yazılır və audit olunur; əməkdaş nişanı görür;
* quiz (apellyasiya olunmayan kateqoriya) davranışı dəyişməyib.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal
from apps.appeals.services import create_appeal
from apps.appeals.services.window import appeal_window_start
from apps.appeals.tests.test_key_correction_2026_10_13 import _AJAX, _KeyFixSetup
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization
from core import runtime_settings
from core.constants import OrganizationType

User = get_user_model()

KEY_OPTION = "KEY-OPTION-1020"
WRONG_OPTION = "WRONG-OPTION-1020"
OTHER_OPTION = "OTHER-OPTION-1020"
STEM_TEXT = "STEM-1020 Aşağıdakı kod nə çap edir?"
STEM_CODE = "print(1020)"
COMMENT = "Cavab açarı səhvdir, B variantı da düzgündür — dərslik 4.2."

INTERNAL_IP = "10.20.30.41"
EXTERNAL_IP = "85.132.9.9"
NETWORK_ON = {
    "EXAM_FINAL_INTERNAL_ONLY": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8"],
    "NETWORK_ZONE_TRUST_HEADER": False,
}


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class _StudentSetup(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("fm_teacher", "fm_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("fm_student", "fm_s@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="FM Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        _assign(self.student, self.org, ProfileRole.STUDENT, "student")
        self.client = Client()
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _attempt(self, category, *, finished_ago=None, results_hidden=False):
        finished_ago = finished_ago or timedelta(minutes=2)
        exam = Exam.objects.create(
            title=f"FM {category}",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended=category,
            is_active=True,
            is_public=True,
            max_attempts_per_user=1,
            results_hidden_from_students=results_hidden,
        )
        self.question = ExamQuestion.objects.create(
            exam=exam, order=1, text=f"{STEM_TEXT}\n```\n{STEM_CODE}\n```", answer_mode="single"
        )
        ExamQuestionOption.objects.create(question=self.question, label="A", text=KEY_OPTION, is_correct=True)
        wrong = ExamQuestionOption.objects.create(question=self.question, label="B", text=WRONG_OPTION)
        ExamQuestionOption.objects.create(question=self.question, label="C", text=OTHER_OPTION)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now() - finished_ago
        )
        answer = ExamAnswer.objects.create(attempt=attempt, question=self.question, is_correct=False)
        answer.selected_options.add(wrong)
        return attempt

    def _result(self, attempt, **extra):
        url = reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id})
        response = self.client.get(url, **extra)
        self.assertEqual(response.status_code, 200)
        return response

    def _form(self, attempt, params=None, **extra):
        response = self.client.get(reverse("appeals:appeal_create", args=[attempt.id]), params or {}, **extra)
        self.assertEqual(response.status_code, 200)
        return response

    def _post(self, attempt, **extra):
        qid = self.question.id
        return self.client.post(
            reverse("appeals:appeal_create", args=[attempt.id]),
            {f"appeal_q_{qid}": "1", f"appeal_type_{qid}": APPEAL_TYPE_WRONG_ANSWER_KEY, f"comment_{qid}": COMMENT},
            **extra,
        )

    def assertLaterContent(self, response):
        """«Sonradan» rejimi: sual gövdəsi var; variantlar, seçim, açar nə HTML-də, nə kontekstdə var."""
        self.assertContains(response, "data-appeals-form", html=False)
        self.assertContains(response, 'data-appeal-mode="later"', html=False)
        self.assertContains(response, "STEM-1020")
        self.assertContains(response, STEM_CODE)
        for text in (KEY_OPTION, WRONG_OPTION, OTHER_OPTION):
            self.assertNotContains(response, text)
        for marker in ("appeal-option", "is-correct", "Düzgün cavab", "Variantlar", "Tələbənin cavabı"):
            self.assertNotContains(response, marker, html=False)
        for answer in response.context["answers"]:
            self.assertEqual(list(answer.delivered.options), [])
            self.assertEqual(answer.delivered.correct_answer, "")
            self.assertFalse(answer.has_selection)
        self.assertTrue(response.context["hide_answer_details"])
        self.assertEqual(response.context["appeal_mode"], "later")

    def assertOnsiteContent(self, response):
        self.assertContains(response, 'data-appeal-mode="onsite"', html=False)
        for text in (KEY_OPTION, WRONG_OPTION, OTHER_OPTION, STEM_CODE):
            self.assertContains(response, text)
        self.assertContains(response, "appeal-option is-correct", html=False)
        self.assertContains(response, "Tələbənin cavabı")
        self.assertEqual(response.context["appeal_mode"], "onsite")


class FinalMidtermWindowTests(_StudentSetup):
    def test_final_attempt_appealable_within_window(self):
        attempt = self._attempt("final", finished_ago=timedelta(days=1))
        self.assertLaterContent(self._form(attempt))
        response = self._post(attempt)
        self.assertEqual(response.status_code, 302)
        appeal = Appeal.objects.get(attempt=attempt)
        self.assertFalse(appeal.filed_onsite)

    def test_midterm_attempt_appealable_within_window(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(hours=5))
        self.assertLaterContent(self._form(attempt, {"from_section": "my-appeals"}))
        self._post(attempt)
        self.assertTrue(Appeal.objects.filter(attempt=attempt, filed_onsite=False).exists())

    def test_window_opens_even_if_answer_review_locked_for_secure_categories(self):
        attempt = self._attempt("midterm")
        with mock.patch("apps.appeals.services.window.exam_answers_release_locked", return_value=True):
            self.assertIsNotNone(appeal_window_start(attempt))
            quiz = self._attempt("quiz")
            self.assertIsNone(appeal_window_start(quiz))

    def test_outside_window_rejected(self):
        attempt = self._attempt("final", finished_ago=timedelta(days=12))
        response = self._form(attempt)
        self.assertNotContains(response, "data-appeals-form", html=False)
        self.assertNotContains(response, KEY_OPTION)
        self._post(attempt)
        self.assertFalse(Appeal.objects.filter(attempt=attempt).exists())

    def test_teacher_hidden_results_keep_window_closed(self):
        attempt = self._attempt("final", results_hidden=True)
        response = self._form(attempt)
        self.assertNotContains(response, "data-appeals-form", html=False)
        self.assertNotContains(response, KEY_OPTION)

    def test_quiz_behaviour_unchanged(self):
        attempt = self._attempt("quiz")
        response = self._form(attempt)
        self.assertEqual(response.context["appeal_block_reason"], "category")
        self.assertNotContains(response, "data-appeals-form", html=False)
        self._post(attempt)
        self.assertFalse(Appeal.objects.filter(attempt=attempt).exists())

    def test_result_page_shows_appeal_button_and_onsite_hint(self):
        attempt = self._attempt("midterm")
        response = self._result(attempt)
        self.assertContains(response, reverse("appeals:appeal_create", args=[attempt.id]))
        self.assertContains(response, "data-appeal-onsite-hint", html=False)
        # Midterm nəticə səhifəsi açarı göstərmir (dəyişməyib).
        self.assertNotContains(response, KEY_OPTION)
        later = self.client.get(
            reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id}),
            {"from_section": "my-results"},
        )
        self.assertNotContains(later, "data-appeal-onsite-hint", html=False)


@override_settings(**NETWORK_ON)
class OnsiteModeTests(_StudentSetup):
    def test_onsite_midterm_shows_options_and_key_and_is_stored(self):
        attempt = self._attempt("midterm")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertOnsiteContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))
        response = self._post(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertEqual(response.status_code, 302)
        appeal = Appeal.objects.get(attempt=attempt)
        self.assertTrue(appeal.filed_onsite)

        from apps.audit.models import AuditLog

        row = AuditLog.objects.filter(resource_type="appeals.appeal", resource_id=str(appeal.pk)).latest("id")
        self.assertEqual(row.new_values.get("mode"), "onsite")
        self.assertIs(row.new_values.get("filed_onsite"), True)

    def test_onsite_final_from_result_screen(self):
        attempt = self._attempt("final", finished_ago=timedelta(minutes=1))
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertOnsiteContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_onsite_also_from_cabinet_link_in_same_session(self):
        attempt = self._attempt("midterm")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertOnsiteContent(self._form(attempt, {"from_section": "my-appeals"}, REMOTE_ADDR=INTERNAL_IP))

    def test_without_post_finish_screen_is_later(self):
        attempt = self._attempt("midterm")
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_cabinet_result_view_does_not_grant_onsite(self):
        attempt = self._attempt("midterm")
        self.client.get(
            reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id}),
            {"from_section": "my-results"},
            REMOTE_ADDR=INTERNAL_IP,
        )
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_external_network_is_later(self):
        attempt = self._attempt("midterm")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=EXTERNAL_IP))
        self._post(attempt, REMOTE_ADDR=EXTERNAL_IP)
        self.assertFalse(Appeal.objects.get(attempt=attempt).filed_onsite)

    def test_after_grace_is_later(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(minutes=20))
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_other_students_session_never_onsite(self):
        attempt = self._attempt("midterm")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        other = User.objects.create_user("fm_other", "fm_o@example.com", "StrongPass123!")
        _assign(other, self.org, ProfileRole.STUDENT, "student")
        client = Client()
        client.force_login(other)
        response = client.get(reverse("appeals:appeal_create", args=[attempt.id]), REMOTE_ADDR=INTERNAL_IP)
        self.assertEqual(response.status_code, 404)

    def test_submit_slack_keeps_onsite_mode_once_form_opened(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(minutes=14))
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertOnsiteContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))
        ExamAttempt.objects.filter(pk=attempt.pk).update(finished_at=timezone.now() - timedelta(minutes=25))
        self._post(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertTrue(Appeal.objects.get(attempt=attempt).filed_onsite)

    def test_post_after_grace_without_onsite_form_is_later(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(minutes=10))
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        ExamAttempt.objects.filter(pk=attempt.pk).update(finished_at=timezone.now() - timedelta(minutes=25))
        self._post(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertFalse(Appeal.objects.get(attempt=attempt).filed_onsite)

    @override_settings(APPEAL_ONSITE_MINUTES=0)
    def test_zero_minutes_disables_onsite_mode(self):
        attempt = self._attempt("final", finished_ago=timedelta(minutes=1))
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_owner_detail_view_never_shows_options(self):
        attempt = self._attempt("midterm")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self._post(attempt, REMOTE_ADDR=INTERNAL_IP)
        appeal = Appeal.objects.get(attempt=attempt)
        response = self.client.get(
            reverse("appeals:appeal_detail", args=[appeal.id]) + "?fragment=1", REMOTE_ADDR=EXTERNAL_IP, **_AJAX
        )
        self.assertEqual(response.status_code, 200)
        for text in (KEY_OPTION, WRONG_OPTION, OTHER_OPTION):
            self.assertNotContains(response, text)
        self.assertNotContains(response, "data-appeal-filed-mode", html=False)


@override_settings(RUNTIME_SETTINGS_ENABLED=True)
class OnsiteRuntimeSettingTests(TestCase):
    def setUp(self):
        runtime_settings.invalidate()
        self.addCleanup(runtime_settings.invalidate)

    def test_key_registered_in_existing_exam_group(self):
        spec = runtime_settings.SPECS["exam.appeal_onsite_minutes"]
        self.assertEqual((spec.group, spec.kind, spec.min, spec.max), ("exam", "int", 0, 120))
        self.assertEqual(spec.default(), 15)
        self.assertEqual([code for code, _label in runtime_settings.GROUPS].count("exam"), 1)

    def test_stored_value_is_used_and_clamped(self):
        from django.apps import apps

        from core.runtime_settings_appeals import appeal_onsite_minutes

        model = apps.get_model("accounts", "RuntimeSetting")
        model.objects.create(key="exam.appeal_onsite_minutes", value=40)
        runtime_settings.invalidate()
        self.assertEqual(appeal_onsite_minutes(), 40)
        model.objects.filter(key="exam.appeal_onsite_minutes").update(value=999)
        runtime_settings.invalidate()
        self.assertLessEqual(appeal_onsite_minutes(), 120)


class StaffSeesFullContentAndBadgeTests(_KeyFixSetup):
    def test_review_modal_shows_full_content_and_onsite_badge(self):
        Appeal.objects.filter(pk=self.item.appeal_id).update(filed_onsite=True)
        response = self._client(self.head).get(
            reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "İmtahan sonunda verilib")
        self.assertContains(response, "appeal-option is-correct", html=False)
        self.assertContains(response, "Tələbənin cavabı")

    def test_later_badge_in_review_and_manage_list(self):
        response = self._client(self.head).get(
            reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )
        self.assertContains(response, "Sonradan verilib")
        self.assertContains(response, "appeal-option is-correct", html=False)
        listing = self._client(self.head).get(reverse("appeals:manage_appeals") + "?fragment=1", **_AJAX)
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'data-appeal-filed-mode="later"', html=False)

    def test_create_appeal_default_mode_is_later(self):
        self.assertFalse(self.item.appeal.filed_onsite)
        second = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[{"question_id": self.q2.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": COMMENT}],
            filed_onsite=True,
        )
        self.assertTrue(second.filed_onsite)
