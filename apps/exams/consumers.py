"""
WebSocket consumer for real-time exam supervision notifications.

Allows the student to receive immediate lock/resume/stop events from the
teacher without relying on HTTP polling.
"""

from __future__ import annotations

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("exams.supervision.ws")


class ExamSupervisionConsumer(AsyncJsonWebsocketConsumer):
    """
    Student connects to ws/exams/supervision/<attempt_id>/.
    Teacher actions (lock, resume, stop) are broadcast to this group.

    Group name: exam_supervision_<attempt_id>
    """

    async def connect(self):
        self.attempt_id = self.scope["url_route"]["kwargs"]["attempt_id"]
        self.group_name = f"exam_supervision_{self.attempt_id}"

        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

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
