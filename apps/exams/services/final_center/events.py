"""final_center paketi — WebSocket yayım köməkçiləri.

Kompakt event sxemi: yalnız UI-nin yenilənməsi üçün lazım olan minimal
sahələr göndərilir — tam tələbə/imtahan payload-ları YAYILMIR. Kanal qatı
əlçatan olmayanda səssiz keçilir (HTTP axını pozulmur); fallback üçün
tələbə/staff tərəfdə aşağı-tezlikli polling endpoint-ləri var.

Qrup adları:
* ``final_room_{session_id}``          — nəzarətçi/heyət monitoru.
* ``final_room_students_{session_id}`` — gözləmə otağındakı tələbələr.
* ``final_ticket_{ticket_id}``         — konkret tələbənin fərdi kanalı.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger("exams.final_center.ws")


def staff_group(session_id: int) -> str:
    return f"final_room_{session_id}"


def students_group(session_id: int) -> str:
    return f"final_room_students_{session_id}"


def ticket_group(ticket_id: int) -> str:
    return f"final_ticket_{ticket_id}"


def _group_send(group_name: str, payload: dict) -> None:
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "final_event", "data": payload},
        )
    except Exception:  # noqa: BLE001 — yayım xətası əsas axını dayandırmamalıdır
        logger.warning("final_center WS yayımı alınmadı: %s", group_name, exc_info=True)


def broadcast_to_staff(session_id: int, payload: dict) -> None:
    _group_send(staff_group(session_id), payload)


def broadcast_to_students(session_id: int, payload: dict) -> None:
    _group_send(students_group(session_id), payload)


def notify_ticket(ticket_id: int, payload: dict) -> None:
    _group_send(ticket_group(ticket_id), payload)


__all__ = [
    "broadcast_to_staff",
    "broadcast_to_students",
    "notify_ticket",
    "staff_group",
    "students_group",
    "ticket_group",
]
