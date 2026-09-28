"""Audit 2026-09-28 EXA-04 — qayıb limiti buraxılış qapısı zal/PIN/kod yollarında, FAIL-CLOSED.

Qapı əvvəl yalnız kabinetdəki ``start_exam`` yolunda idi; bilet (``begin_attempt_for_ticket``),
fərdi PIN və kod (``exam_code_check``) yolları onu keçirdi, registrar xətası isə «buraxılır»
(fail-open) kimi qəbul olunurdu.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, TICKET_STATUS_WAITING
from apps.exams.models import (
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomSession,
    ExamStudentPin,
    FinalExamTicket,
)
from apps.exams.services.final_center import TicketStateError, admission_block_reason, begin_attempt_for_ticket
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    _make_org,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.exams.tests.test_views import _assign_user_to_org
from apps.registrar.models import Subject

User = get_user_model()

ELIGIBILITY = "apps.registrar.public.exam_eligibility"
BARRED = {"linked": True, "barred": True, "reason": "QAYIB-LIMITI"}
ADMITTED = {"linked": True, "barred": False, "reason": ""}


class AdmissionBlockReasonTests(TestCase):
    def setUp(self):
        self.org, self.teacher, self.student = _make_people("a3adm")
        self.subject = Subject.objects.create(organization=self.org, code="A3-1", name="Fənn")
        self.exam = _make_quiz(self.org, self.teacher, subject=self.subject)

    def test_unlinked_exam_is_not_gated(self):
        Exam.objects.filter(pk=self.exam.pk).update(subject=None)
        self.exam.refresh_from_db()
        with patch(ELIGIBILITY, side_effect=AssertionError("çağırılmamalıdır")):
            self.assertIsNone(admission_block_reason(self.student, self.exam))

    def test_barred_student_gets_reason(self):
        with patch(ELIGIBILITY, return_value=BARRED):
            self.assertEqual(admission_block_reason(self.student, self.exam), "QAYIB-LIMITI")

    def test_admitted_student_passes(self):
        with patch(ELIGIBILITY, return_value=ADMITTED):
            self.assertIsNone(admission_block_reason(self.student, self.exam))

    def test_registrar_failure_denies_start(self):
        with patch(ELIGIBILITY, side_effect=RuntimeError("db down")):
            self.assertTrue(admission_block_reason(self.student, self.exam))

    def test_active_attempt_is_not_interrupted(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        with patch(ELIGIBILITY, side_effect=RuntimeError("db down")):
            self.assertIsNone(admission_block_reason(self.student, self.exam))


class TicketAdmissionGateTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("a3tk_owner", "a3tk_owner@test.az", PASSWORD)
        self.org = _make_org(owner, "A3TK Org")
        center = User.objects.create_user("a3tk_center", "a3tk_center@test.az", PASSWORD)
        _assign_user_to_org(center, self.org, ProfileRole.MEMBER, membership_role_name="exam_center_head")
        self.student = User.objects.create_user("a3tk_student", "a3tk_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        subject = Subject.objects.create(organization=self.org, code="A3-TK", name="Fənn")
        now = timezone.now()
        self.exam = Exam.objects.create(
            title="A3 Final",
            author=center,
            organization=self.org,
            subject=subject,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            random_question_count=1,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=2),
        )
        question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Sual", answer_mode="single")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        room = ExamRoom.objects.create(organization=self.org, name="Zal", code="Z3", capacity=10, created_by=center)
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            scheduled_start=now - timedelta(hours=2),
            scheduled_end=now + timedelta(hours=2),
            state=ROOM_SESSION_STATE_ACTIVE,
            started_at=now - timedelta(minutes=30),
            created_by=center,
        )
        self.ticket = FinalExamTicket.objects.create(
            organization=self.org, session=session, exam=self.exam, student=self.student, status=TICKET_STATUS_WAITING
        )

    def test_barred_student_cannot_start_in_the_hall(self):
        with patch(ELIGIBILITY, return_value=BARRED):
            with self.assertRaisesMessage(TicketStateError, "QAYIB-LIMITI"):
                begin_attempt_for_ticket(self.ticket)
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())

    def test_eligibility_error_fails_closed_in_the_hall(self):
        with patch(ELIGIBILITY, side_effect=RuntimeError("db down")):
            with self.assertRaises(TicketStateError):
                begin_attempt_for_ticket(self.ticket)
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())

    def test_admitted_student_starts(self):
        with patch(ELIGIBILITY, return_value=ADMITTED):
            attempt = begin_attempt_for_ticket(self.ticket)
        self.assertEqual(attempt.status, "in_progress")


@override_settings(CACHES=LOCMEM_CACHE)
class CodeCheckAdmissionGateTests(TestCase):
    def setUp(self):
        self.org, self.teacher, self.student = _make_people("a3cc")
        subject = Subject.objects.create(organization=self.org, code="A3-CC", name="Fənn")
        self.exam = _make_quiz(self.org, self.teacher, subject=subject)

    def _post(self):
        client = _student_client("a3cc_student", self.org)
        return client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.exam.slug, "access_code": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_barred_student_cannot_start_via_code_path(self):
        with patch(ELIGIBILITY, return_value=BARRED):
            response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "QAYIB-LIMITI")
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())

    def test_eligibility_error_fails_closed_on_code_path(self):
        with patch(ELIGIBILITY, side_effect=RuntimeError("db down")):
            response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())


class StudentPinAdmissionGateTests(_FlowBase):
    """Fərdi PIN yolu (``/exams/final/``): buraxılmayan tələbə login-dən ƏVVƏL rədd olunur."""

    RAW_PIN = "13572468"

    def setUp(self):
        super().setUp()
        FinalExamTicket.objects.all().delete()
        subject = Subject.objects.create(organization=self.org, code="A3-PIN", name="Fənn")
        type(self.exam).objects.filter(pk=self.exam.pk).update(
            subject=subject, start_datetime=timezone.now() - timedelta(minutes=1)
        )
        ExamStudentPin.objects.create(
            exam=self.exam, student=self.student, pin_hash=make_password(self.RAW_PIN), pin_cipher="placeholder"
        )

    def _post(self):
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": self.RAW_PIN}
        )
        return client, response

    def test_barred_student_is_rejected_before_login(self):
        with patch(ELIGIBILITY, return_value=BARRED):
            client, response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QAYIB-LIMITI")
        self.assertNotIn("_auth_user_id", client.session)
        self.assertFalse(FinalExamTicket.objects.filter(exam=self.exam, student=self.student).exists())

    def test_eligibility_error_fails_closed_on_pin_path(self):
        with patch(ELIGIBILITY, side_effect=RuntimeError("db down")):
            client, response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_admitted_student_proceeds(self):
        with patch(ELIGIBILITY, return_value=ADMITTED):
            _client, response = self._post()
        self.assertEqual(response.status_code, 302)
