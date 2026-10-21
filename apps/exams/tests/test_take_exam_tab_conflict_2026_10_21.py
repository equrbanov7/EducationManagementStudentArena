"""2026-10-21 (sahib, zal imtahanı): tək tabda yalançı «başqa tabda yenilənib» konflikti.

Kök səbəb: eyni tabın iki POST-u (fonda autosave + «Qaralama saxla»/«Bitir») eyni
``autosave_revision`` ilə gedirdi; ikincisi 409 alırdı və tab donurdu. Server indi aradakı
yazıların hamısı EYNİ writer-indirsə (``autosave_writer`` + artan ``autosave_seq``) yazını
qəbul edir; başqa writer-in yazısı arada olubsa 409 qalır (çox-tab qoruması). Klient 409-dan
sonra ``answers-state`` ilə sinxronlaşır (tests/js/take_exam_tab_conflict.test.js).
"""

import json
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.option_tokens import option_token
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import _make_people
from apps.exams.tests.test_views import _login_with_org
from apps.exams.views.student import _autosave_writer

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
WRITER = "tabwriterAAAA0001"
OTHER = "tabwriterBBBB0002"


@override_settings(CACHES=LOCMEM)
class _Base(TestCase):
    exam_type = "written"

    def setUp(self):
        cache.clear()
        self.org, self.teacher, self.student = _make_people(f"tab{self.exam_type[:2]}")
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="Tab conflict",
            exam_type=self.exam_type,
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
        )
        self.exam.allowed_users.add(self.student)
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Bir", points=1)
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="İki", points=1)
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q1)
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q2)
        _login_with_org(self.client, self.student, self.org)
        self.url = reverse("exams:take_exam", args=[self.exam.slug, self.attempt.id])
        self.state_url = reverse("exams:take_exam_answers_state", args=[self.exam.slug, self.attempt.id])

    def post(self, action="autosave", *, base, writer=WRITER, seq=1, **answers):
        payload = {"submit_action": action, "autosave_revision": str(base)}
        if writer:
            payload["autosave_writer"] = writer
            payload["autosave_seq"] = str(seq)
        if action == "autosave":
            payload["changed_questions[]"] = [str(qid) for qid in answers]
        for qid, value in answers.items():
            payload[f"q_{qid}"] = value
        if action != "autosave":
            for question in (self.q1, self.q2):
                payload[f"q_present_{question.id}"] = "1"
        return self.client.post(self.url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def text(self, question):
        return ExamAnswer.objects.get(attempt=self.attempt, question=question).text_answer


class SameTabOverlapTests(_Base):
    def test_save_draft_overlapping_an_autosave_of_the_same_tab_is_not_a_conflict(self):
        """REPRO: autosave (base 0) yazılıb, eyni tabın «Qaralama saxla»-sı da base 0 ilə gəlir."""
        first = self.post(base=0, seq=1, **{str(self.q1.id): "bir"})
        self.assertEqual(first.json()["server_revision"], 1)
        draft = self.post("save_draft", base=0, seq=2, **{str(self.q1.id): "bir!", str(self.q2.id): "iki"})
        self.assertEqual(draft.status_code, 200, draft.content[:300])
        self.assertEqual(draft.json()["server_revision"], 2)
        self.assertEqual((self.text(self.q1), self.text(self.q2)), ("bir!", "iki"))

    def test_finish_after_a_lost_autosave_response_submits_everything(self):
        self.post(base=0, seq=1, **{str(self.q1.id): "bir"})  # cavab klientə çatmayıb
        self.post(base=0, seq=2, **{str(self.q2.id): "iki"})  # növbəti autosave hələ base 0 ilə
        finish = self.post("finish", base=0, seq=3, **{str(self.q1.id): "bir", str(self.q2.id): "iki"})
        self.assertEqual(finish.status_code, 200, finish.content[:300])
        self.assertTrue(finish.json()["finished"])
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_finished)

    def test_an_older_delayed_request_of_the_same_tab_does_not_clobber_newer_data(self):
        """Reload-dan əvvəlki səhifənin gecikmiş sorğusu (kiçik seq) tabın yeni yazısını əzmir."""
        self.post(base=0, seq=5, **{str(self.q1.id): "yeni"})
        stale = self.post(base=0, seq=4, **{str(self.q1.id): "köhnə"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.text(self.q1), "yeni")

    def test_replay_fingerprint_ignores_writer_and_seq(self):
        self.post(base=0, writer="", **{str(self.q1.id): "bir"})
        retry = self.post(base=0, seq=9, **{str(self.q1.id): "bir"})
        self.assertEqual(retry.status_code, 200, retry.content[:300])


class RealSecondTabTests(_Base):
    def test_a_different_tab_with_a_stale_base_still_gets_409_with_reason(self):
        self.post(base=0, writer=OTHER, **{str(self.q1.id): "digər tab"})
        stale = self.post(base=0, **{str(self.q1.id): "bu tab"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["reason"], "foreign_writer")
        self.assertEqual(self.text(self.q1), "digər tab")

    def test_own_streak_interrupted_by_another_tab_is_a_conflict(self):
        self.post(base=0, seq=1, **{str(self.q1.id): "a"})
        self.post(base=1, writer=OTHER, seq=1, **{str(self.q2.id): "digər"})
        self.post(base=2, seq=2, **{str(self.q1.id): "b"})
        stale = self.post(base=1, seq=3, **{str(self.q2.id): "bu tab"})
        self.assertEqual(stale.status_code, 409, "base 1-dən sonra digər tabın yazısı var")
        self.assertEqual(self.text(self.q2), "digər")

    def test_legacy_client_without_writer_keeps_strict_occ(self):
        self.post(base=0, writer="", **{str(self.q1.id): "bir"})
        stale = self.post(base=0, writer="", **{str(self.q1.id): "başqa"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["reason"], "unknown")

    def test_lost_writer_record_falls_back_to_strict_409(self):
        self.post(base=0, seq=1, **{str(self.q1.id): "bir"})
        cache.clear()
        self.assertEqual(self.post(base=0, seq=2, **{str(self.q1.id): "iki"}).status_code, 409)


class AnswersStateEndpointTests(_Base):
    def test_returns_revision_writer_and_text_answers(self):
        self.post(base=0, **{str(self.q1.id): "  cavab  "})
        response = self.client.get(self.state_url, {"q": f"{self.q1.id},{self.q2.id}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["server_revision"], 1)
        self.assertEqual(data["writer"], WRITER)
        self.assertEqual(data["answers"], {str(self.q1.id): "cavab", str(self.q2.id): ""})

    def test_other_students_attempt_is_404(self):
        other = ExamAttempt.objects.create(user=self.teacher, exam=self.exam, status="in_progress", attempt_number=1)
        url = reverse("exams:take_exam_answers_state", args=[self.exam.slug, other.id])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_finished_attempt_reports_finished(self):
        self.attempt.mark_finished(status="submitted")
        data = self.client.get(self.state_url).json()
        self.assertTrue(data["finished"])
        self.assertNotIn("answers", data)

    def test_take_page_renders_writer_state_and_sync_url(self):
        self.post(base=0, **{str(self.q1.id): "bir"})
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn(f'data-answers-state-url="{self.state_url}"', html)
        self.assertIn(f'data-writer="{WRITER}"', html)
        self.assertIn('data-writer-since="0"', html)
        self.assertIn("take_exam/writer.js", html)
        self.assertIn("take_exam/resync.js", html)


class AnswersStateTestExamTests(_Base):
    exam_type = "test"

    def setUp(self):
        super().setUp()
        for question in (self.q1, self.q2):
            question.answer_mode = "single"
            question.save(update_fields=["answer_mode"])
        self.options = {
            question.id: [
                ExamQuestionOption.objects.create(question=question, label=label, text=label, is_correct=label == "A")
                for label in ("A", "B")
            ]
            for question in (self.q1, self.q2)
        }

    def test_selected_options_are_returned_as_page_tokens_with_bounded_queries(self):
        chosen = self.options[self.q1.id][1]
        token = option_token(self.attempt.id, chosen.id)
        self.assertEqual(self.post(base=0, **{str(self.q1.id): token}).status_code, 200)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.state_url, {"q": f"{self.q1.id},{self.q2.id}"})
        data = json.loads(response.content)
        self.assertEqual(data["answers"], {str(self.q1.id): token, str(self.q2.id): ""})
        self.assertLessEqual(len(queries), 12, [q["sql"] for q in queries.captured_queries])


class CenterExamSecondTabTests(_Base):
    """2026-10-21 (sahib): zal (final/midterm) imtahanında HƏQİQİ ikinci tab heç yaza bilmir."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.exams.services.center_exams.is_center_exam", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_second_tab_cannot_write_even_with_the_current_revision(self):
        self.assertEqual(self.post(base=0, **{str(self.q1.id): "birinci tab"}).status_code, 200)
        second = self.post(base=1, writer=OTHER, **{str(self.q1.id): "ikinci tab"})
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["reason"], "foreign_writer")
        self.assertEqual(self.text(self.q1), "birinci tab")
        self.assertEqual(self.post(base=1, seq=2, **{str(self.q2.id): "davam"}).status_code, 200, "first tab works")

    def test_same_tab_draft_and_finish_overlap_never_conflict(self):
        self.post(base=0, seq=1, **{str(self.q1.id): "bir"})
        self.assertEqual(self.post("save_draft", base=0, seq=2, **{str(self.q1.id): "bir"}).status_code, 200)
        finish = self.post("finish", base=1, seq=3, **{str(self.q1.id): "bir", str(self.q2.id): "iki"})
        self.assertEqual(finish.status_code, 200, finish.content[:300])
        self.assertTrue(finish.json()["finished"])

    def test_lease_expires_so_a_new_computer_after_reentry_can_write(self):
        self.post(base=0, **{str(self.q1.id): "köhnə kompüter"})
        with mock.patch.object(_autosave_writer, "CENTER_OWNER_LEASE_SECONDS", -1):
            fresh = self.post(base=1, writer=OTHER, **{str(self.q1.id): "yeni kompüter"})
        self.assertEqual(fresh.status_code, 200, fresh.content[:300])
        self.assertEqual(self.text(self.q1), "yeni kompüter")

    def test_legacy_client_without_writer_is_not_affected_by_the_lease(self):
        self.post(base=0, **{str(self.q1.id): "bir"})
        self.assertEqual(self.post(base=1, writer="", **{str(self.q1.id): "köhnə JS"}).status_code, 200)


class NonCenterExamSecondTabTests(_Base):
    def test_other_writer_with_current_revision_is_accepted_outside_the_hall(self):
        self.post(base=0, **{str(self.q1.id): "bir"})
        self.assertEqual(self.post(base=1, writer=OTHER, **{str(self.q2.id): "iki"}).status_code, 200)
