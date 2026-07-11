"""
WebSocket consumers for real-time exam flows.

* ``ExamSupervisionConsumer``  — supervised attempt üçün tələbə kanalı
  (müəllimin lock/resume/stop hadisələri).
* ``FinalExamRoomConsumer``    — final oturumunun nəzarətçi/heyət monitoru.
* ``FinalExamWaitConsumer``    — final gözləmə otağındakı tələbə kanalı
  (presence + sinxron start eventi).
"""

from __future__ import annotations

import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.exams.features import exam_supervision_enabled

logger = logging.getLogger("exams.supervision.ws")


class ExamSupervisionConsumer(AsyncJsonWebsocketConsumer):
    """
    Student connects to ws/exams/supervision/<attempt_id>/.
    Teacher actions (lock, resume, stop) are broadcast to this group.

    Group name: exam_supervision_<attempt_id>
    """

    async def connect(self):
        if not exam_supervision_enabled():
            await self.close(code=4403)
            return

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        try:
            self.attempt_id = int(self.scope["url_route"]["kwargs"]["attempt_id"])
        except (KeyError, TypeError, ValueError):
            await self.close(code=4400)
            return

        # Authorization (EXAM-SEC-001): only the student sitting this attempt —
        # or the exam author / a superadmin observing — may subscribe.  Without
        # it any authenticated user could tap another attempt's supervision feed
        # by guessing the sequential attempt id.
        if not await self._can_observe_attempt(user, self.attempt_id):
            await self.close(code=4403)
            return

        self.group_name = f"exam_supervision_{self.attempt_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _can_observe_attempt(self, user, attempt_id) -> bool:
        """
        Owner-scoped access to an attempt's realtime supervision feed.  The sole
        expected client is the student taking the attempt (they receive the
        teacher's lock/resume/stop events); the exam author and superadmins may
        also observe.  RLS is bypassed for the lookup so the legitimate owner is
        never rejected when the WebSocket scope carries no active-org context —
        authorization is enforced explicitly on ``user_id`` below.
        """
        from apps.exams.models import ExamAttempt
        from core.rls import bypass_rls

        with bypass_rls():
            row = ExamAttempt.objects.filter(pk=attempt_id).values("user_id", "exam__author_id").first()
        if row is None:
            return False
        if row["user_id"] == user.id:
            return True
        if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
            return True
        return row["exam__author_id"] == user.id

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def supervision_event(self, event):
        """
        Handle supervision events sent via channel layer group_send.
        Event format: {"type": "supervision_event", "data": {...}}
        """
        data = event.get("data") or {}
        await self.send_json(data)


# ---------------------------------------------------------------------------
# Final imtahan mərkəzi — otaq monitoru (nəzarətçi/heyət)
# ---------------------------------------------------------------------------


