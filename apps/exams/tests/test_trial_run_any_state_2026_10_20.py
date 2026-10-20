"""«Sınaq keç» imtahanın istənilən vəziyyətində (2026-10-20).

Sahibin sözü: «imtahan yaradarkən "Sınaqdan keç"ə click edərkən imtahan deaktivdə olsa, tarixə də
çatmasa yenə mümkün olsun».

* Müəllif deaktiv / gələcək tarixli / bitmiş imtahanı sınaqdan keçirir — cəhd ``is_trial=True``,
  take səhifəsi açılır, autosave/finish işləyir; bitmiş imtahanda sınaq öz müddəti qədər yazılır.
* Müəllif olmayan, sualları idarə edən imtahan mərkəzi də sınaq keçir (final, deaktiv, kənar şəbəkə).
* Tələbə / icazəsiz müəllim ``?trial=1`` əlavə etsə də sərt yoldadır: deaktiv → 404, gələcək tarix →
  «hələ başlamayıb», cəhd yaranmır; adi cəhd deaktiv imtahanda əvvəlki kimi 403.
* Sınaq cəhdi statistikaya / jurnala sayılmır.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.services.journal_sync import sync_attempt_to_journal
from apps.exams.services.start_intent import start_intent_token
from apps.exams.services.trial_run import can_trial_run_exam
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    User,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org

EXTERNAL_IP = "85.132.9.9"
NETWORK_ON = {
    "EXAM_FINAL_INTERNAL_ONLY": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8"],
    "NETWORK_ZONE_TRUST_HEADER": False,
}


def _start_url(exam, user, *, trial=True):
    query = f"si={start_intent_token(user.pk, exam.pk)}"
    if trial:
        query = f"trial=1&{query}"
    return f"{reverse('exams:start_exam', kwargs={'slug': exam.slug})}?{query}"


def _take_url(attempt):
    return reverse("exams:take_exam", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id})


@override_settings(CACHES=LOCMEM_CACHE)
class TrialRunAnyStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("trial1020")
        cls.other_teacher = User.objects.create_user("trial1020_other", "trial1020_other@test.az", PASSWORD)
        _assign_user_to_org(cls.other_teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.exam_center = User.objects.create_user("trial1020_center", "trial1020_center@test.az", PASSWORD)
        _assign_user_to_org(cls.exam_center, cls.org, ProfileRole.MEMBER, "exam_center_head")

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _exam(self, title, **changes):
        exam = _make_quiz(self.org, self.teacher, n_questions=2, title=title)
        for field, value in changes.items():
            setattr(exam, field, value)
        if changes:
            exam.save(update_fields=list(changes))
        return exam

    def _client(self, user):
        return _student_client(user.username, self.org)

    def _start_trial(self, client, exam, user, **extra):
        response = client.get(_start_url(exam, user), **extra)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        attempt = ExamAttempt.objects.get(exam=exam, user=user)
        self.assertEqual(response["Location"].split("?")[0], _take_url(attempt))
        self.assertTrue(attempt.is_trial)
        return attempt

    def _autosave(self, client, attempt, **extra):
        question = attempt.exam.questions.order_by("order").first()
        return client.post(
            _take_url(attempt),
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(question.id)],
                f"q_{question.id}": option_value(attempt, question.options.get(label="A")),
                "marked_question_ids": "[]",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            **extra,
        )

    # ── müəllif ───────────────────────────────────────────────────────────
    def test_author_trial_on_inactive_exam_creates_trial_attempt_and_is_writable(self):
        exam = self._exam("Deaktiv", is_active=False)
        client = self._client(self.teacher)

        attempt = self._start_trial(client, exam, self.teacher)

        self.assertEqual(client.get(_take_url(attempt)).status_code, 200)
        autosave = self._autosave(client, attempt)
        self.assertEqual(autosave.status_code, 200, autosave.content[:300])
        self.assertTrue(autosave.json()["success"])
        finish = client.post(_take_url(attempt), {"submit_action": "finish"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(finish.status_code, 200)
        self.assertTrue(finish.json()["finished"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        result = client.get(reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id}))
        self.assertEqual(result.status_code, 200)

    def test_author_trial_on_future_dated_exam(self):
        now = timezone.now()
        exam = self._exam("Gələcək", start_datetime=now + timedelta(days=2), end_datetime=now + timedelta(days=3))
        client = self._client(self.teacher)

        attempt = self._start_trial(client, exam, self.teacher)

        self.assertEqual(client.get(_take_url(attempt)).status_code, 200)
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(minutes=exam.total_duration_minutes))

    def test_author_trial_on_ended_exam_runs_for_its_own_duration(self):
        now = timezone.now()
        exam = self._exam("Bitmiş", start_datetime=now - timedelta(days=3), end_datetime=now - timedelta(days=1))
        client = self._client(self.teacher)

        attempt = self._start_trial(client, exam, self.teacher)

        # Keçmiş `end_datetime` sınağı dərhal bağlamır — deadline = başlanğıc + müddət.
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(minutes=exam.total_duration_minutes))
        self.assertEqual(client.get(_take_url(attempt)).status_code, 200)
        autosave = self._autosave(client, attempt)
        self.assertEqual(autosave.status_code, 200, autosave.content[:300])
        self.assertTrue(autosave.json()["success"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")

        # Öz müddəti bitəndən sonra isə yazı bağlanır.
        ExamAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(minutes=exam.total_duration_minutes + 10)
        )
        late = self._autosave(client, attempt)
        self.assertTrue(late.json().get("finished"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")

    def test_author_trial_still_requires_an_active_question(self):
        exam = self._exam("Sualsız", is_active=False)
        exam.questions.update(is_active=False)
        client = self._client(self.teacher)

        response = client.get(_start_url(exam, self.teacher))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_trial_without_token_shows_confirm_page_and_post_creates_trial(self):
        exam = self._exam("Təsdiq", is_active=False)
        client = self._client(self.teacher)
        url = f"{reverse('exams:start_exam', kwargs={'slug': exam.slug})}?trial=1"

        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url).status_code, 302)
        self.assertTrue(ExamAttempt.objects.get(exam=exam, user=self.teacher).is_trial)

    # ── müəllif olmayan sual meneceri ─────────────────────────────────────
    @override_settings(**NETWORK_ON)
    def test_exam_center_non_author_trial_on_inactive_final_from_external_network(self):
        exam = self._exam("Final qaralama", is_active=False, exam_type_extended="final")
        client = self._client(self.exam_center)

        attempt = self._start_trial(client, exam, self.exam_center, REMOTE_ADDR=EXTERNAL_IP)

        self.assertEqual(client.get(_take_url(attempt), REMOTE_ADDR=EXTERNAL_IP).status_code, 200)
        autosave = self._autosave(client, attempt, REMOTE_ADDR=EXTERNAL_IP)
        self.assertEqual(autosave.status_code, 200, autosave.content[:300])
        self.assertTrue(autosave.json()["success"])

    def test_plain_non_author_teacher_cannot_trial_inactive_exam(self):
        exam = self._exam("Başqasının qaralaması", is_active=False)
        client = self._client(self.other_teacher)

        self.assertEqual(client.get(_start_url(exam, self.other_teacher)).status_code, 404)
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_teacher_cannot_trial_final_of_someone_else(self):
        exam = self._exam("Final", exam_type_extended="final")
        self.other_teacher.set_active_organization_context(self.org)
        self.assertFalse(can_trial_run_exam(self.other_teacher, exam))
        self.assertFalse(can_trial_run_exam(self.student, exam))
        self.assertTrue(can_trial_run_exam(self.teacher, exam))

    # ── tələbə: davranış dəyişməyib ───────────────────────────────────────
    def test_student_with_trial_param_gets_404_on_inactive_exam(self):
        exam = self._exam("Tələbəyə deaktiv", is_active=False)
        client = self._client(self.student)

        self.assertEqual(client.get(_start_url(exam, self.student)).status_code, 404)
        self.assertEqual(client.get(_start_url(exam, self.student, trial=False)).status_code, 404)
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_student_with_trial_param_gets_not_started_error_on_future_exam(self):
        now = timezone.now()
        exam = self._exam(
            "Tələbəyə gələcək", start_datetime=now + timedelta(days=2), end_datetime=now + timedelta(days=3)
        )
        client = self._client(self.student)

        response = client.get(_start_url(exam, self.student))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("take", response["Location"])
        expected = exam.can_user_start(self.student)[1]
        self.assertIn(expected, [str(message) for message in get_messages(response.wsgi_request)])
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_student_with_trial_param_gets_ended_error_on_past_exam(self):
        now = timezone.now()
        exam = self._exam(
            "Tələbəyə bitmiş", start_datetime=now - timedelta(days=3), end_datetime=now - timedelta(days=1)
        )
        client = self._client(self.student)

        response = client.get(_start_url(exam, self.student))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_student_regular_attempt_is_blocked_after_deactivation(self):
        exam = self._exam("Sonradan deaktiv")
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        for question in exam.questions.order_by("order"):
            ExamAnswer.objects.create(attempt=attempt, question=question)
        exam.is_active = False
        exam.save(update_fields=["is_active"])
        client = self._client(self.student)

        self.assertEqual(client.get(_take_url(attempt)).status_code, 403)
        self.assertEqual(self._autosave(client, attempt).status_code, 403)

    def test_student_trial_param_on_active_exam_creates_regular_attempt(self):
        exam = self._exam("Aktiv")
        client = self._client(self.student)

        self.assertEqual(client.get(_start_url(exam, self.student)).status_code, 302)
        self.assertFalse(ExamAttempt.objects.get(exam=exam, user=self.student).is_trial)

    # ── sınaq nəticələrə sayılmır ─────────────────────────────────────────
    def test_trial_attempt_is_excluded_from_statistics_and_journal(self):
        exam = self._exam("Statistika", is_active=False)
        client = self._client(self.teacher)
        attempt = self._start_trial(client, exam, self.teacher)
        client.post(_take_url(attempt), {"submit_action": "finish"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)

        stats = client.get(reverse("exams:teacher_exam_statistics", kwargs={"slug": exam.slug}))
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.context["total_attempts"], 0)
        self.assertIsNone(sync_attempt_to_journal(attempt))
        self.assertEqual(exam.attempts_left_for(self.teacher), exam.max_attempts_per_user or None)


def test_trial_deadline_ignores_close_exam_end():
    """Bitmə vaxtı müddətdən yaxın olsa da sınaq tam müddət işləyir (sahib 2026-10-20)."""
    from datetime import timedelta
    from types import SimpleNamespace

    from django.utils import timezone

    from apps.exams.domain.attempt_deadline import attempt_deadline_at

    now = timezone.now()
    exam = SimpleNamespace(end_datetime=now + timedelta(minutes=5), total_duration_minutes=60)
    trial = SimpleNamespace(exam=exam, started_at=now, room_id=None, is_trial=True)
    normal = SimpleNamespace(exam=exam, started_at=now, room_id=None, is_trial=False)
    assert attempt_deadline_at(trial) == now + timedelta(minutes=60)
    assert attempt_deadline_at(normal) == exam.end_datetime
