"""Final imtahan giriş sessiyası, PIN rotasiyası və kompüter dəyişməsi regresiyaları."""

from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import Client, SimpleTestCase
from django.urls import reverse

from apps.exams.models import ExamRoomComputer, ExamStudentPin
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, regenerate_pin, start_room
from apps.exams.services.final_center.entry import (
    ENTRY_SESSION_KEY,
    ENTRY_VERSION_SESSION_KEY,
    entry_session_values_match,
)
from apps.exams.tests.test_final_center_flow import _FlowBase


class FinalSessionExclusivityTests(_FlowBase):
    def _start_attempt(self, client):
        client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": ""},
        )
        start_room(self.session, self.invigilator)
        response = client.post(reverse("exams:final_exam_begin", args=[self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        return self.ticket.attempt

    def test_ticket_pin_is_claimed_once(self):
        first = Client()
        response = first.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.raw_pin},
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.pin_revoked_at)

        second = Client()
        response = second.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.raw_pin},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", second.session)

    def test_reentry_pin_invalidates_old_browser_and_resumes_same_answers_on_new_computer(self):
        old_client, response = self._entry_client()
        self.assertEqual(response.status_code, 302)
        attempt = self._start_attempt(old_client)
        answer = attempt.answers.select_related("question").first()
        selected = answer.question.options.get(is_correct=True)
        answer.selected_options.set([selected])

        new_computer = ExamRoomComputer.objects.create(
            organization=self.org,
            room=self.room,
            label="PC-NEW",
            seat_number=11,
            mac_address="AA:BB:CC:DD:EE:11",
            ip_address="10.0.0.11",
            created_by=self.center,
        )
        staff = self._client_for(self.invigilator)
        response = staff.post(reverse("exams:exam_center_ticket_reentry", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        new_pin = response.json()["pin"]

        response = old_client.get(reverse("exams:supervision_status_api", args=[attempt.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "entry_session_valid": False,
                "redirect_url": reverse("exams:final_exam_entry"),
            },
        )
        self.assertNotIn("_auth_user_id", old_client.session)

        old_url = reverse("exams:take_exam", args=[self.exam.slug, attempt.pk])
        response = old_client.get(old_url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", old_client.session)

        new_client = Client()
        response = new_client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": new_pin},
            REMOTE_ADDR=new_computer.ip_address,
        )
        self.assertEqual(response.status_code, 302)
        response = new_client.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=new_computer.ip_address)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/attempt/{attempt.pk}/", response["Location"])

        response = new_client.get(old_url, REMOTE_ADDR=new_computer.ip_address)
        self.assertEqual(response.status_code, 200)
        restored = response.context["answers_by_qid"][answer.question_id]
        self.assertEqual(restored["selected_option_ids"], {selected.pk})

        self.ticket.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.ticket.attempt_id, attempt.pk)
        self.assertEqual(self.ticket.seat_number, new_computer.seat_number)
        self.assertEqual(attempt.room_computer_id, new_computer.pk)

        duplicate = Client()
        response = duplicate.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": new_pin},
            REMOTE_ADDR=new_computer.ip_address,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", duplicate.session)

    def test_student_pin_relogin_invalidates_previous_session_even_with_issued_ticket_pin(self):
        """Hibrid hal: biletdə pin_issued_at dolu olsa belə (nəzarətçi PIN-i),
        fərdi ExamStudentPin ilə hər yeni giriş əvvəlki brauzer sessiyasını
        keçərsizləşdirməlidir — versiya yalnız pin_issued_at-a bağlansa bu itir."""
        from datetime import timedelta

        from django.utils import timezone

        # Student-PIN yolu imtahanın başlamış olmasını tələb edir (can_user_start).
        type(self.exam).objects.filter(pk=self.exam.pk).update(start_datetime=timezone.now() - timedelta(minutes=1))
        ExamStudentPin.objects.create(
            exam=self.exam,
            student=self.student,
            pin_hash=make_password("24681357"),
            pin_cipher="encrypted-placeholder",
        )
        self.assertIsNotNone(self.ticket.pin_issued_at)  # hibrid ön şərt

        first = Client()
        response = first.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "24681357"},
        )
        self.assertEqual(response.status_code, 302)

        second = Client()
        response = second.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "24681357"},
        )
        self.assertEqual(response.status_code, 302)

        self.ticket.refresh_from_db()
        self.assertFalse(
            entry_session_values_match(
                first.session.get(ENTRY_SESSION_KEY),
                first.session.get(ENTRY_VERSION_SESSION_KEY),
                self.ticket,
            )
        )
        self.assertTrue(
            entry_session_values_match(
                second.session.get(ENTRY_SESSION_KEY),
                second.session.get(ENTRY_VERSION_SESSION_KEY),
                self.ticket,
            )
        )

    def test_completed_ticket_seat_does_not_block_new_student_entry(self):
        """Bitmiş biletin köhnə oturacağı həmin kompüterdən yeni girişi bloklamamalıdır."""
        from apps.exams.domain.final_center import TICKET_STATUS_COMPLETED
        from apps.exams.models import FinalExamTicket

        FinalExamTicket.objects.create(
            organization=self.org,
            session=self.session,
            exam=self.exam,
            student=self.student2,
            status=TICKET_STATUS_COMPLETED,
            seat_number=self.computer.seat_number,
        )
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.raw_pin},
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        # Yer stale sahiblə toqquşduğu üçün boş saxlanılır, giriş isə işləyir.
        self.assertIsNone(self.ticket.seat_number)
        self.assertEqual(self.ticket.session_id, self.session.pk)

    def test_attempt_start_revokes_original_exam_student_pin(self):
        personal_pin = ExamStudentPin.objects.create(
            exam=self.exam,
            student=self.student,
            pin_hash=make_password("13572468"),
            pin_cipher="encrypted-placeholder",
        )
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.ticket.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)

        personal_pin.refresh_from_db()
        self.assertIsNotNone(personal_pin.revoked_at)
        self.assertEqual(personal_pin.pin_cipher, "")

    def test_rotated_pin_blocks_stale_direct_attempt_url(self):
        old_client, response = self._entry_client()
        self.assertEqual(response.status_code, 302)
        attempt = self._start_attempt(old_client)

        regenerate_pin(self.ticket, self.invigilator)

        response = old_client.get(reverse("exams:take_exam", args=[self.exam.slug, attempt.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", old_client.session)

    @patch("apps.exams.services.supervision.notify_attempt_student")
    @patch("apps.exams.services.final_center.tickets.notify_ticket")
    def test_pin_rotation_immediately_evicts_old_browser_channels(self, notify_ticket, notify_attempt):
        client, _response = self._entry_client()
        attempt = self._start_attempt(client)

        regenerate_pin(self.ticket, self.invigilator)

        notify_ticket.assert_called_once_with(self.ticket.pk, {"event": "credential_rotated"})
        notify_attempt.assert_called_once_with(attempt.pk, {"action": "session_revoked"})


class FinalResumeFrontendContractTests(SimpleTestCase):
    def test_final_answers_autosave_fast_and_new_device_opens_first_unanswered(self):
        from pathlib import Path

        js_dir = Path(__file__).resolve().parents[1] / "static" / "exams" / "js" / "take_exam"
        config_source = (js_dir / "config.js").read_text(encoding="utf-8")
        navigation_source = (js_dir / "navigation.js").read_text(encoding="utf-8")
        supervision_source = (
            Path(__file__).resolve().parents[1] / "static" / "exams" / "js" / "exam_supervision" / "websocket.js"
        ).read_text(encoding="utf-8")
        supervision_api_source = (
            Path(__file__).resolve().parents[1] / "static" / "exams" / "js" / "exam_supervision" / "api.js"
        ).read_text(encoding="utf-8")

        self.assertIn('examForm.dataset.examTypeExtended === "final"', config_source)
        self.assertIn("Math.min(serverAutoSaveIntervalMs, 3000)", config_source)
        self.assertIn("findIndex(function (slide)", navigation_source)
        self.assertIn("!ns.progress.isSlideAnswered(slide)", navigation_source)
        self.assertIn('data.action === "session_revoked"', supervision_source)
        self.assertIn('cache: "no-store"', supervision_api_source)
        self.assertIn("data.entry_session_valid === false", supervision_api_source)
        self.assertIn("window.location.replace", supervision_api_source)
