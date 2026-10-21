"""2026-10-21 (sahib) — imtahan zalı: başlıqsız çərçivə, açar yalnız zal kompüterində, apellyasiyadan sonra çıxış.

1. «İmtahan zalında midterm/final verərkən yuxarıdakı header görünməməlidir, nəticəyə baxanda da olmaz» — zal
   sessiyasında cəhd, nəticə, apellyasiya və istənilən digər səhifədə sayt başlığı (``blog-header``), ⌘K axtarış,
   «Qoşul», AI düyməsi YOXDUR; yerinə minimal zal çərçivəsi (``data-hall-frame``). Kabinet nəticəsində başlıq qalır.
2. «Düzgün və səhv cavabı ancaq həmin zaldakı imtahan verdiyi kompüterdə görə bilər» — «imtahan sonunda» rejimi və
   nəticə səhifəsindəki açar/verdikt yalnız HƏMİN cəhdin aktiv zal sessiyası + bağlı cihazda.
3. «Apellyasiya verəndən sonra giriş səhifəsinə geri qayıtmalı — uğurlu formada olduğunu dedikdən sonra» — zal
   apellyasiyası → uğur ekranı (artıq çıxış edilib) → «Bitir» → ``/exams/midterm/`` | ``/exams/final/``.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.appeals.models import Appeal
from apps.appeals.tests.test_final_midterm_appeals_2026_10_20 import (
    INTERNAL_IP,
    KEY_OPTION,
    NETWORK_ON,
    OTHER_OPTION,
    WRONG_OPTION,
    _StudentSetup,
)
from apps.exams.models import ExamAttempt
from apps.exams.tests.hall_helpers import enter_hall, leave_hall, switch_device

CHROME_MARKERS = ("blog-header", "data-global-search", "ai-bot-btn", "Qoşul")


@override_settings(**NETWORK_ON, EXAM_MIDTERM_VIA_CENTER=True)
class _HallSetup(_StudentSetup):
    def _hall_attempt(self, category="midterm", **kwargs):
        attempt = self._attempt(category, **kwargs)
        enter_hall(self.client, attempt)
        return attempt

    def _result_url(self, attempt):
        return reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id})

    def assertChromeless(self, response):
        for marker in CHROME_MARKERS:
            self.assertNotContains(response, marker, html=False)
        self.assertNotContains(response, reverse("accounts:profile"), html=False)

    def assertKeyHidden(self, response):
        for text in (KEY_OPTION, OTHER_OPTION):
            self.assertNotContains(response, text)
        self.assertNotContains(response, "q-verdict-chip", html=False)
        self.assertNotContains(response, "correct-option", html=False)


class HallChromeTests(_HallSetup):
    def test_result_page_in_hall_is_chromeless_with_frame(self):
        attempt = self._hall_attempt()
        response = self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertChromeless(response)
        self.assertContains(response, "data-hall-frame", html=False)
        self.assertContains(response, "exams/css/hall/hall_frame.css", html=False)
        self.assertContains(response, attempt.exam.title)

    def test_appeal_page_in_hall_is_chromeless_with_frame(self):
        attempt = self._hall_attempt()
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        response = self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertChromeless(response)
        self.assertContains(response, "data-hall-frame", html=False)
        self.assertContains(response, reverse("exams:hall_session_exit"), html=False)

    def test_any_other_page_in_hall_session_is_chromeless(self):
        self._hall_attempt()
        response = self.client.get(reverse("exams:student_exam_history"))
        self.assertEqual(response.status_code, 200)
        for marker in ("blog-header", "data-global-search", "ai-bot-btn"):
            self.assertNotContains(response, marker, html=False)
        self.assertContains(response, "data-hall-frame", html=False)

    def test_cabinet_result_keeps_site_header(self):
        attempt = self._attempt("midterm")
        response = self.client.get(self._result_url(attempt), {"from_section": "my-results"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "blog-header", html=False)
        self.assertNotContains(response, "data-hall-frame", html=False)

    def test_take_page_in_hall_has_no_site_header(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self._attempt("final").exam,
            status="in_progress",
            attempt_number=2,
        )
        enter_hall(self.client, attempt)
        response = self.client.get(
            reverse("exams:take_exam", args=[attempt.exam.slug, attempt.id]), REMOTE_ADDR=INTERNAL_IP
        )
        self.assertEqual(response.status_code, 200)
        for marker in ("blog-header", "data-global-search", "ai-bot-btn"):
            self.assertNotContains(response, marker, html=False)

    def test_hall_exit_logs_out_to_kind_entry(self):
        self._hall_attempt("midterm")
        response = self.client.post(reverse("exams:hall_session_exit"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:midterm_exam_entry"))
        self.assertNotIn("_auth_user_id", self.client.session)


class HallOnlyAnswerKeyTests(_HallSetup):
    def test_bound_device_in_hall_sees_key_on_result_and_appeal(self):
        attempt = self._hall_attempt()
        result = self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertContains(result, KEY_OPTION)
        self.assertOnsiteContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_other_device_same_session_is_later_and_result_hides_key(self):
        attempt = self._hall_attempt()
        switch_device(self.client)
        self.assertKeyHidden(self._result(attempt, REMOTE_ADDR=INTERNAL_IP))
        response = self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertLaterContent(response)
        self._post(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertFalse(Appeal.objects.get(attempt=attempt).filed_onsite)

    def test_unbound_attempt_is_never_onsite(self):
        attempt = self._attempt("final")
        enter_hall(self.client, attempt, bind_device=False)
        self.assertKeyHidden(self._result(attempt, REMOTE_ADDR=INTERNAL_IP))
        self.assertLaterContent(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_after_leaving_hall_appeal_is_later(self):
        attempt = self._hall_attempt()
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        leave_hall(self.client)
        self.assertLaterContent(self._form(attempt, {"from_section": "my-appeals"}, REMOTE_ADDR=INTERNAL_IP))

    def test_other_browser_logged_in_normally_is_later(self):
        attempt = self._hall_attempt("final")
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        from django.test import Client

        home = Client()
        home.force_login(self.student)
        session = home.session
        session["active_organization"] = self.org.slug
        session.save()
        response = home.get(reverse("appeals:appeal_create", args=[attempt.id]), REMOTE_ADDR=INTERNAL_IP)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["appeal_mode"], "later")
        for text in (KEY_OPTION, WRONG_OPTION, OTHER_OPTION):
            self.assertNotContains(response, text)
        self.assertNotContains(response, "Cavabınız: düzgün")
        self.assertNotContains(response, "Cavabınız: səhv")
        result = home.get(self._result_url(attempt), REMOTE_ADDR=INTERNAL_IP)
        self.assertKeyHidden(result)

    def test_cabinet_result_hides_per_question_verdicts(self):
        for category in ("midterm", "final"):
            with self.subTest(category=category):
                attempt = self._attempt(category)
                response = self.client.get(self._result_url(attempt), {"from_section": "my-results"})
                self.assertEqual(response.status_code, 200)
                self.assertKeyHidden(response)
                self.assertEqual(response.context["answer_verdict_by_qid"], {})
                self.assertContains(response, "score-points-value", html=False)

    def test_notes_mention_hall_computer_and_minutes(self):
        attempt = self._hall_attempt()
        result = self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertContains(result, "yalnız imtahan verdiyiniz zal kompüterində")
        self.assertContains(result, "15 dəqiqə")
        form = self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertContains(form, "data-appeal-hall-note", html=False)
        self.assertContains(form, "15 dəqiqə")


class HallAppealSubmitTests(_HallSetup):
    def _submit_in_hall(self, category):
        attempt = self._hall_attempt(category)
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        return attempt, self._post(attempt, REMOTE_ADDR=INTERNAL_IP)

    def test_midterm_hall_appeal_shows_success_then_midterm_entry(self):
        attempt, response = self._submit_in_hall("midterm")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("appeals:hall_appeal_done"))
        # Zal sessiyası bağlanıb: logout + marker yoxdur.
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("final_exam_ticket_id", self.client.session)
        done = self.client.get(response["Location"])
        self.assertEqual(done.status_code, 200)
        self.assertContains(done, "Apellyasiyanız qəbul edildi")
        self.assertContains(done, attempt.exam.title)
        self.assertContains(done, "1 sual üzrə etiraz qeydə alındı")
        self.assertContains(done, "Bitir")
        entry = reverse("exams:midterm_exam_entry")
        self.assertContains(done, f'href="{entry}"', html=False)
        self.assertContains(done, f'data-hall-done-url="{entry}"', html=False)
        self.assertContains(done, "appeals/js/hall_done.js", html=False)
        self.assertChromeless(done)
        self.assertTrue(Appeal.objects.get(attempt=attempt).filed_onsite)

    def test_final_hall_appeal_goes_to_final_entry(self):
        _attempt, response = self._submit_in_hall("final")
        done = self.client.get(response["Location"])
        self.assertContains(done, f'data-hall-done-url="{reverse("exams:final_exam_entry")}"', html=False)

    def test_done_page_without_summary_goes_to_entry(self):
        self.client.logout()
        response = self.client.get(reverse("appeals:hall_appeal_done"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_entry"))

    def test_cabinet_appeal_unchanged(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(hours=3))
        response = self.client.post(
            reverse("appeals:appeal_create", args=[attempt.id]) + "?from_section=my-appeals",
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": "wrong_answer_key",
                f"comment_{self.question.id}": "Cavab açarı səhvdir, B variantı da düzgündür — dərslik 4.2.",
                "from_section": "my-appeals",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:profile") + "?section=my-appeals")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(Appeal.objects.get(attempt=attempt).filed_onsite)

    def test_five_minute_review_logs_out_to_midterm_entry(self):
        attempt = self._hall_attempt("midterm")
        ExamAttempt.objects.filter(pk=attempt.pk).update(finished_at=timezone.now() - timedelta(minutes=6))
        response = self.client.get(self._result_url(attempt), REMOTE_ADDR=INTERNAL_IP)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:midterm_exam_entry"))
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(EXAM_HALL_COMPUTER_CHECK=True)
class StrictHallComputerTests(_HallSetup):
    """Koordinator 2026-10-21: sərt zal rejimində mərkəz cəhdinin take/yazı/nəticə/zal-apellyasiya sorğuları yalnız
    qeydli zal kompüterindən (``center_exams.ensure_center_hall_computer``); sınaq cəhdi istisnadır."""

    BLOCKED = "qeydiyyatdan keçməyib"

    def _open_attempt(self, *, is_trial=False):
        exam = self._attempt("final").exam
        return ExamAttempt.objects.create(
            user=self.student, exam=exam, status="in_progress", attempt_number=2, is_trial=is_trial
        )

    def _take(self, attempt):
        return self.client.get(
            reverse("exams:take_exam", args=[attempt.exam.slug, attempt.id]), REMOTE_ADDR="10.99.0.7"
        )

    def test_unregistered_computer_take_and_result_blocked(self):
        attempt = self._open_attempt()
        enter_hall(self.client, attempt)  # qeydli kompüterlər: 127.0.0.1 / 10.20.30.41 — 10.99.0.7 deyil
        response = self._take(attempt)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, self.BLOCKED, status_code=403)
        finished = self._hall_attempt("final")
        result = self.client.get(self._result_url(finished), REMOTE_ADDR="10.99.0.7")
        self.assertEqual(result.status_code, 403)
        self.assertNotContains(result, KEY_OPTION, status_code=403)
        form = self.client.get(reverse("appeals:appeal_create", args=[finished.id]), REMOTE_ADDR="10.99.0.7")
        self.assertEqual(form.status_code, 403)

    def test_autosave_post_blocked_on_unregistered_computer(self):
        attempt = self._open_attempt()
        enter_hall(self.client, attempt)
        response = self.client.post(
            reverse("exams:take_exam", args=[attempt.exam.slug, attempt.id]),
            {"submit_action": "save"},
            REMOTE_ADDR="10.99.0.7",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json().get("hall_computer_blocked"))

    def test_registered_computer_ok(self):
        attempt = self._open_attempt()
        enter_hall(self.client, attempt)
        self.assertEqual(
            self.client.get(
                reverse("exams:take_exam", args=[attempt.exam.slug, attempt.id]), REMOTE_ADDR=INTERNAL_IP
            ).status_code,
            200,
        )
        finished = self._hall_attempt("final")
        self.assertEqual(self.client.get(self._result_url(finished), REMOTE_ADDR=INTERNAL_IP).status_code, 200)

    def test_trial_attempt_not_gated(self):
        from django.test import RequestFactory

        from apps.exams.services.center_exams import ensure_center_hall_computer

        attempt = self._open_attempt(is_trial=True)
        request = RequestFactory().get("/", REMOTE_ADDR="10.99.0.7")
        ensure_center_hall_computer(request, attempt)  # istisna atmır
