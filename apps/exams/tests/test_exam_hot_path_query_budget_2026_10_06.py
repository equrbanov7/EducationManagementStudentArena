"""Perf 2026-10-06 — imtahan qaynar yolunun sorğu büdcəsi (1000 eyni-anlı tələbə yük testi).

Yük testində autosave DB-ni doyururdu. Ölçü (``config.settings.test``, 5 suallıq MCQ
quiz; saya hər sorğuda ~9 middleware sorğusu da daxildir — session/user/profile/
Membership/RLS, bu dalğada toxunulmayıb):

=====================================  =====  =====
endpoint                               əvvəl  sonra
=====================================  =====  =====
start POST (yeni cəhd)                    43     38
suallar səhifəsi GET                      28     25
autosave POST (1 MCQ, marked «[]»)        26     19
finish POST (5 MCQ: 3 düz + 2 səhv)       42     28
=====================================  =====  =====

Büdcələr yuxarı həddir (middleware-in sonrakı azalmaları testi sındırmır); struktur
yoxlamaları isə konkret təkrarların geri qayıtmamasını təsdiqləyir: attempt POST-da
bir dəfə (kilid altında) yüklənir, exclusion ayrıca sorğu deyil, müəllif/fayl/
nəzarət-konfiqi sorğuları yoxdur, revision ``UPDATE … RETURNING`` ilə artır.
Semantika testləri tək kilidli yolun köhnə zəmanətlərini (exclusion, deaktiv
imtahan, final-mərkəz giriş sessiyası, «resumed», bitmiş cəhd) yoxlayır.
"""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import _make_people, _make_quiz
from apps.exams.tests.test_views import _login_with_org

START_BUDGET = 38
QUESTIONS_PAGE_BUDGET = 25
AUTOSAVE_BUDGET = 19
# 3 düz + 2 səhv: `TestAnswerWriteBatch` iki sahə dəsti üçün iki bulk UPDATE edir.
FINISH_BUDGET = 28


def _sqls(ctx):
    return [q["sql"] for q in ctx.captured_queries]


def _attempt_selects(sqls):
    return [s for s in sqls if s.startswith("SELECT") and 'FROM "exams_examattempt"' in s]


