"""
Final imtahan mərkəzi — kabinet konteksti + xatırlatma bildirişləri testləri.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.public import student_final_exam_context
from apps.exams.services.final_center import notify_upcoming_final_exams, set_ticket_pin
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.notifications.models import InAppNotification
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _CabinetBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cab_owner", "cab_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Cab University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("cab_center", "cab_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.student = User.objects.create_user("cab_student", "cab_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.exam = Exam.objects.create(
            title="Cab Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
        )
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal C", code="ZC", capacity=20)

    def _set_window(self, *, start_delta, end_delta):
        """İMTAHANIN cədvəlini qur — kabinet/xatırlatma bundan asılıdır
        (oturum sisteminin ləğvi: pəncərə imtahandan, zaldan yox)."""
        now = timezone.now()
        self.exam.start_datetime = now + start_delta
        self.exam.end_datetime = now + end_delta
        self.exam.save(update_fields=["start_datetime", "end_datetime"])

    def _session(self, *, start_delta, end_delta):
        now = timezone.now()
        return ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.center,
            scheduled_start=now + start_delta,
            scheduled_end=now + end_delta,
            created_by=self.center,
        )

    def _ticket(self, session=None):
        ticket = FinalExamTicket.objects.create(
            organization=self.org, session=session, exam=self.exam, student=self.student
        )
        set_ticket_pin(ticket, self.center)
        return ticket


class CabinetContextTests(_CabinetBase):
    def test_no_ticket_returns_has_ticket_false(self):
        ctx = student_final_exam_context(self.student, self.exam)
        self.assertFalse(ctx["has_ticket"])

    def test_context_exposes_window_and_pin_within_visibility(self):
        # İmtahan pəncərəsi indi açıqdır (başlanğıc keçib, son gələcəkdə).
        self._set_window(start_delta=timedelta(minutes=-5), end_delta=timedelta(hours=2))
        self._ticket()
        ctx = student_final_exam_context(self.student, self.exam)
        self.assertTrue(ctx["has_ticket"])
        self.assertEqual(ctx["window_start"], self.exam.start_datetime)
        self.assertEqual(ctx["window_end"], self.exam.end_datetime)
        self.assertTrue(ctx["entry_open"])  # pəncərə açıqdır
        self.assertIsNotNone(ctx["pin"])  # görünmə pəncərəsi daxilində

    def test_pin_hidden_outside_visibility_window(self):
        # Başlanğıc çox uzaqda → PIN hələ görünmür (görünmə pəncərəsi bağlı).
        self._set_window(start_delta=timedelta(days=10), end_delta=timedelta(days=10, hours=2))
        self._ticket()
        with override_settings(FINAL_EXAM_PIN_VISIBILITY_MINUTES=60):
            ctx = student_final_exam_context(self.student, self.exam)
        self.assertTrue(ctx["has_ticket"])
        self.assertIsNone(ctx["pin"])


class ReminderTaskTests(_CabinetBase):
    def _count_reminders(self):
        return InAppNotification.objects.filter(recipient=self.student, notification_type="exam").count()

    def test_reminder_sent_within_threshold(self):
        self._set_window(start_delta=timedelta(days=2), end_delta=timedelta(days=2, hours=2))
        ticket = self._ticket()
        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)):
            sent = notify_upcoming_final_exams()
        self.assertEqual(sent, 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.reminder_stage, 3)
        self.assertEqual(self._count_reminders(), 1)

    def test_reminder_not_duplicated_for_same_stage(self):
        self._set_window(start_delta=timedelta(days=2), end_delta=timedelta(days=2, hours=2))
        self._ticket()
        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)):
            notify_upcoming_final_exams()
            second = notify_upcoming_final_exams()
        self.assertEqual(second, 0)
        self.assertEqual(self._count_reminders(), 1)

    def test_second_reminder_at_closer_threshold(self):
        self._set_window(start_delta=timedelta(days=2), end_delta=timedelta(days=2, hours=2))
        ticket = self._ticket()
        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)):
            notify_upcoming_final_exams()  # 3-day reminder
            # Vaxtı 1 günə yaxınlaşdır (imtahanı sürüşdürmək əvəzinə now-u irəli aparırıq).
            near = timezone.now() + timedelta(days=1, hours=12)  # exam.start ~ now+2d → days_left ~0.5
            second = notify_upcoming_final_exams(now=near)
        self.assertEqual(second, 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.reminder_stage, 1)
        self.assertEqual(self._count_reminders(), 2)

    def test_no_reminder_outside_horizon(self):
        self._set_window(start_delta=timedelta(days=10), end_delta=timedelta(days=10, hours=2))
        self._ticket()
        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)):
            sent = notify_upcoming_final_exams()
        self.assertEqual(sent, 0)

    def test_no_reminder_for_completed_ticket(self):
        self._set_window(start_delta=timedelta(days=2), end_delta=timedelta(days=2, hours=2))
        ticket = self._ticket()
        FinalExamTicket.objects.filter(pk=ticket.pk).update(status="completed")
        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)):
            sent = notify_upcoming_final_exams()
        self.assertEqual(sent, 0)


class SupervisorNavFlagTests(_CabinetBase):
    """Naviqasiya bayrağı: kim final mərkəzi menyusunu görür."""

    def test_exam_center_always_sees_final_center(self):
        from apps.exams.public import user_supervises_final_sessions

        # İmtahan mərkəzinin oturum təyinatı olmasa da rol ilə giriş var (view qatı);
        # bu helper yalnız təyinatı yoxlayır, ona görə mərkəzin təyinatı yoxdursa False.
        self.assertFalse(user_supervises_final_sessions(self.center))

    def test_assigned_invigilator_flag_true(self):
        from apps.exams.public import user_supervises_final_sessions

        teacher = User.objects.create_user("cab_invig", "cab_invig@test.az", PASSWORD)
        _assign_user_to_org(teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.assertFalse(user_supervises_final_sessions(teacher))
        session = self._session(start_delta=timedelta(hours=1), end_delta=timedelta(hours=3))
        session.invigilator = teacher
        session.save(update_fields=["invigilator"])
        self.assertTrue(user_supervises_final_sessions(teacher))

    def test_cancelled_session_does_not_count(self):
        from apps.exams.domain.final_center import ROOM_SESSION_STATE_CANCELLED
        from apps.exams.public import user_supervises_final_sessions

        teacher = User.objects.create_user("cab_invig2", "cab_invig2@test.az", PASSWORD)
        _assign_user_to_org(teacher, self.org, ProfileRole.TEACHER, "teacher")
        session = self._session(start_delta=timedelta(hours=1), end_delta=timedelta(hours=3))
        session.invigilator = teacher
        session.state = ROOM_SESSION_STATE_CANCELLED
        session.save(update_fields=["invigilator", "state"])
        self.assertFalse(user_supervises_final_sessions(teacher))
