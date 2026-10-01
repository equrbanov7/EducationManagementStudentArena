"""EXAMQA 2026-10-01 — test imtahanı axınının tam analizi (sahib: «bug varmı, MAC ünvan məsələləri»).

Hər sinif bir tapıntının reqressiya testidir:

* ``LegacyStoredMacFormatTests`` — DB-də qeyri-kanonik (kiçik hərf / «-») saxlanmış
  MAC MAC-rejimində heç vaxt uyğun gəlmirdi → qeydli kompüterdəki tələbə kilidlənirdi.
* ``ResolveClientMacTests`` — ARP agentinin cavabının emalı (normallaşma, fail-closed).
* ``SupervisionLockWriteGuardTests`` — nəzarət kilidi yalnız klient overlay-i idi;
  kilidli cəhdə autosave/təhvil server tərəfindən qəbul olunurdu.
* ``AttemptIdorTests`` — başqasının cəhdinə/nəticəsinə/sual siqnalına çıxış yoxdur.
* ``StudentPagesQueryBudgetTests`` — tarixçə və nəticə səhifələrində N+1 yoxdur.
"""

import io
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import (
    ExamAttempt,
    ExamRoom,
    ExamRoomComputer,
    ExamSupervisionConfig,
)
from apps.exams.services.exam_center_gate import (
    org_computer_access_allowed,
    resolve_client_mac,
    resolve_room_computer,
    room_ip_access_allowed,
)
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    _make_org,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org

User = get_user_model()

MAC = "C8:D3:FF:B3:89:50"


class _RoomFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("eqmac")
        cls.room = ExamRoom.objects.create(organization=cls.org, name="EQ Zal", code="EQZ", capacity=10)

    def _raw_computer(self, mac, *, label="PC-01", active=True, room=None):
        # Servis qatını (``add_computer`` normallaşdırması) yan keçən yazı —
        # shell/skript/SQL ilə yaradılmış köhnə sətirləri təqlid edir.
        return ExamRoomComputer.objects.create(
            organization=self.org,
            room=room or self.room,
            label=label,
            mac_address=mac,
            is_active=active,
        )

    def _request(self):
        return RequestFactory().get("/exams/final/", REMOTE_ADDR="10.0.3.66")

    def _client_mac(self, mac):
        return mock.patch("apps.exams.services.exam_center_gate.resolve_client_mac", return_value=mac)


@override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent")
class LegacyStoredMacFormatTests(_RoomFixture):
    def test_lowercase_colon_mac_in_db_matches_every_gate(self):
        computer = self._raw_computer(MAC.lower())
        with self._client_mac(MAC):
            self.assertTrue(room_ip_access_allowed(self._request(), self.room))
            self.assertTrue(org_computer_access_allowed(self._request(), self.org))
            self.assertEqual(resolve_room_computer(self._request(), self.org), (self.room, computer))

    def test_dash_and_dotted_formats_in_db_match(self):
        self._raw_computer(MAC.replace(":", "-").lower(), label="PC-dash")
        other = "AA:BB:CC:DD:EE:0F"
        dotted = self._raw_computer("aabb.ccdd.ee0f", label="PC-dot")
        with self._client_mac(other):
            self.assertEqual(resolve_room_computer(self._request(), self.org), (self.room, dotted))
        with self._client_mac(MAC):
            self.assertTrue(org_computer_access_allowed(self._request(), self.org))

    def test_canonical_rows_still_use_exact_match(self):
        computer = self._raw_computer(MAC)
        with self._client_mac(MAC):
            self.assertEqual(resolve_room_computer(self._request(), self.org), (self.room, computer))

    def test_unregistered_and_inactive_legacy_rows_stay_blocked(self):
        self._raw_computer(MAC.lower(), active=False)
        self._raw_computer("aa:aa:aa:aa:aa:01", label="PC-02")
        with self._client_mac(MAC):
            # Aktiv qeyd var (PC-02), amma client MAC-ı yalnız deaktiv sətirdədir.
            self.assertFalse(room_ip_access_allowed(self._request(), self.room))
            self.assertFalse(org_computer_access_allowed(self._request(), self.org))
            self.assertEqual(resolve_room_computer(self._request(), self.org), (None, None))

    def test_garbage_mac_row_never_matches_and_does_not_crash(self):
        self._raw_computer("not-a-mac")
        with self._client_mac(MAC):
            self.assertFalse(room_ip_access_allowed(self._request(), self.room))
            self.assertEqual(resolve_room_computer(self._request(), self.org), (None, None))

    def test_other_org_legacy_row_is_not_matched(self):
        other_owner = User.objects.create_user("eqmac_other", "eqmac_other@test.az", PASSWORD)
        other_org = _make_org(other_owner, "EQ Other Org")
        other_room = ExamRoom.objects.create(organization=other_org, name="Other", code="OTH", capacity=5)
        ExamRoomComputer.objects.create(organization=other_org, room=other_room, label="X", mac_address=MAC.lower())
        self._raw_computer("aa:aa:aa:aa:aa:02", label="PC-own")
        with self._client_mac(MAC):
            self.assertFalse(org_computer_access_allowed(self._request(), self.org))
            self.assertEqual(resolve_room_computer(self._request(), self.org), (None, None))