class _HotPathBase(TestCase):
    def setUp(self):
        self.org, self.teacher, self.student = _make_people("hotpath")
        self.exam = _make_quiz(self.org, self.teacher, n_questions=5)
        _login_with_org(self.client, self.student, self.org)

    def _start(self):
        response = self.client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 302)
        self.attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        self.take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        self.questions = list(self.exam.questions.order_by("order"))
        return response

    def _autosave_payload(self, question, label="A", revision=0):
        # Brauzerin real autosave gövdəsi (draft.js): «marked_question_ids» hər dəfə gedir.
        return {
            "submit_action": "autosave",
            "changed_questions[]": [str(question.id)],
            f"q_{question.id}": option_value(self.attempt, question.options.get(label=label)),
            "marked_question_ids": "[]",
            "autosave_revision": str(revision),
        }

    def _post(self, payload):
        return self.client.post(self.take_url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def _autosave(self, question, label="A", revision=0):
        return self._post(self._autosave_payload(question, label, revision))


class ExamHotPathQueryBudgetTests(_HotPathBase):
    def test_start_budget(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExamAttempt.objects.filter(exam=self.exam, user=self.student, status="in_progress").exists())
        sqls = _sqls(ctx)
        self.assertLessEqual(len(sqls), START_BUDGET, "\n".join(sqls))
        # Müəllif obyekti (`user == exam.author`) və fənnsiz imtahanın təşkilatı yüklənmir.
        self.assertFalse(
            [s for s in sqls if 'FROM "auth_user"' in s and f'"auth_user"."id" = {self.teacher.pk}' in s],
            "exam.author ayrıca yüklənir",
        )
        self.assertFalse([s for s in sqls if 'FROM "organizations_organization"' in s])

    def test_questions_page_budget(self):
        self._start()
        self.client.get(self.take_url)  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.take_url)
        self.assertEqual(response.status_code, 200)
        sqls = _sqls(ctx)
        self.assertLessEqual(len(sqls), QUESTIONS_PAGE_BUDGET, "\n".join(sqls))
        # Test imtahanında cavab faylları göstərilmir; nəzarət konfiqi və exclusion attempt SELECT-indədir.
        self.assertFalse([s for s in sqls if 'FROM "exams_examanswerfile"' in s])
        self.assertFalse([s for s in sqls if s.startswith('SELECT "exams_examsupervisionconfig"')])
        self.assertFalse([s for s in sqls if s.startswith("SELECT 1") and "exams_exam_excluded_users" in s])
        self.assertEqual(len(response.context["answers_by_qid"]), 5)

    def test_autosave_single_mcq_budget(self):
        self._start()
        question = self.questions[0]
        payload = self._autosave_payload(question)
        with CaptureQueriesContext(connection) as ctx:
            response = self._post(payload)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["server_revision"], 1)
        sqls = _sqls(ctx)
        self.assertLessEqual(len(sqls), AUTOSAVE_BUDGET, "\n".join(sqls))

        attempt_selects = _attempt_selects(sqls)
        self.assertEqual(len(attempt_selects), 1, "attempt POST-da bir dəfə yüklənməlidir")
        locked = attempt_selects[0]
        self.assertIn('FOR UPDATE OF "exams_examattempt"', locked)
        self.assertIn("exams_exam_excluded_users", locked, "exclusion eyni SELECT-də EXISTS olmalıdır")
        self.assertEqual(sum("exams_exam_excluded_users" in s for s in sqls), 1)
        lock_index = sqls.index(locked)
        self.assertFalse([s for s in sqls[lock_index:] if 'FROM "auth_user"' in s], "müəllif/istifadəçi yüklənir")
        self.assertFalse([s for s in sqls if 'FROM "exams_examanswerfile"' in s])
        self.assertTrue([s for s in sqls if "RETURNING" in s and "autosave_revision" in s])

        answer = ExamAnswer.objects.get(attempt=self.attempt, question=question)
        self.assertEqual(answer.selected_option_ids_snapshot, [question.options.get(label="A").pk])
        self.assertTrue(answer.is_correct)

    def test_finish_budget_and_result(self):
        self._start()
        self.assertEqual(self._autosave(self.questions[0]).status_code, 200)
        payload = {"submit_action": "finish", "autosave_revision": "1", "marked_question_ids": "[]"}
        for index, question in enumerate(self.questions):
            label = "A" if index < 3 else "B"
            payload[f"q_{question.id}"] = option_value(self.attempt, question.options.get(label=label))
            payload[f"q_present_{question.id}"] = "1"
        with CaptureQueriesContext(connection) as ctx:
            response = self._post(payload)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["finished"])
        sqls = _sqls(ctx)
        self.assertLessEqual(len(sqls), FINISH_BUDGET, "\n".join(sqls))
        self.assertEqual(len(_attempt_selects([s for s in sqls if "FOR UPDATE" in s])), 1)
        self.assertEqual(sum(s.startswith('SELECT "exams_examanswer"."id"') for s in sqls), 1, "cavablar 2 dəfə")
        finish_updates = [s for s in sqls if s.startswith('UPDATE "exams_examattempt"') and '"status"' in s]
        self.assertEqual(len(finish_updates), 1)
        self.assertIn('"correct_count"', finish_updates[0])

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "submitted")
        self.assertEqual((self.attempt.correct_count, self.attempt.wrong_count), (3, 2))
        self.assertEqual(self.attempt.autosave_revision, 2)


class LockedPostGuaranteeTests(_HotPathBase):
    """Tək kilidli POST yolu köhnə iki-mərhələli yoxlamanın hər zəmanətini saxlayır."""

    def setUp(self):
        super().setUp()
        self._start()
        self.question = self.questions[0]

    def _assert_nothing_written(self):
        answer = ExamAnswer.objects.get(attempt=self.attempt, question=self.question)
        self.assertIsNone(answer.selected_option_ids_snapshot)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.autosave_revision, 0)

    def test_excluded_student_autosave_is_forbidden(self):
        self.exam.excluded_users.add(self.student)
        response = self._autosave(self.question)
        self.assertEqual(response.status_code, 403)
        self._assert_nothing_written()

    def test_deactivated_exam_autosave_is_forbidden(self):
        self.exam.is_active = False
        self.exam.save(update_fields=["is_active"])
        response = self._autosave(self.question)
        self.assertEqual(response.status_code, 403)
        self._assert_nothing_written()

    def test_revoked_final_entry_session_logs_out_outside_the_transaction(self):
        with patch("apps.exams.services.final_center.final_attempt_entry_session_valid", return_value=False):
            response = self._autosave(self.question)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)
        self._assert_nothing_written()

    def test_resumed_supervision_state_is_cleared_and_write_accepted(self):
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(supervision_status="resumed")
        response = self._autosave(self.question)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.supervision_status, "active")
        self.assertEqual(self.attempt.autosave_revision, 1)

    def test_finished_attempt_autosave_returns_already_finished(self):
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(status="submitted")
        response = self._autosave(self.question)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["already_finished"])
        self._assert_nothing_written()

    def test_marked_question_ids_are_still_validated(self):
        other = self.questions[1]
        response = self.client.post(
            self.take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(self.question.id)],
                f"q_{self.question.id}": option_value(self.attempt, self.question.options.get(label="A")),
                "marked_question_ids": f"[{other.id}, 999999, {other.id}]",
                "autosave_revision": "0",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.marked_question_ids, [other.id])
