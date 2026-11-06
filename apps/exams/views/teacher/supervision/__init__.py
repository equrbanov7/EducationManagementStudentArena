"""teacher supervision — geriyə-uyğun fasad paketi.

QEYD (2026-07-29): köhnə müəllim nəzarət UI-ı (supervision_monitor,
supervision_detail, exam_live_monitor + onların poll/snapshot/müdaxilə
API-ləri) tamamilə silindi. Canlı nəzarət artıq İmtahan Mərkəzinin zal
oturumu monitorundadır (``exams/exam_center/``); müdaxilə orada
session/ticket üzərindən aparılır (``exam_center_ticket_resume``).

2026-11-06 (sahib): ``room`` — imtahan səviyyəli «Nəzarət otağı» (bütün növlər, biletsiz) geri
gəldi; zal axınında olmayan quiz/yazılı/praktiki imtahanlarda kilidli tələbəni bərpa etməyin yeganə yolu.

Qalanı tələbənin imtahan səhifəsinin çağırdığı endpoint-lərdir —
onlar proctoring-in özəyidir (pozuntu qeydi + status yoxlaması) və
silinsəydi tam ekran/tab nəzarəti tamamilə sıradan çıxardı.
"""

from .monitor import (  # noqa: F401
    log_incident_api,
    supervision_status_api,
)
from .room import (  # noqa: F401
    exam_supervision_attempt_pause,
    exam_supervision_attempt_resume,
    exam_supervision_attempt_snapshot,
    exam_supervision_room,
    exam_supervision_room_snapshot,
)
from .signals import heartbeat_api, log_signal_api  # noqa: F401

__all__ = [
    "exam_supervision_attempt_pause",
    "exam_supervision_attempt_resume",
    "exam_supervision_attempt_snapshot",
    "exam_supervision_room",
    "exam_supervision_room_snapshot",
    "heartbeat_api",
    "log_incident_api",
    "log_signal_api",
    "supervision_status_api",
]
