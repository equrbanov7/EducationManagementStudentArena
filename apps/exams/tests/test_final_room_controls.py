"""Zal monitorunda "hamısını bitir" düyməsi + gün sonu (22:00) avtomatik bağlama."""

from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_CANCELLED,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
)
from apps.exams.models import ExamRoomSession
from apps.exams.services.final_center import (
    auto_close_stale_room_sessions,
    open_entry,
    start_room,
)
from apps.exams.tests.test_final_center_flow import _FlowBase


class RoomEndAllViewTests(_FlowBase):
    def _activate_session(self):
        open_entry(self.session, self.center)
        self.session.refresh_from_db()
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ACTIVE)

    def test_end_all_ends_active_sessions_in_room(self):
        self._activate_session()
        client = Client()
        client.force_login(self.center)
        response = client.post(
            reverse("exams:exam_center_room_end_all", args=[self.room.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "ended": 1})
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ENDED)

    def test_end_all_is_idempotent_when_nothing_active(self):
        client = Client()
        client.force_login(self.center)
        response = client.post(
            reverse("exams:exam_center_room_end_all", args=[self.room.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["ended"], 0)
        # 2026-07-29: boş halda izahlı mesaj da qaytarılır (düymə daimi görünür).
        self.assertIn("error", data)


class AutoCloseDailyCutoffTests(_FlowBase):
    def test_active_session_is_ended_and_entry_open_is_cancelled(self):
        # Aktiv oturum.
        open_entry(self.session, self.center)
        self.session.refresh_from_db()
        start_room(self.session, self.invigilator)

        # İkinci otaq + giriş açıq (başlamamış) oturum.
        from apps.exams.models import ExamRoom

        now = timezone.now()
        room2 = ExamRoom.objects.create(
            organization=self.org, name="Zal B", code="ZB", capacity=10, created_by=self.center
        )
        session2 = ExamRoomSession.objects.create(
            organization=self.org,
            room=room2,
            invigilator=self.invigilator,
            scheduled_start=now - timedelta(minutes=30),
            scheduled_end=now + timedelta(hours=1),
            created_by=self.center,
        )
        open_entry(session2, self.center)
        session2.refresh_from_db()
        self.assertEqual(session2.state, ROOM_SESSION_STATE_ENTRY_OPEN)

        result = auto_close_stale_room_sessions()
        self.assertEqual(result, {"ended": 1, "cancelled": 1})

        self.session.refresh_from_db()
        session2.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ENDED)
        self.assertEqual(session2.state, ROOM_SESSION_STATE_CANCELLED)

    def test_future_session_is_not_touched(self):
        now = timezone.now()
        from apps.exams.models import ExamRoom

        room_future = ExamRoom.objects.create(
            organization=self.org, name="Zal C", code="ZC", capacity=10, created_by=self.center
        )
        future = ExamRoomSession.objects.create(
            organization=self.org,
            room=room_future,
            invigilator=self.invigilator,
            scheduled_start=now + timedelta(days=1),
            scheduled_end=now + timedelta(days=1, hours=2),
            created_by=self.center,
        )
        open_entry(future, self.center)  # gələcək oturum, amma giriş açıq
        future.refresh_from_db()

        result = auto_close_stale_room_sessions()
        self.assertEqual(result["cancelled"], 0)
        future.refresh_from_db()
        self.assertEqual(future.state, ROOM_SESSION_STATE_ENTRY_OPEN)