class FinalExamRoomConsumer(AsyncJsonWebsocketConsumer):
    """
    ws/exams/final/room/<session_id>/ — yalnız icazəli heyət.

    Giriş yoxlaması: autentifikasiya + tenant üzvlüyü + oturum təyinatı
    (imtahan mərkəzi / nəzarətçi / heyət). Tələbələr bu kanala qoşula BİLMƏZ.
    İdarəedici əməliyyatlar (start/son/çıxarma) WS ilə deyil, CSRF-qorumalı
    HTTP endpoint-ləri ilə gedir — WS yalnız oxu kanalıdır.
    """

    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        try:
            self.session_id = int(self.scope["url_route"]["kwargs"]["session_id"])
        except (KeyError, TypeError, ValueError):
            await self.close(code=4400)
            return

        if not await self._can_supervise(user, self.session_id):
            await self.close(code=4403)
            return

        from apps.exams.services.final_center import staff_group

        self.group_name = staff_group(self.session_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _can_supervise(self, user, session_id) -> bool:
        from apps.exams.models import ExamRoomSession
        from apps.exams.services.final_center import can_supervise_session_ws

        session = ExamRoomSession.objects.select_related("room").filter(pk=session_id).first()
        if session is None:
            return False
        return can_supervise_session_ws(user, session)

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Monitor kanalı oxu-yönümlüdür; yalnız ping-ə cavab verilir.
        if isinstance(content, dict) and content.get("action") == "ping":
            await self.send_json({"event": "pong"})

    async def final_event(self, event):
        await self.send_json(event.get("data") or {})


# ---------------------------------------------------------------------------
# Final imtahan mərkəzi — tələbə gözləmə/presence kanalı
# ---------------------------------------------------------------------------


class FinalExamWaitConsumer(AsyncJsonWebsocketConsumer):
    """
    ws/exams/final/wait/<ticket_id>/ — yalnız biletin öz sahibi.

    Presence Redis cache-də saxlanır (heartbeat başına DB sətri YOX).
    Sinxron start: ``room_started`` eventi bu kanala yayılır; hər tələbə
    öz attempt-ini autentifikasiyalı HTTP POST ilə açır (ağır payload
    WS-lə göndərilmir).
    """

    # İnbound mesajlar üçün minimal interval — spam qorunması.
    MIN_MESSAGE_INTERVAL = 3.0

    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        try:
            self.ticket_id = int(self.scope["url_route"]["kwargs"]["ticket_id"])
        except (KeyError, TypeError, ValueError):
            await self.close(code=4400)
            return

        info = await self._authorize(user, self.ticket_id)
        if info is None:
            await self.close(code=4403)
            return

        self.session_id = info["session_id"]
        self._last_message_ts = 0.0

        from apps.exams.services.final_center import students_group, ticket_group

        self.groups_joined = [ticket_group(self.ticket_id), students_group(self.session_id)]
        for group in self.groups_joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await self._mark_connected(info["reconnect"])

    @database_sync_to_async
    def _authorize(self, user, ticket_id):
        """
        Bilet sahibliyi + oturumun canlı olması. Çıxarılmış/bitmiş biletlər
        qoşula bilməz. Qaytarır: {"session_id", "reconnect"} | None.
        """
        from apps.exams.domain.final_center import (
            ROOM_SESSION_STATE_ACTIVE,
            ROOM_SESSION_STATE_ENTRY_OPEN,
            TICKET_STATUS_ACTIVE,
            TICKET_STATUS_READY,
            TICKET_STATUS_WAITING,
        )
        from apps.exams.models import FinalExamTicket

        ticket = FinalExamTicket.objects.select_related("session").filter(pk=ticket_id, student=user).first()
        if ticket is None:
            return None
        if ticket.status not in (TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE):
            return None
        if ticket.session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
            return None
        self._ticket_status = ticket.status
        return {"session_id": ticket.session_id, "reconnect": bool(ticket.last_seen_at)}

    @database_sync_to_async
    def _mark_connected_db(self, reconnect: bool):
        from django.db.models import F
        from django.utils import timezone

        from apps.exams.models import FinalExamTicket
        from apps.exams.services.final_center import broadcast_to_staff, touch_presence

        touch_presence(self.session_id, self.ticket_id, status=self._ticket_status)
        updates = {"last_seen_at": timezone.now()}
        if reconnect:
            updates["reconnect_count"] = F("reconnect_count") + 1
        FinalExamTicket.objects.filter(pk=self.ticket_id).update(**updates)
        broadcast_to_staff(
            self.session_id,
            {
                "event": "student_reconnected" if reconnect else "student_connected",
                "ticket_id": self.ticket_id,
            },
        )

    async def _mark_connected(self, reconnect: bool):
        await self._mark_connected_db(reconnect)

    async def disconnect(self, close_code):
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)
        if getattr(self, "session_id", None):
            await self._mark_disconnected()

    @database_sync_to_async
    def _mark_disconnected(self):
        from apps.exams.services.final_center import broadcast_to_staff, drop_presence

        drop_presence(self.session_id, self.ticket_id)
        broadcast_to_staff(
            self.session_id,
            {"event": "student_disconnected", "ticket_id": self.ticket_id},
        )

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        # Sadə throttle: həddən tez gələn mesajlar sükutla atılır.
        now = time.monotonic()
        if now - self._last_message_ts < self.MIN_MESSAGE_INTERVAL:
            return
        self._last_message_ts = now

        action = content.get("action")
        if action == "heartbeat":
            await self._heartbeat()
        elif action == "ready":
            await self._set_ready(bool(content.get("value", True)))

    @database_sync_to_async
    def _heartbeat(self):
        from apps.exams.models import FinalExamTicket
        from apps.exams.services.final_center import touch_presence, touch_ticket_last_seen

        touch_presence(self.session_id, self.ticket_id, status=self._ticket_status)
        ticket = FinalExamTicket.objects.filter(pk=self.ticket_id).only("id", "last_seen_at").first()
        if ticket:
            touch_ticket_last_seen(ticket)

    @database_sync_to_async
    def _set_ready(self, value: bool):
        from apps.exams.models import FinalExamTicket
        from apps.exams.services.final_center import set_ready

        ticket = FinalExamTicket.objects.select_related("session").filter(pk=self.ticket_id).first()
        if ticket is None:
            return
        if set_ready(ticket, value):
            self._ticket_status = ticket.status

    async def final_event(self, event):
        await self.send_json(event.get("data") or {})
