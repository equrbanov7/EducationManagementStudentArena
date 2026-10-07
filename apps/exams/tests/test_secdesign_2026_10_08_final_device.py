"""Təhlükəsizlik dizaynı 2026-10-08 — davam edən final cəhdi başladığı cihaza bağlıdır.

Audit 2026-10-07 «Dizayn riskləri»: qeydli zal kompüteri olmayan təşkilatda final cəhdi
(biletsiz, fərdi PIN axını) istənilən cihazdan — məs. tələbənin telefonundan adi login
ilə — davam etdirilə bilirdi; giriş sessiyası yoxlaması yalnız bilet olanda işləyirdi.

İndi: ilk girişdə cəhd imzalı cihaz cookie-si (+ sessiya) ilə bağlanır; eyni cihaz
(brauzer çöküşündən sonra da) davam edir; başqa cihaz aydın Azərbaycan dilli mesajla
dayandırılır; nəzarətçi/imtahan mərkəzinin «cihaz dəyişikliyi» təsdiqi (audit) cəhdi
yeni cihaza köçürür. Qeydli kompüteri olan təşkilatda da eyni qayda (defense in depth).
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, TICKET_STATUS_ACTIVE
from apps.exams.models import (
    ExamAnswer,
    ExamAttempt,
    ExamRoom,
    ExamRoomComputer,
    ExamRoomSession,
    FinalAttemptDevice,
    FinalExamTicket,
)
from apps.exams.services.final_center.device_binding import DEVICE_COOKIE_NAME
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

HALL_IP = "10.20.30.41"
OTHER_IP = "85.132.9.9"


def _make_final(org, teacher, title, n_questions):
    exam = _make_quiz(org, teacher, n_questions=n_questions, title=title)
    exam.exam_type_extended = "final"
    exam.save(update_fields=["exam_type_extended"])
    return exam


@override_settings(CACHES=LOCMEM_CACHE)
class FinalAttemptDeviceBindingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("fd1008")
        cls.center = User.objects.create_user("fd1008_center", "fd1008_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.exam = _make_final(cls.org, cls.teacher, "FD1008 Final", 2)

    def setUp(self):
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        self.questions = list(self.exam.questions.order_by("order"))
        for question in self.questions:
            ExamAnswer.objects.create(attempt=self.attempt, question=question)
        self.take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        self.seen_url = reverse("exams:question_seen", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        self.approve_url = reverse("exams:exam_center_final_device_change", kwargs={"attempt_id": self.attempt.id})
        self.device_a = _student_client("fd1008_student", self.org)

    def _device(self, *, cookie_from=None):
        client = _student_client("fd1008_student", self.org)
        if cookie_from is not None:
            client.cookies[DEVICE_COOKIE_NAME] = cookie_from.cookies[DEVICE_COOKIE_NAME].value
        return client

    def _autosave(self, client, label="A", **extra):
        question = self.questions[0]
        return client.post(
            self.take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(question.id)],
                f"q_{question.id}": option_value(self.attempt, question.options.get(label=label)),
                "marked_question_ids": "[]",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            **extra,
        )

    def _audit(self, reason):
        return AuditLog.objects.filter(reason=reason, object_id=str(self.attempt.pk))

    # ── eyni cihaz ─────────────────────────────────────────────────────────

    def test_first_access_binds_the_attempt_to_this_device(self):
        response = self.device_a.get(self.take_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(DEVICE_COOKIE_NAME, response.cookies)
        cookie = response.cookies[DEVICE_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        binding = FinalAttemptDevice.objects.get(attempt=self.attempt)
        self.assertEqual(len(binding.token_hash), 64)
        self.assertNotIn(binding.token_hash, cookie.value)
        self.assertTrue(self._audit("final_device_bound").exists())
        self.assertEqual(self._autosave(self.device_a).status_code, 200)

    def test_same_device_continues_after_a_browser_crash_and_new_login(self):
        self.device_a.get(self.take_url)
        restarted = self._device(cookie_from=self.device_a)  # yeni sessiya, eyni cihaz cookie-si

        self.assertEqual(restarted.get(self.take_url).status_code, 200)
        self.assertEqual(self._autosave(restarted).status_code, 200)
        self.assertFalse(self._audit("final_device_mismatch").exists())

    # ── başqa cihaz ────────────────────────────────────────────────────────

    def test_other_device_is_blocked_with_a_clear_azerbaijani_message(self):
        self.device_a.get(self.take_url)
        phone = self._device()

        page = phone.get(self.take_url)
        self.assertEqual(page.status_code, 403)
        self.assertTemplateUsed(page, "exams/student/final_device_blocked.html")
        self.assertContains(page, "başqa cihazda", status_code=403)
        self.assertContains(page, "cihaz dəyişikliyi", status_code=403)
        self.assertNotContains(page, self.questions[0].text, status_code=403)

        autosave = self._autosave(phone)
        self.assertEqual(autosave.status_code, 403)
        self.assertTrue(autosave.json()["device_blocked"])
        self.assertIn("cihaz", autosave.json()["error"])
        self.assertIsNone(
            ExamAnswer.objects.get(attempt=self.attempt, question=self.questions[0]).selected_option_ids_snapshot
        )

        seen = phone.post(self.seen_url, {"question_id": str(self.questions[0].id)})
        self.assertEqual(seen.status_code, 403)
        self.assertNotIn("html", seen.json())

        denied = self._audit("final_device_mismatch")
        self.assertTrue(denied.exists())
        self.assertEqual(denied.first().action, "deny")

    def test_forged_device_cookie_is_ignored(self):
        self.device_a.get(self.take_url)
        phone = self._device()
        phone.cookies[DEVICE_COOKIE_NAME] = "forged-device-value"
        self.assertEqual(phone.get(self.take_url).status_code, 403)

    # ── nəzarətçi təsdiqi ──────────────────────────────────────────────────

    def test_proctor_approval_moves_the_attempt_to_the_new_device(self):
        self.device_a.get(self.take_url)
        center = _student_client("fd1008_center", self.org)

        approve = center.post(self.approve_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(approve.status_code, 200, approve.content[:300])
        self.assertTrue(approve.json()["success"])
        approval = self._audit("final_device_change_approved").get()
        self.assertEqual(approval.user_id, self.center.pk)

        phone = self._device()
        self.assertEqual(phone.get(self.take_url).status_code, 200)
        self.assertEqual(self._autosave(phone).status_code, 200)
        rebound = self._audit("final_device_rebound").get()
        self.assertEqual(rebound.changes.get("source"), "proctor_approval")
        binding = FinalAttemptDevice.objects.get(attempt=self.attempt)
        self.assertIsNone(binding.change_approved_at, "təsdiq birdəfəlikdir")

        # Köhnə cihaz artıq dayandırılır.
        self.assertEqual(self.device_a.get(self.take_url).status_code, 403)

    def test_expired_approval_does_not_unblock(self):
        self.device_a.get(self.take_url)
        _student_client("fd1008_center", self.org).post(self.approve_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        FinalAttemptDevice.objects.filter(attempt=self.attempt).update(
            change_approved_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(self._device().get(self.take_url).status_code, 403)

    def test_only_exam_center_can_approve(self):
        self.device_a.get(self.take_url)
        for client in (self._device(), _student_client("fd1008_teacher", self.org)):
            response = client.post(self.approve_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(response.status_code, 403)
        self.assertIsNone(FinalAttemptDevice.objects.get(attempt=self.attempt).change_approved_at)
        self.assertFalse(self._audit("final_device_change_approved").exists())

    def test_pin_lookup_offers_device_change_for_a_bound_attempt(self):
        from apps.exams.models import ExamStudentPin

        ExamStudentPin.objects.create(exam=self.exam, student=self.student, pin_hash="x")
        self.device_a.get(self.take_url)
        center = _student_client("fd1008_center", self.org)
        url = reverse("exams:exam_center_student_pins", kwargs={"student_id": self.student.pk})

        items = center.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()["tickets"]

        self.assertEqual([item["device_change_url"] for item in items], [self.approve_url])

    # ── əhatə ──────────────────────────────────────────────────────────────

    def test_non_final_exams_are_not_bound(self):
        quiz = _make_quiz(self.org, self.teacher, n_questions=1, title="FD1008 Quiz")
        attempt = ExamAttempt.objects.create(user=self.student, exam=quiz, status="in_progress")
        ExamAnswer.objects.create(attempt=attempt, question=quiz.questions.get())
        url = reverse("exams:take_exam", kwargs={"slug": quiz.slug, "attempt_id": attempt.id})
        self.assertEqual(self.device_a.get(url).status_code, 200)
        self.assertEqual(self._device().get(url).status_code, 200)
        self.assertFalse(FinalAttemptDevice.objects.filter(attempt=attempt).exists())

    def test_binding_check_costs_one_query_on_the_autosave_path(self):
        self.device_a.get(self.take_url)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self._autosave(self.device_a).status_code, 200)
        binding_queries = [q["sql"] for q in ctx.captured_queries if "exams_finalattemptdevice" in q["sql"]]
        self.assertEqual(len(binding_queries), 1, binding_queries)


@override_settings(CACHES=LOCMEM_CACHE)
class FinalDeviceWithHallComputersTests(TestCase):
    """Qeydli kompüteri olan təşkilat: eyni qayda + eyni qeydli kompüter (kiosk cookie silir)."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("fdh1008")
        cls.center = User.objects.create_user("fdh1008_center", "fdh1008_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.exam = _make_final(cls.org, cls.teacher, "FDH1008 Final", 1)
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal 1008", code="Z1008", capacity=10)
        cls.computer = ExamRoomComputer.objects.create(
            organization=cls.org,
            room=cls.room,
            label="PC-1",
            seat_number=1,
            mac_address="aa:bb:cc:dd:ee:01",
            ip_address=HALL_IP,
        )

    def setUp(self):
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", room=self.room, room_computer=self.computer
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.exam.questions.get())
        self.take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})

    def test_other_device_is_blocked_even_with_registered_computers(self):
        self.assertEqual(
            _student_client("fdh1008_student", self.org).get(self.take_url, REMOTE_ADDR=HALL_IP).status_code, 200
        )
        phone = _student_client("fdh1008_student", self.org)
        self.assertEqual(phone.get(self.take_url, REMOTE_ADDR=OTHER_IP).status_code, 403)

    def test_same_registered_hall_computer_without_cookie_continues(self):
        _student_client("fdh1008_student", self.org).get(self.take_url, REMOTE_ADDR=HALL_IP)
        kiosk_restart = _student_client("fdh1008_student", self.org)  # cookie-lər silinib
        self.assertEqual(kiosk_restart.get(self.take_url, REMOTE_ADDR=HALL_IP).status_code, 200)
        rebound = AuditLog.objects.get(reason="final_device_rebound", object_id=str(self.attempt.pk))
        self.assertEqual(rebound.changes.get("source"), "hall_computer")

    def test_reentry_pin_from_the_proctor_approves_the_device_change(self):
        # Cəhd əvvəl zal kompüterində açılıb (bağlanıb), sonra bilet axınına qoşulur.
        self.assertEqual(
            _student_client("fdh1008_student", self.org).get(self.take_url, REMOTE_ADDR=HALL_IP).status_code, 200
        )
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.center,
            state=ROOM_SESSION_STATE_ACTIVE,
            scheduled_start=timezone.now() - timedelta(minutes=10),
            scheduled_end=timezone.now() + timedelta(hours=2),
        )
        ticket = FinalExamTicket.objects.create(
            organization=self.org,
            session=session,
            exam=self.exam,
            student=self.student,
            status=TICKET_STATUS_ACTIVE,
            attempt=self.attempt,
        )
        center = Client()
        center.force_login(self.center)
        center_session = center.session
        center_session["active_organization"] = self.org.slug
        center_session.save()

        response = center.post(
            reverse("exams:exam_center_ticket_reentry", kwargs={"session_id": session.pk, "ticket_id": ticket.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200, response.content[:300])
        binding = FinalAttemptDevice.objects.get(attempt=self.attempt)
        self.assertIsNotNone(binding.change_approved_at)
        approval = AuditLog.objects.get(reason="final_device_change_approved", object_id=str(self.attempt.pk))
        self.assertEqual(approval.changes.get("source"), "reentry_pin")
        self.assertEqual(approval.user_id, self.center.pk)
