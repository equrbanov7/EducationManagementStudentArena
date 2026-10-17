"""Paket D (2026-10-17) — imtahan günü səhifələrinin redizaynı: sorğu büdcəsi + selektor qoruyucusu.

Redizayn yalnız şablon/CSS-dir (imtahan mərkəzi başlığı `ems-header`/`ems-crumbs`, hex → `--ems-*`
tokenləri; imtahan yazma səhifələri YALNIZ rəng/keş versiyası). Bu testlər:

* hər dəyişən səhifənin sorğu sayının redizayndan əvvəlki ölçüdən artmadığını (``config.settings.test``,
  isinmədən sonra; middleware sorğuları daxil),
* 30 s-lik zal monitoru snapshot-unun aktiv tələbə sayından ASILI OLMADIĞINI (sabit sorğu sayı),
* `take_exam` JS-inin (`take_exam/*.js`, `exam_supervision/*`, vaxt xəbərdarlığı) oxuduğu id/data
  çəngəllərinin render olunmuş səhifədə qaldığını yoxlayır.

=========================  =====  =====
səhifə                     əvvəl  sonra
=========================  =====  =====
room_list                     21     21
room_monitor                  32     32
room snapshot (JSON)          19     19
session_monitor               23     23
session snapshot (JSON)       15     15
session_detail                17     17
session_history               19     19
reports                       20     20
final entry (anonim)           1      1
final entry (PIN-dən sonra)   13     13
final waiting                 12     12
start confirm                 23     23
take_exam (5 MCQ)             21     21
=========================  =====  =====
"""

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.exams.models import ExamAttempt, FinalExamTicket
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, set_ticket_pin, start_room
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import _make_people, _make_quiz
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.exams.tests.test_views import _login_with_org

BUDGETS = {
    "room_list": 21,
    "room_monitor": 32,
    "room_snapshot": 19,
    "session_monitor": 23,
    "session_snapshot": 15,
    "session_detail": 17,
    "session_history": 19,
    "reports": 20,
    "final_entry_anon": 1,
    "final_entry_gate": 13,
    "final_waiting": 12,
    "start_confirm": 23,
    "take_exam": 21,
}

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

# take_exam.html-də statik olan və JS-in getElementById ilə oxuduğu id-lər (2026-10-17 grep).
TAKE_EXAM_JS_IDS = (
    "answered-count",
    "autosave-revision-field",
    "cancelFinishBtn",
    "confirmFinishBtn",
    "current-question-num",
    "exam-form",
    "exam-sync-status",
    "exam-timer-container",
    "exam-timer-pill",
    "examLoadingScreen",
    "examTimeWarningModal",
    "finish-btn",
    "finishConfirmBackdrop",
    "finishConfirmSummary",
    "marked-question-ids-field",
    "next-btn",
    "prev-btn",
    "progress-fill",
    "question-timer-container",
    "question-timer-value",
    "questionTransitionSkeleton",
    "save-draft-btn",
    "sidebar-answered-count",
    "timer-value",
    "unanswered-count",
)
TAKE_EXAM_JS_HOOKS = (
    "data-question-nav",
    "data-mark-question",
    "data-mark-label",
    "data-pill-q",
    "data-pill-q-value",
    "data-pill-exam",
    "data-pill-exam-value",
    "data-exam-time-warning-close",
    "data-autosave-revision",
    "data-question-seen-url",
    'class="question-slide',
    'class="timer-strip"',
)


def _per_ticket_exam_lookups(sqls):
    return sum(1 for sql in sqls if 'FROM "exams_exam" WHERE "exams_exam"."id" = ' in sql)


def _count(client, url, **extra):
    client.get(url, **extra)  # isinmə (keş, sessiya)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, **extra)
    return response, len(ctx.captured_queries), [q["sql"] for q in ctx.captured_queries]


