"""EXAM-P1-04 — server-authoritative per-question timer.

Product qaydası: vaxt-limitli sual İLK göstərilən andan server saatı ilə
sayılır; müddət (limit + grace) keçəndən sonra həmin sualın POST yazısı
saxlanmır — client timer-ini devtools ilə uzatmaq işləmir. Limitsiz suallar
və siqnal göndərməmiş (köhnə client) cəhdlər geriyə-uyğun işləyir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.question_timer import mark_question_seen, question_timer_expired
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class QuestionTimerTestBase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("qt_teacher", "qt_teacher@example.com", "pw")
        self.student = User.objects.create_user("qt_student", "qt_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="QT Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        self.exam = Exam.objects.create(
            title="QT Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )

    def _question(self, *, order=1, time_limit=None):
        q = ExamQuestion.objects.create(
            exam=self.exam,
            order=order,
            text=f"Q{order}",
            points=1,
            is_active=True,
            answer_mode="single",
            time_limit_seconds=time_limit,
        )
        ExamQuestionOption.objects.create(question=q, text="A", is_correct=True)
        ExamQuestionOption.objects.create(question=q, text="B", is_correct=False)
        return q

    def _attempt(self, *questions):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=1)
        for q in questions:
            ExamAnswer.objects.create(attempt=attempt, question=q)
        return attempt

    def _expire_question(self, attempt, question, *, seconds_ago=600):
        timing = dict(attempt.question_timing or {})
        timing[str(question.id)] = (timezone.now() - timedelta(seconds=seconds_ago)).isoformat()
        attempt.question_timing = timing
        attempt.save(update_fields=["question_timing"])


class QuestionTimerServiceTests(QuestionTimerTestBase):
    def test_mark_seen_keeps_first_timestamp(self):
        q = self._question(time_limit=60)
        attempt = self._attempt(q)
        first = mark_question_seen(attempt, q)
        self.assertEqual(first["limit_seconds"], 60)
        started_raw = attempt.question_timing[str(q.id)]
        # Təkrar siqnal (slide-a qayıdış / reload / ikinci tab) timer-i sıfırlamır.
        again = mark_question_seen(attempt, q)
        self.assertEqual(attempt.question_timing[str(q.id)], started_raw)
        self.assertLessEqual(again["remaining_seconds"], first["remaining_seconds"])

    def test_no_limit_records_nothing(self):
        q = self._question(time_limit=None)
        attempt = self._attempt(q)
        info = mark_question_seen(attempt, q)
        self.assertIsNone(info["limit_seconds"])
        self.assertEqual(attempt.question_timing, {})
        self.assertFalse(question_timer_expired(attempt, q))

    def test_expired_only_after_limit_plus_grace(self):
        q = self._question(time_limit=60)
        attempt = self._attempt(q)
        mark_question_seen(attempt, q)
        self.assertFalse(question_timer_expired(attempt, q))
        # limit + grace keçib → expired.
        self._expire_question(attempt, q, seconds_ago=60 + 10 + 5)
        self.assertTrue(question_timer_expired(attempt, q))

    def test_never_seen_question_not_expired(self):
        q = self._question(time_limit=60)
        attempt = self._attempt(q)
        self.assertFalse(question_timer_expired(attempt, q))


class QuestionSeenEndpointTests(QuestionTimerTestBase):
    def _seen_url(self, attempt):
        return reverse("exams:question_seen", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})

    def test_endpoint_marks_and_returns_remaining(self):
        q = self._question(time_limit=45)
        attempt = self._attempt(q)
        _login_with_org(self.client, self.student, self.org)
        response = self.client.post(self._seen_url(attempt), {"question_id": q.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["limit_seconds"], 45)
        self.assertLessEqual(payload["remaining_seconds"], 45)
        attempt.refresh_from_db()
        self.assertIn(str(q.id), attempt.question_timing)

    def test_endpoint_rejects_foreign_attempt(self):
        q = self._question(time_limit=45)
        attempt = self._attempt(q)
        other = User.objects.create_user("qt_other", "qt_other@example.com", "pw")
        _assign_user_to_org(other, self.org, ProfileRole.STUDENT)
        _login_with_org(self.client, other, self.org)
        response = self.client.post(self._seen_url(attempt), {"question_id": q.id})
        self.assertEqual(response.status_code, 404)

    def test_endpoint_rejects_question_outside_attempt(self):
        q = self._question(time_limit=45)
        stray = self._question(order=2, time_limit=45)
        attempt = self._attempt(q)  # stray çatdırılmayıb
        _login_with_org(self.client, self.student, self.org)
        response = self.client.post(self._seen_url(attempt), {"question_id": stray.id})
        self.assertEqual(response.status_code, 404)

    def test_endpoint_rejects_finished_attempt(self):
        q = self._question(time_limit=45)
        attempt = self._attempt(q)
        attempt.status = "submitted"
        attempt.finished_at = timezone.now()
        attempt.save(update_fields=["status", "finished_at"])
        _login_with_org(self.client, self.student, self.org)
        response = self.client.post(self._seen_url(attempt), {"question_id": q.id})
        self.assertEqual(response.status_code, 409)


class ExpiredQuestionSaveEnforcementTests(QuestionTimerTestBase):
    def _take_url(self, attempt):
        return reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})

    def _autosave(self, attempt, question, option):
        return self.client.post(
            self._take_url(attempt),
            {
                "submit_action": "autosave",
                f"q_{question.id}": str(option.id),
                "changed_questions[]": [str(question.id)],
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_expired_question_write_is_dropped(self):
        q = self._question(time_limit=30)
        attempt = self._attempt(q)
        self._expire_question(attempt, q, seconds_ago=300)
        _login_with_org(self.client, self.student, self.org)
        option = q.options.filter(is_correct=True).first()
        response = self._autosave(attempt, q, option)
        self.assertEqual(response.status_code, 200)
        answer = attempt.answers.get(question=q)
        # Yazı SAXLANMADI — müddət server tərəfdə bitib.
        self.assertEqual(set(answer.selected_options.all()), set())

    def test_within_limit_write_is_saved(self):
        q = self._question(time_limit=300)
        attempt = self._attempt(q)
        mark_question_seen(attempt, q)
        _login_with_org(self.client, self.student, self.org)
        option = q.options.filter(is_correct=True).first()
        response = self._autosave(attempt, q, option)
        self.assertEqual(response.status_code, 200)
        answer = attempt.answers.get(question=q)
        self.assertEqual({opt.id for opt in answer.selected_options.all()}, {option.id})

    def test_unseen_question_write_is_saved_backward_compat(self):
        # Siqnal göndərməyən köhnə client: started_at yoxdur → bloklanmır.
        q = self._question(time_limit=30)
        attempt = self._attempt(q)
        _login_with_org(self.client, self.student, self.org)
        option = q.options.filter(is_correct=True).first()
        response = self._autosave(attempt, q, option)
        self.assertEqual(response.status_code, 200)
        answer = attempt.answers.get(question=q)
        self.assertEqual({opt.id for opt in answer.selected_options.all()}, {option.id})
