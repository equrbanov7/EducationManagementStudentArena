"""Yazılmış, amma cavabı klientə çatmamış autosave-in təkrarı 409 vermir (tutum testi 2026-10-05)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import _make_people
from apps.exams.tests.test_views import _login_with_org


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class AutosaveReplayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org, self.teacher, self.student = _make_people("replay")
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="Replay Written",
            exam_type="written",
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
        )
        self.exam.allowed_users.add(self.student)
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Yaz", points=1)
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.question)
        _login_with_org(self.client, self.student, self.org)
        self.url = reverse("exams:take_exam", args=[self.exam.slug, self.attempt.id])

    def _save(self, text, revision):
        return self.client.post(
            self.url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(self.question.id)],
                f"q_{self.question.id}": text,
                "autosave_revision": str(revision),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_identical_retry_after_lost_response_succeeds_without_new_write(self):
        first = self._save("cavab", 0)
        self.assertEqual(first.json()["server_revision"], 1)
        retry = self._save("cavab", 0)  # cavab itib — klient köhnə revision ilə təkrarlayır
        self.assertEqual(retry.status_code, 200, retry.content[:200])
        self.assertEqual(retry.json()["server_revision"], 1)
        self.assertTrue(retry.json()["replayed"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.autosave_revision, 1)

    def test_different_content_from_stale_revision_still_conflicts(self):
        self._save("cavab", 0)
        stale = self._save("başqa tab", 0)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(ExamAnswer.objects.get(attempt=self.attempt).text_answer, "cavab")

    def test_two_revisions_behind_still_conflicts(self):
        self._save("bir", 0)
        self._save("iki", 1)
        self.assertEqual(self._save("iki", 0).status_code, 409)

    # Review 2026-10-07: barmaq izi yalnız `q_*` + `changed_questions[]` idi — eyni mətnli,
    # amma FƏRQLİ rəsmli (`paint_data_*`) və ya fərqli işarəli (`marked_question_ids`) təkrar
    # «replay» sayılıb yazısız 200 alırdı → klient «saxlandı» görür, yeni rəsm/işarə itirdi.

    def _save_with(self, revision, **extra):
        payload = {
            "submit_action": "autosave",
            "changed_questions[]": [str(self.question.id)],
            f"q_{self.question.id}": "cavab",
            "autosave_revision": str(revision),
        }
        payload.update(extra)
        return self.client.post(self.url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_same_text_but_different_drawing_is_not_replayed(self):
        paint = {f"paint_enabled_{self.question.id}": "1"}
        first = self._save_with(0, **paint, **{f"paint_data_{self.question.id}": "data:image/png;base64,QUFB"})
        self.assertEqual(first.status_code, 200, first.content[:200])
        retry = self._save_with(0, **paint, **{f"paint_data_{self.question.id}": "data:image/png;base64,QkJC"})
        self.assertEqual(retry.status_code, 409, "fərqli rəsm replay kimi yazısız qəbul olunmamalıdır")

    def test_same_answers_but_different_marks_are_not_replayed(self):
        first = self._save_with(0, marked_question_ids="[]")
        self.assertEqual(first.status_code, 200, first.content[:200])
        retry = self._save_with(0, marked_question_ids=f"[{self.question.id}]")
        self.assertEqual(retry.status_code, 409, "fərqli işarələr replay kimi yazısız qəbul olunmamalıdır")

    def test_identical_retry_with_meta_fields_still_replays(self):
        meta = {"return_to": "/accounts/profile/", "csrfmiddlewaretoken": "x", "marked_question_ids": "[]"}
        self.assertEqual(self._save_with(0, **meta).status_code, 200)
        retry = self._save_with(0, **{**meta, "csrfmiddlewaretoken": "y"})
        self.assertEqual(retry.status_code, 200, retry.content[:200])
        self.assertTrue(retry.json()["replayed"])
