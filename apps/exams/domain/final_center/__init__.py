"""
Final imtahan mərkəzi domain modelləri.

Mərkəzləşdirilmiş universitet final imtahanları üçün:

* ``ExamRoom``          — fiziki imtahan zalı (org-scoped resurs).
* ``ExamRoomSession``   — bir imtahanın bir zalda keçirilən oturumu
                          (nəzarətçi, rəsmi start/son, state machine).
* ``FinalExamTicket``   — tələbənin oturuma təyinatı + şəxsi PIN +
                          həyat dövrü (waiting → active → completed).

Mövcud sistemlə inteqrasiya: sual/attempt/nəticə axını üçün ``Exam`` və
``ExamAttempt`` modelləri OLDUĞU KİMİ istifadə olunur — burada yalnız
zal/oturum/PIN qatı əlavə edilir. Supervision (anti-cheat) qatı da mövcud
``ExamSupervisionConfig``/``SupervisionIncident`` üzərində qalır.

MODUL BÖLGÜSÜ (2026-09-21, modul-ölçü qapısı): tək ``final_center.py`` paketə
çevrilib — ``states.py`` (sabitlər), ``rooms.py`` (``ExamRoom`` /
``ExamRoomComputer``), ``sessions.py`` (``ExamRoomSession``), ``tickets.py``
(``FinalExamTicket``). Bütün adlar buradan yenidən ixrac olunur;
``from apps.exams.domain.final_center import …`` yolu dəyişmir.
"""

from .rooms import ExamRoom, ExamRoomComputer
from .sessions import ExamRoomSession
from .states import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_CANCELLED,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
    ROOM_SESSION_STATES,
    ROOM_SESSION_TRANSITIONS,
    TICKET_LIVE_STATUSES,
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
    TICKET_STATUSES,
    TICKET_TRANSITIONS,
)
from .tickets import FinalExamTicket

__all__ = [
    "ExamRoom",
    "ExamRoomComputer",
    "ExamRoomSession",
    "FinalExamTicket",
    "ROOM_SESSION_STATES",
    "ROOM_SESSION_STATE_PREPARED",
    "ROOM_SESSION_STATE_ENTRY_OPEN",
    "ROOM_SESSION_STATE_ACTIVE",
    "ROOM_SESSION_STATE_ENDED",
    "ROOM_SESSION_STATE_CANCELLED",
    "ROOM_SESSION_TRANSITIONS",
    "TICKET_STATUSES",
    "TICKET_STATUS_ASSIGNED",
    "TICKET_STATUS_WAITING",
    "TICKET_STATUS_READY",
    "TICKET_STATUS_ACTIVE",
    "TICKET_STATUS_COMPLETED",
    "TICKET_STATUS_REMOVED",
    "TICKET_STATUS_ABSENT",
    "TICKET_TRANSITIONS",
    "TICKET_LIVE_STATUSES",
]