class ExamCentreBudgetTests(_FlowBase):
    def _assert_budget(self, key, client, url, **extra):
        response, count, sqls = _count(client, url, **extra)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertLessEqual(count, BUDGETS[key], f"{key}: {count} sorğu\n" + "\n".join(sqls))
        return response

    def _live(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)

    def test_room_list_and_reports_budget(self):
        center = self._client_for(self.center)
        response = self._assert_budget("room_list", center, reverse("exams:exam_center_room_list"))
        self.assertContains(response, 'class="ems-crumbs"')
        response = self._assert_budget("reports", center, reverse("exams:exam_center_reports"))
        self.assertContains(response, "ems-header fxc-header")

    def test_monitor_pages_budget(self):
        self._live()
        center = self._client_for(self.center)
        response = self._assert_budget(
            "room_monitor", center, reverse("exams:exam_center_room_monitor", kwargs={"room_id": self.room.pk})
        )
        # JS müqaviləsi: id-lər + ilk render qarşılıqlı-istisna düymələr (test_final_center_flow ilə eyni).
        for marker in ('id="fxc-room-root"', 'id="fxc-room-ws"', 'id="fxc-room-updated"', 'id="fxc-room-sessions"'):
            self.assertContains(response, marker)
        self.assertContains(response, 'id="fxc-start-all-btn">')
        self.assertContains(response, 'id="fxc-end-all-btn" hidden>')
        self._assert_budget(
            "room_snapshot",
            center,
            reverse("exams:exam_center_room_snapshot", kwargs={"room_id": self.room.pk}),
            **AJAX,
        )
        response = self._assert_budget(
            "session_monitor",
            center,
            reverse("exams:exam_center_session_monitor", kwargs={"session_id": self.session.pk}),
        )
        for marker in ('id="fxc-monitor-root"', 'id="fxc-state-pill"', 'id="fxc-ws-state"', 'id="fxc-server-time"'):
            self.assertContains(response, marker)
        self._assert_budget(
            "session_snapshot",
            center,
            reverse("exams:exam_center_session_snapshot", kwargs={"session_id": self.session.pk}),
            **AJAX,
        )
        self._assert_budget(
            "session_detail",
            center,
            reverse("exams:exam_center_session_detail", kwargs={"session_id": self.session.pk}),
        )
        self._assert_budget(
            "session_history",
            center,
            reverse("exams:exam_center_session_history", kwargs={"session_id": self.session.pk}),
        )

    def test_room_snapshot_query_count_is_constant(self):
        """30 s-lik poll: ikinci aktiv tələbə əlavə olunanda sorğu sayı dəyişmir.

        2026-10-18: `room_monitor_snapshot` bilet sorğusuna `attempt__exam` əlavə olundu (sessiya snapshot-u kimi) —
        aktiv bilet başına `exams_exam WHERE id = …` sorğusu artıq YOXDUR.
        """
        self._live()
        center = self._client_for(self.center)
        url = reverse("exams:exam_center_room_snapshot", kwargs={"room_id": self.room.pk})
        _, one, sqls_one = _count(center, url, **AJAX)

        ticket2 = FinalExamTicket.objects.create(
            organization=self.org, session=self.session, exam=self.exam, student=self.student2
        )
        set_ticket_pin(ticket2, self.center)
        enter_waiting(ticket2, language="")
        begin_attempt_for_ticket(ticket2)
        response, two, sqls_two = _count(center, url, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["active"], 2)
        lookups_one, lookups_two = _per_ticket_exam_lookups(sqls_one), _per_ticket_exam_lookups(sqls_two)
        self.assertEqual((lookups_one, lookups_two), (0, 0), "\n".join(sqls_two))
        self.assertEqual(one, two, "\n".join(sqls_two))

    def test_final_entry_and_waiting_budget(self):
        self._assert_budget("final_entry_anon", Client(), reverse("exams:final_exam_entry"))
        student, _ = self._entry_client()
        self._assert_budget("final_entry_gate", student, reverse("exams:final_exam_entry"))
        enter_waiting(self.ticket, language="")
        response = self._assert_budget(
            "final_waiting", student, reverse("exams:final_exam_waiting", kwargs={"ticket_id": self.ticket.pk})
        )
        for marker in (
            'id="fexc-waiting-root"',
            'id="fexc-wait-message"',
            'id="fexc-conn-state"',
            'id="fexc-manual-start"',
        ):
            self.assertContains(response, marker)


class TakeExamSkinGuardTests(TestCase):
    def setUp(self):
        self.q_org, teacher, self.q_student = _make_people("pkgd")
        self.quiz = _make_quiz(self.q_org, teacher, n_questions=5)
        self.client = Client()
        _login_with_org(self.client, self.q_student, self.q_org)

    def test_start_confirm_budget(self):
        url = reverse("exams:start_exam", kwargs={"slug": self.quiz.slug})
        response, count, sqls = _count(self.client, url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/student/exam_start_confirm.html")
        self.assertLessEqual(count, BUDGETS["start_confirm"], "\n".join(sqls))
        # Forma eyni URL-ə POST edir (EXAMQA R1) — dəyişməyib.
        self.assertContains(response, 'method="post"')
        self.assertContains(response, "exam-start-confirm__tips")

    def test_take_exam_budget_and_js_hooks_preserved(self):
        self.client.post(reverse("exams:start_exam", kwargs={"slug": self.quiz.slug}))
        attempt = ExamAttempt.objects.get(exam=self.quiz, user=self.q_student)
        url = reverse("exams:take_exam", kwargs={"slug": self.quiz.slug, "attempt_id": attempt.id})
        response, count, sqls = _count(self.client, url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(count, BUDGETS["take_exam"], "\n".join(sqls))
        html = response.content.decode()
        missing = [i for i in TAKE_EXAM_JS_IDS if f'id="{i}"' not in html]
        self.assertEqual(missing, [], "take_exam JS-in oxuduğu id-lər itib")
        missing_hooks = [h for h in TAKE_EXAM_JS_HOOKS if h not in html]
        self.assertEqual(missing_hooks, [], "take_exam JS çəngəlləri itib")
