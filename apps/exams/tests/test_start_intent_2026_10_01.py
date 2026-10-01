"""EXAMQA R1 (2026-10-01): kənar link tələbənin vaxtlı cəhdini başlada bilməz.

* tokensiz GET → təsdiq səhifəsi, cəhd YARANMIR;
* POST (CSRF) və ya platformanın öz linkindəki imzalı token → cəhd yaranır;
* başqa istifadəçinin / başqa imtahanın / saxta tokeni → təsdiq səhifəsi;
* davam edən cəhdə qayıtmaq tokensiz də işləyir (yan təsiri yoxdur);
* CSRF-siz POST rədd olunur (403).
"""

import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.exams.models import ExamAttempt
from apps.exams.services.start_intent import exam_start_url, start_intent_token
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    _make_people,
    _make_quiz,
    _student_client,
)


@override_settings(CACHES=LOCMEM_CACHE)
class StartIntentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("siq")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=2, title="SI Quiz")
        cls.other_exam = _make_quiz(cls.org, cls.teacher, n_questions=1, title="SI Other")

    def setUp(self):
        self.client = _student_client("siq_student", self.org)
        self.url = reverse("exams:start_exam", kwargs={"slug": self.exam.slug})

    def _attempts(self):
        return ExamAttempt.objects.filter(exam=self.exam, user=self.student).count()

    def test_plain_get_shows_confirmation_and_creates_nothing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/student/exam_start_confirm.html")
        self.assertContains(response, 'method="post"')
        self.assertEqual(self._attempts(), 0)

    def test_post_starts_the_attempt(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._attempts(), 1)

    def test_get_with_own_token_starts_the_attempt(self):
        response = self.client.get(exam_start_url(self.exam, self.student))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._attempts(), 1)

    def test_foreign_or_forged_tokens_do_not_start(self):
        for token in (
            start_intent_token(self.teacher.pk, self.exam.pk),  # başqa istifadəçi
            start_intent_token(self.student.pk, self.other_exam.pk),  # başqa imtahan
            "WzEsMl0:forged:signature",
        ):
            response = self.client.get(self.url, {"si": token})
            self.assertTemplateUsed(response, "exams/student/exam_start_confirm.html")
        self.assertEqual(self._attempts(), 0)

    def test_resume_works_without_token(self):
        self.client.post(self.url)
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/{attempt.id}/", response["Location"])
        self.assertEqual(self._attempts(), 1)

    def test_post_without_csrf_is_rejected(self):
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="siq_student", password=PASSWORD)
        session = strict.session
        session["active_organization"] = self.org.slug
        session.save()
        response = strict.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._attempts(), 0)

    def test_student_exam_list_links_carry_a_working_token(self):
        response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 200)
        # Token zaman möhürlüdür (saniyəyə görə dəyişir) — səhifədəkini götürüb işlədiyini yoxlayırıq.
        match = re.search(rf"{re.escape(self.url)}\?(?:[^\"]*&)?si=([^&\"]+)", response.content.decode())
        self.assertIsNotNone(match, "imtahan siyahısındakı «Başla» linkində si tokeni yoxdur")
        self.client.get(self.url, {"si": match.group(1)})
        self.assertEqual(self._attempts(), 1)