class _AgentResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _agent(payload):
    return mock.patch(
        "apps.exams.services.exam_center_gate.urlopen",
        return_value=_AgentResponse(json.dumps(payload).encode()),
    )


@override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent", EXAM_ARP_AGENT_URL="http://172.18.0.1:8953")
class ResolveClientMacTests(TestCase):
    def _request(self, ip="10.0.3.66"):
        return RequestFactory().get("/exams/final/", REMOTE_ADDR=ip)

    def test_agent_mac_is_normalised_and_client_ip_is_queried(self):
        with _agent({"ip": "10.0.3.66", "mac": "c8-d3-ff-b3-89-50"}) as urlopen:
            self.assertEqual(resolve_client_mac(self._request()), MAC)
        called_url = urlopen.call_args.args[0]
        self.assertTrue(called_url.startswith("http://172.18.0.1:8953/mac?"))
        self.assertIn("ip=10.0.3.66", called_url)

    def test_missing_arp_entry_is_fail_closed(self):
        with _agent({"ip": "10.0.3.66", "mac": None}):
            self.assertIsNone(resolve_client_mac(self._request()))

    def test_malformed_agent_mac_is_fail_closed(self):
        with _agent({"mac": "zz:zz"}):
            self.assertIsNone(resolve_client_mac(self._request()))

    def test_agent_timeout_is_fail_closed(self):
        with mock.patch("apps.exams.services.exam_center_gate.urlopen", side_effect=TimeoutError("slow")):
            self.assertIsNone(resolve_client_mac(self._request()))

    def test_unparseable_client_ip_never_calls_agent(self):
        with mock.patch("apps.exams.services.exam_center_gate.get_client_ip", return_value="unknown"):
            with mock.patch("apps.exams.services.exam_center_gate.urlopen") as urlopen:
                self.assertIsNone(resolve_client_mac(self._request()))
        urlopen.assert_not_called()

    @override_settings(EXAM_ARP_AGENT_URL="")
    def test_missing_agent_url_is_fail_closed(self):
        with mock.patch("apps.exams.services.exam_center_gate.urlopen") as urlopen:
            self.assertIsNone(resolve_client_mac(self._request()))
        urlopen.assert_not_called()

    @override_settings(EXAM_CLIENT_MAC_RESOLUTION="off")
    def test_off_mode_never_calls_agent(self):
        with mock.patch("apps.exams.services.exam_center_gate.urlopen") as urlopen:
            self.assertIsNone(resolve_client_mac(self._request()))
        urlopen.assert_not_called()


