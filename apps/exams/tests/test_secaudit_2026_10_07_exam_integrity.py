"""Təhlükəsizlik auditi 2026-10-07 — onlayn imtahan bütövlüyü (exams tərəfi).

* ``WrittenSecureIdealAnswerTests`` — nəticə səhifəsi midterm (və kabinetdəki final) YAZILI
  imtahanın «ideal cavab nümunəsi»ni (``correct_answer``) təhvildən dərhal sonra göstərirdi;
  «midterm həmişə gizli» qaydası (2026-10-05) yalnız test variantlarına tətbiq olunurdu.
* ``QuestionSeenWindowTests`` — ``question-seen`` vaxtı bitmiş (sweep hələ bağlamamış) cəhddə
  və nəzarət kilidi altında da vaxtlı sualın məzmununu çatdırıb taymerini başladırdı
  (strict delivery-nin yazı pəncərəsi/423 qaydası yalnız POST yolunda idi).
* ``StudentIncidentTypeTests`` — tələbə endpoint-i sistem/müəllim hadisələrini
  (``teacher_resumed``, ``auto_submitted`` …) də qəbul edirdi — tələbə öz nəzarət
  tarixçəsinə saxta «müəllim bərpa etdi» qeydi yaza bilirdi.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamSupervisionConfig, SupervisionIncident
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    _make_people,
    _make_quiz,
    _student_client,
)

IDEAL_ANSWER = "IDEAL-ANSWER-SEC1007"


@override_settings(CACHES=LOCMEM_CACHE)
class WrittenSecureIdealAnswerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("sw1007")

    def setUp(self):
        self.client = _student_client("sw1007_student", self.org)

    def _attempt(self, category):
        exam = Exam.objects.create(
            title=f"SW {category}",
            author=self.teacher,
            organization=self.org,
            exam_type="written",
            exam_type_extended=category,
            is_active=True,
            is_public=True,
            max_attempts_per_user=1,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Yazılı sual", correct_answer=IDEAL_ANSWER)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="submitted", finished_at=timezone.now() - timedelta(minutes=1)
        )
        ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="mənim cavabım")
        return exam, attempt

    def _result(self, exam, attempt, query=""):
        response = self.client.get(reverse("exams:exam_result", args=[exam.slug, attempt.id]) + query)
        self.assertEqual(response.status_code, 200)
        return response

    def test_written_midterm_ideal_answer_hidden_on_plain_result_url(self):
        exam, attempt = self._attempt("midterm")
        self.assertNotContains(self._result(exam, attempt), IDEAL_ANSWER)

    def test_written_final_ideal_answer_hidden_in_cabinet(self):
        exam, attempt = self._attempt("final")
        self.assertNotContains(self._result(exam, attempt, "?from_section=my-results"), IDEAL_ANSWER)

    def test_written_final_center_review_keeps_time_boxed_ideal_answer(self):
        """Qəbul edilmiş dizayn (test açarı kimi): mərkəzin 5 dəq-lik baxışında görünür."""
        exam, attempt = self._attempt("final")
        self.assertContains(self._result(exam, attempt), IDEAL_ANSWER)

    def test_written_quiz_still_shows_ideal_answer(self):
        exam, attempt = self._attempt("quiz")
        self.assertContains(self._result(exam, attempt), IDEAL_ANSWER)


@override_settings(CACHES=LOCMEM_CACHE, EXAM_SUPERVISION_ENABLED=True)
class QuestionSeenWindowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("qs1007")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=2, duration=10, title="QS1007")
        cls.exam.questions.update(time_limit_seconds=30)
        ExamSupervisionConfig.objects.create(exam=cls.exam, enabled=True)

    def setUp(self):
        self.client = _student_client("qs1007_student", self.org)
        self.client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        self.question_id = self.attempt.answers.order_by("id").values_list("question_id", flat=True).first()
        self.url = reverse("exams:question_seen", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})

    def _seen(self):
        return self.client.post(self.url, {"question_id": str(self.question_id)})

    def _timer_started(self):
        self.attempt.refresh_from_db()
        return str(self.question_id) in (self.attempt.question_timing or {})

    def test_control_open_attempt_delivers_content(self):
        response = self._seen()
        self.assertEqual(response.status_code, 200)
        self.assertIn("html", response.json())
        self.assertTrue(self._timer_started())

    def test_overdue_attempt_is_closed_and_gets_no_question_content(self):
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(started_at=timezone.now() - timedelta(minutes=30))
        response = self._seen()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("html", response.json())
        self.assertFalse(self._timer_started())
        self.assertEqual(self.attempt.status, "expired")

    def test_supervision_locked_attempt_gets_no_question_content(self):
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(
            supervision_status="locked", supervision_locked_at=timezone.now(), supervision_manual_lock=True
        )
        response = self._seen()
        self.assertEqual(response.status_code, 423)
        self.assertNotIn("html", response.json())
        self.assertFalse(self._timer_started())


@override_settings(CACHES=LOCMEM_CACHE, EXAM_SUPERVISION_ENABLED=True)
class StudentIncidentTypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("si1007")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=1, title="SI1007")
        ExamSupervisionConfig.objects.create(exam=cls.exam, enabled=True)

    def setUp(self):
        self.client = _student_client("si1007_student", self.org)
        self.client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        self.url = reverse("exams:supervision_log_incident", kwargs={"attempt_id": self.attempt.id})

    def _log(self, event_type):
        return self.client.post(
            self.url,
            data=json.dumps({"event_type": event_type, "metadata": {"teacher_username": "invigilator"}}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_student_cannot_forge_teacher_or_system_events(self):
        for event_type in (
            "teacher_resumed",
            "teacher_granted_chance",
            "auto_locked",
            "auto_submitted",
            "resume_window_expired",
            "suspicious_repeated",
        ):
            with self.subTest(event_type=event_type):
                self.assertEqual(self._log(event_type).status_code, 400)
        self.assertFalse(SupervisionIncident.objects.filter(attempt=self.attempt).exists())

    def test_client_observed_events_are_still_accepted(self):
        for event_type in ("tab_switched", "copy_attempt", "window_focused", "exam_started_supervised"):
            with self.subTest(event_type=event_type):
                self.assertEqual(self._log(event_type).status_code, 200)
        self.assertEqual(SupervisionIncident.objects.filter(attempt=self.attempt).count(), 4)
