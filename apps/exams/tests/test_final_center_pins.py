"""
Final imtahan mərkəzi — PIN təhlükəsizliyi və bilet state machine unit testləri.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import (
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import Exam, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import (
    decrypt_ticket_pin,
    generate_pin_value,
    revoke_ticket_pin,
    set_ticket_pin,
    student_visible_pin,
    transition_ticket,
    verify_ticket_pin,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _FinalCenterBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fcp_owner", "fcp_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="FCP University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("fcp_center", "fcp_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.student = User.objects.create_user("fcp_student", "fcp_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        _now = timezone.now()
        cls.exam = Exam.objects.create(
            title="FCP Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            # PIN müddəti/görünmə pəncərəsi imtahanın cədvəlindən gəlir (oturum
            # sisteminin ləğvi): başlanğıc 10 dəq sonra, son 2 saat sonra.
            start_datetime=_now + timedelta(minutes=10),
            end_datetime=_now + timedelta(hours=2),
        )
        cls.room = ExamRoom.objects.create(
            organization=cls.org, name="Zal 1", code="Z1", capacity=30, created_by=cls.center
        )
        now = timezone.now()
        cls.session = ExamRoomSession.objects.create(
            organization=cls.org,
            room=cls.room,
            invigilator=cls.center,
            scheduled_start=now + timedelta(minutes=10),
            scheduled_end=now + timedelta(hours=2),
            created_by=cls.center,
        )

    def _ticket(self, student=None):
        return FinalExamTicket.objects.create(
            organization=self.org,
            session=self.session,
            exam=self.exam,
            student=student or self.student,
        )


class PinSecurityTests(_FinalCenterBase):
    def test_generated_pin_has_configured_length_and_charset(self):
        pin = generate_pin_value()
        self.assertEqual(len(pin), 8)
        self.assertTrue(pin.isdigit())

    def test_set_ticket_pin_stores_hash_not_plaintext(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.pin_hash, raw)
        self.assertNotIn(raw, ticket.pin_hash)
        self.assertNotIn(raw, ticket.pin_cipher)
        self.assertIsNotNone(ticket.pin_issued_at)
        self.assertIsNotNone(ticket.pin_expires_at)

    def test_verify_accepts_correct_and_rejects_wrong_pin(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        self.assertTrue(verify_ticket_pin(ticket, raw))
        self.assertFalse(verify_ticket_pin(ticket, "00000000" if raw != "00000000" else "11111111"))

    def test_repeated_failures_lock_the_ticket(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        for _ in range(5):
            self.assertFalse(verify_ticket_pin(ticket, "wrong-pin"))
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_pin_locked)
        # Kilid müddətində düz PIN də qəbul edilmir.
        self.assertFalse(verify_ticket_pin(ticket, raw))

    def test_successful_verify_resets_failure_counter(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        verify_ticket_pin(ticket, "wrong-pin")
        self.assertTrue(verify_ticket_pin(ticket, raw))
        ticket.refresh_from_db()
        self.assertEqual(ticket.pin_failed_attempts, 0)
        self.assertIsNone(ticket.pin_locked_until)

    def test_expired_pin_is_rejected(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        FinalExamTicket.objects.filter(pk=ticket.pk).update(pin_expires_at=timezone.now() - timedelta(minutes=1))
        ticket.refresh_from_db()
        self.assertFalse(ticket.has_valid_pin)
        self.assertFalse(verify_ticket_pin(ticket, raw))

    def test_regeneration_invalidates_previous_pin(self):
        ticket = self._ticket()
        old_raw = set_ticket_pin(ticket, self.center)
        new_raw = set_ticket_pin(ticket, self.center)
        self.assertNotEqual(old_raw, new_raw)
        self.assertFalse(verify_ticket_pin(ticket, old_raw))
        self.assertTrue(verify_ticket_pin(ticket, new_raw))

    def test_revoked_pin_is_rejected_and_cipher_wiped(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        revoke_ticket_pin(ticket)
        ticket.refresh_from_db()
        self.assertEqual(ticket.pin_cipher, "")
        self.assertFalse(verify_ticket_pin(ticket, raw))

    def test_decrypt_returns_original_pin_for_authorized_display(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        self.assertEqual(decrypt_ticket_pin(ticket), raw)

    def test_student_visible_pin_respects_visibility_window(self):
        ticket = self._ticket()
        raw = set_ticket_pin(ticket, self.center)
        # Pəncərə daxilində (start 10 dəq sonra, default 120 dəq) → görünür.
        self.assertEqual(student_visible_pin(ticket), raw)
        with override_settings(FINAL_EXAM_PIN_VISIBILITY_MINUTES=5):
            self.assertIsNone(student_visible_pin(ticket))

    def test_student_visible_pin_hidden_after_final_status(self):
        ticket = self._ticket()
        set_ticket_pin(ticket, self.center)
        FinalExamTicket.objects.filter(pk=ticket.pk).update(status=TICKET_STATUS_COMPLETED)
        ticket.refresh_from_db()
        self.assertIsNone(student_visible_pin(ticket))


class TicketStateMachineTests(_FinalCenterBase):
    def test_valid_transition_assigned_to_waiting(self):
        ticket = self._ticket()
        self.assertTrue(transition_ticket(ticket, TICKET_STATUS_WAITING))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TICKET_STATUS_WAITING)

    def test_invalid_transition_rejected(self):
        ticket = self._ticket()
        # assigned → completed birbaşa mümkün deyil.
        self.assertFalse(transition_ticket(ticket, TICKET_STATUS_COMPLETED))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TICKET_STATUS_ASSIGNED)

    def test_completed_is_terminal(self):
        ticket = self._ticket()
        FinalExamTicket.objects.filter(pk=ticket.pk).update(status=TICKET_STATUS_COMPLETED)
        ticket.refresh_from_db()
        self.assertFalse(transition_ticket(ticket, TICKET_STATUS_ACTIVE))
        self.assertFalse(transition_ticket(ticket, TICKET_STATUS_REMOVED))

    def test_stale_status_loses_the_race(self):
        """Paralel yeniləmə: köhnə statusla gələn keçid təsirsiz qalır."""
        ticket = self._ticket()
        stale_copy = FinalExamTicket.objects.get(pk=ticket.pk)
        self.assertTrue(transition_ticket(ticket, TICKET_STATUS_WAITING))
        # stale_copy hələ "assigned" bilir → şərti UPDATE 0 sətir tapır.
        self.assertFalse(transition_ticket(stale_copy, TICKET_STATUS_REMOVED, extra_updates={"removal_reason": "x"}))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TICKET_STATUS_WAITING)

    def test_unique_ticket_per_exam_student(self):
        from django.db import IntegrityError

        self._ticket()
        with self.assertRaises(IntegrityError):
            self._ticket()