@override_settings(CACHES=LOCMEM_CACHE, EXAM_SUPERVISION_ENABLED=True)
class SupervisionLockWriteGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("eqlock")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=2, title="EQ Lock")
        ExamSupervisionConfig.objects.create(exam=cls.exam, enabled=True)

    def setUp(self):
        self.client = _student_client("eqlock_student", self.org)
        self.client.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        self.url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.answer = self.attempt.answers.select_related("question").order_by("id").first()
        self.correct = self.answer.question.options.get(is_correct=True)

    def _lock(self, *, manual):
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(
            supervision_status="locked", supervision_locked_at=timezone.now(), supervision_manual_lock=manual
        )

    def _autosave(self):
        return self.client.post(
            self.url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(self.answer.question_id)],
                f"q_{self.answer.question_id}": option_value(self.attempt, self.correct),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_autosave_is_rejected_while_violation_locked(self):
        self._lock(manual=False)
        response = self._autosave()
        self.assertEqual(response.status_code, 423)
        self.assertTrue(response.json()["locked"])
        self.answer.refresh_from_db()
        self.assertEqual(list(self.answer.selected_options.all()), [])

    def test_finish_is_rejected_while_invigilator_suspended(self):
        self._lock(manual=True)
        response = self.client.post(self.url, {"submit_action": "finish"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 423)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "in_progress")

    def test_non_ajax_post_while_locked_redirects_back_without_writing(self):
        self._lock(manual=True)
        response = self.client.post(self.url, {"submit_action": "finish"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_finished)

    def test_writes_resume_after_teacher_resume(self):
        self._lock(manual=True)
        self.assertEqual(self._autosave().status_code, 423)
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(
            supervision_status="resumed", supervision_locked_at=None, supervision_manual_lock=False
        )
        response = self._autosave()
        self.assertEqual(response.status_code, 200)
        self.answer.refresh_from_db()
        self.assertEqual([option.pk for option in self.answer.selected_options.all()], [self.correct.pk])

    def test_expired_resume_window_still_finishes_with_lock_time_answers(self):
        # Kilid pəncərəsi bitibsə cəhd «submitted» olur — guard bunu bloklamır.
        self._lock(manual=False)
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(supervision_locked_at=timezone.now() - timedelta(hours=1))
        response = self._autosave()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["finished"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "submitted")
        self.answer.refresh_from_db()
        self.assertEqual(list(self.answer.selected_options.all()), [])

    @override_settings(EXAM_SUPERVISION_ENABLED=False)
    def test_supervision_feature_off_keeps_legacy_behaviour(self):
        self._lock(manual=False)
        self.assertEqual(self._autosave().status_code, 200)


@override_settings(CACHES=LOCMEM_CACHE)
class AttemptIdorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("eqidor")
        cls.other = User.objects.create_user("eqidor_other", "eqidor_other@test.az", PASSWORD)
        _assign_user_to_org(cls.other, cls.org, ProfileRole.STUDENT)
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=2, title="EQ IDOR")

    def test_other_student_cannot_touch_attempt_result_or_timer(self):
        owner = _student_client("eqidor_student", self.org)
        owner.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        answer = attempt.answers.order_by("id").first()
        intruder = _student_client("eqidor_other", self.org)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(intruder.get(take_url).status_code, 404)
        self.assertEqual(
            intruder.post(take_url, {"submit_action": "finish"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code,
            404,
        )
        result_url = reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(intruder.get(result_url).status_code, 404)
        seen_url = reverse("exams:question_seen", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(intruder.post(seen_url, {"question_id": answer.question_id}).status_code, 404)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")

    def test_answers_to_foreign_questions_are_ignored(self):
        other_exam = _make_quiz(self.org, self.teacher, n_questions=1, title="EQ Foreign")
        foreign_question = other_exam.questions.get()
        foreign_correct = foreign_question.options.get(is_correct=True)
        client = _student_client("eqidor_student", self.org)
        client.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        response = client.post(
            take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(foreign_question.id)],
                f"q_{foreign_question.id}": str(foreign_correct.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(attempt.answers.filter(question=foreign_question).exists())
        self.assertFalse(foreign_question.answers.exists())


@override_settings(CACHES=LOCMEM_CACHE)
class StudentPagesQueryBudgetTests(TestCase):
    """Tələbə tarixçəsi və nəticə səhifəsi cəhd sayından asılı olmayan sorğu sayı ilə açılır."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("eqperf")

    def _finished_attempts(self, count):
        exams = []
        now = timezone.now()
        for index in range(count):
            exam = _make_quiz(self.org, self.teacher, n_questions=2, title=f"EQ Perf {index}", max_attempts_per_user=0)
            attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=exam,
                status="submitted",
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=20),
            )
            for question in exam.questions.all():
                answer = attempt.answers.create(question=question)
                answer.selected_options.set([question.options.get(is_correct=True)])
            exams.append(exam)
        return exams

    def _count(self, client, url):
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_history_query_count_is_independent_of_attempt_count(self):
        client = _student_client("eqperf_student", self.org)
        url = reverse("exams:student_exam_history")
        self._finished_attempts(2)
        client.get(url)
        small = self._count(client, url)
        self._finished_attempts(6)
        large = self._count(client, url)
        self.assertLessEqual(large, small + 2, f"history page: {small} → {large} queries")

    def test_result_page_query_count_is_independent_of_previous_attempts(self):
        exam = _make_quiz(self.org, self.teacher, n_questions=3, title="EQ Perf Result", max_attempts_per_user=0)
        now = timezone.now()

        def add_attempt():
            attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=exam,
                status="submitted",
                attempt_number=ExamAttempt.objects.filter(user=self.student, exam=exam).count() + 1,
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=20),
            )
            for question in exam.questions.all():
                attempt.answers.create(question=question).selected_options.set([question.options.get(is_correct=True)])
            return attempt

        add_attempt()  # bir əvvəlki cəhd — toplu (batch) sorğular artıq ölçüdə olsun
        latest = add_attempt()
        client = _student_client("eqperf_student", self.org)
        url = reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": latest.id})
        client.get(url)
        small = self._count(client, url)
        for _ in range(5):
            add_attempt()
        large = self._count(client, url)
        self.assertLessEqual(large, small + 2, f"result page: {small} → {large} queries")


@override_settings(CACHES=LOCMEM_CACHE)
class TeacherPendingQueryBudgetTests(TestCase):
    """Yoxlanılacaq yazılı işlər siyahısı cəhd sayından asılı olmayan sorğu sayı ilə açılır."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("eqpend")

    def _written_attempts(self, count):
        now = timezone.now()
        for index in range(count):
            exam = _make_quiz(self.org, self.teacher, n_questions=1, title=f"EQ Written {index}")
            exam.exam_type = "written"
            exam.save(update_fields=["exam_type"])
            ExamAttempt.objects.create(
                user=self.student,
                exam=exam,
                status="submitted",
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=20),
            )

    def _count(self, client):
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("exams:teacher_pending_attempts"))
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_pending_page_query_count_is_independent_of_attempt_count(self):
        client = Client()
        _login_with_org(client, self.teacher, self.org)
        self._written_attempts(1)
        client.get(reverse("exams:teacher_pending_attempts"))
        small = self._count(client)
        self._written_attempts(5)
        large = self._count(client)
        self.assertLessEqual(large, small + 1, f"pending page: {small} → {large} queries")
