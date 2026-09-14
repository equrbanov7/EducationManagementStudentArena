"""W4 2026-09-14 (w3sweep R7) — fərdi PIN (ExamStudentPin) axını oturum tarixçəsində.

Əvvəl: `/exams/final/` + fərdi PIN girişi biletə yalnız `entry_validated_at`
yazırdı (audit hadisəsi yox) və fərdi PIN-in yaradılması (signal, bulk_create)
audit-siz idi → oturum tarixçəsi KPI-ları «Girişlər 0 / PIN əməliyyatı 0».

İndi: `claim_student_pin_entry` uğurda `final_entry_validated_student_pin`
audit yazır (tarixçə `final_entry_validated` kodu, detalda «fərdi imtahan PIN-i
ilə»); `session_history` oturum biletlərinin fərdi PIN-lərini
`final_tickets_assigned` kodu ilə sintez edir → hər iki KPI dolur.
"""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.models import ExamStudentPin, FinalExamTicket
from apps.exams.services.final_center import session_history
from apps.exams.services.final_center.entry import STUDENT_PIN_ENTRY_REASON
from apps.exams.tests.test_final_center_flow import _FlowBase


class StudentPinEntryHistoryTests(_FlowBase):
    RAW_PIN = "24681357"

    def setUp(self):
        super().setUp()
        # Fərdi PIN yolu: bilet PIN-siz, yalnız ExamStudentPin; imtahan başlamış olmalıdır.
        FinalExamTicket.objects.all().delete()
        type(self.exam).objects.filter(pk=self.exam.pk).update(start_datetime=timezone.now() - timedelta(minutes=1))
        self.student_pin = ExamStudentPin.objects.create(
            exam=self.exam,
            student=self.student,
            pin_hash=make_password(self.RAW_PIN),
            pin_cipher="encrypted-placeholder",
        )

    def _login_with_student_pin(self):
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.RAW_PIN},
        )
        self.assertEqual(response.status_code, 302)
        return client

    def test_student_pin_login_writes_entry_audit_event_without_raw_pin(self):
        self._login_with_student_pin()
        ticket = FinalExamTicket.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(ticket.session_id, self.session.pk)

        logs = list(
            AuditLog.objects.filter(
                resource_type="final_exam_ticket", resource_id=str(ticket.pk), reason=STUDENT_PIN_ENTRY_REASON
            )
        )
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log.user_id, self.student.pk)
        self.assertEqual(log.organization_id, self.org.pk)
        self.assertEqual(log.changes["entry"], "student_pin")
        self.assertEqual(log.changes["seat"], self.computer.seat_number)
        # Xam PIN heç bir sahəyə düşmür.
        for value in (log.reason, str(log.changes), str(log.old_values), str(log.new_values)):
            self.assertNotIn(self.RAW_PIN, value)

    def test_session_history_counts_student_pin_entry_and_pin_provisioning(self):
        self._login_with_student_pin()
        events = session_history(self.session)

        entries = [e for e in events if e["code"] == "final_entry_validated"]
        self.assertEqual(len(entries), 1)
        self.assertIn("fərdi imtahan PIN-i ilə", entries[0]["detail"])
        self.assertIn(f"kompüter {self.computer.seat_number}", entries[0]["detail"])
        self.assertEqual(entries[0]["actor"], self.student.username)
        self.assertEqual(entries[0]["student"], self.student.username)

        pins = [e for e in events if e["code"] == "final_tickets_assigned"]
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0]["time"], self.student_pin.created_at)
        self.assertEqual(pins[0]["actor"], "Sistem")
        self.assertEqual(pins[0]["student"], self.student.username)
        self.assertIn("fərdi imtahan PIN-i", pins[0]["detail"])
        # Xronoloji: PIN yaradılması girişdən əvvəldir.
        self.assertLess(pins[0]["time"], entries[0]["time"])

    def test_history_page_kpis_include_student_pin_flow(self):
        self._login_with_student_pin()
        response = self._client_for(self.center).get(
            reverse("exams:exam_center_session_history", args=[self.session.pk])
        )
        self.assertEqual(response.status_code, 200)
        summary = response.context["summary"]
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["pins"], 1)

    def test_relogin_records_each_entry_separately(self):
        self._login_with_student_pin()
        self._login_with_student_pin()
        events = session_history(self.session)
        self.assertEqual(sum(1 for e in events if e["code"] == "final_entry_validated"), 2)
        # Fərdi PIN yaradılması bir dəfədir — təkrar giriş onu çoxaltmır.
        self.assertEqual(sum(1 for e in events if e["code"] == "final_tickets_assigned"), 1)

    def test_other_students_pins_are_not_attributed_to_this_session(self):
        # Eyni imtahan, oturuma qoşulmayan tələbənin PIN-i tarixçəyə düşmür.
        ExamStudentPin.objects.create(
            exam=self.exam,
            student=self.student2,
            pin_hash=make_password("11112222"),
            pin_cipher="encrypted-placeholder",
        )
        self._login_with_student_pin()
        events = session_history(self.session)
        pins = [e for e in events if e["code"] == "final_tickets_assigned"]
        self.assertEqual([e["student"] for e in pins], [self.student.username])
