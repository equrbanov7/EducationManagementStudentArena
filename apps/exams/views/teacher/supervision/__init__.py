"""teacher supervision — geriyə-uyğun fasad paketi.

QEYD (2026-07-29): köhnə müəllim nəzarət UI-ı (supervision_monitor,
supervision_detail, exam_live_monitor + onların poll/snapshot/müdaxilə
API-ləri) tamamilə silindi. Canlı nəzarət artıq İmtahan Mərkəzinin zal
oturumu monitorundadır (``exams/exam_center/``); müdaxilə orada
session/ticket üzərindən aparılır (``exam_center_ticket_resume``).

Burada YALNIZ tələbənin imtahan səhifəsinin çağırdığı iki endpoint qalır —
onlar proctoring-in özəyidir (pozuntu qeydi + status yoxlaması) və
silinsəydi tam ekran/tab nəzarəti tamamilə sıradan çıxardı.
"""

from .monitor import (  # noqa: F401
    log_incident_api,
    supervision_status_api,
)

__all__ = [
    "log_incident_api",
    "supervision_status_api",
]
