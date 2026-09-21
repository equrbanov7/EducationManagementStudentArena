"""Final imtahan mərkəzi — zal oturumu və bilet state-machine sabitləri.

``final_center.py``-dan paketə bölünüb (modul-ölçü qapısı, 2026-09-21);
``apps.exams.domain.final_center`` eyni adları yenidən ixrac edir.
"""

# ---------------------------------------------------------------------------
# State machine sabitləri — DB-də saxlanan yeganə mənbə.
# Keçidlər backend-də ``transition_*`` helper-ləri ilə şərti UPDATE kimi
# tətbiq olunur (yarış şəraitində idempotent).
# ---------------------------------------------------------------------------

ROOM_SESSION_STATE_PREPARED = "prepared"
ROOM_SESSION_STATE_ENTRY_OPEN = "entry_open"
ROOM_SESSION_STATE_ACTIVE = "active"
ROOM_SESSION_STATE_ENDED = "ended"
ROOM_SESSION_STATE_CANCELLED = "cancelled"

ROOM_SESSION_STATES = (
    ROOM_SESSION_STATE_PREPARED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_CANCELLED,
)

# İcazəli keçidlər: mənbə → mümkün hədəflər.
ROOM_SESSION_TRANSITIONS = {
    ROOM_SESSION_STATE_PREPARED: {ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_CANCELLED},
    ROOM_SESSION_STATE_ENTRY_OPEN: {ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_CANCELLED},
    ROOM_SESSION_STATE_ACTIVE: {ROOM_SESSION_STATE_ENDED},
    ROOM_SESSION_STATE_ENDED: set(),
    ROOM_SESSION_STATE_CANCELLED: set(),
}

TICKET_STATUS_ASSIGNED = "assigned"
TICKET_STATUS_WAITING = "waiting"
TICKET_STATUS_READY = "ready"
TICKET_STATUS_ACTIVE = "active"
TICKET_STATUS_COMPLETED = "completed"
TICKET_STATUS_REMOVED = "removed"
TICKET_STATUS_ABSENT = "absent"

TICKET_STATUSES = (
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_WAITING,
    TICKET_STATUS_READY,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_ABSENT,
)

TICKET_TRANSITIONS = {
    TICKET_STATUS_ASSIGNED: {TICKET_STATUS_WAITING, TICKET_STATUS_REMOVED, TICKET_STATUS_ABSENT},
    TICKET_STATUS_WAITING: {
        TICKET_STATUS_READY,
        TICKET_STATUS_ASSIGNED,  # tələbə gözləmə otağından imtina etdi (attempt yanmır)
        TICKET_STATUS_ACTIVE,
        TICKET_STATUS_REMOVED,
        TICKET_STATUS_ABSENT,
    },
    TICKET_STATUS_READY: {
        TICKET_STATUS_WAITING,
        TICKET_STATUS_ACTIVE,
        TICKET_STATUS_REMOVED,
        TICKET_STATUS_ABSENT,
    },
    TICKET_STATUS_ACTIVE: {TICKET_STATUS_COMPLETED, TICKET_STATUS_REMOVED},
    TICKET_STATUS_COMPLETED: set(),
    # Yenidən buraxılma yalnız imtahan mərkəzi qərarı ilə (re-admit).
    TICKET_STATUS_REMOVED: {TICKET_STATUS_ASSIGNED},
    TICKET_STATUS_ABSENT: set(),
}

# Gözləmə otağında "canlı" sayılan ticket statusları (monitor sayğacları üçün).
TICKET_LIVE_STATUSES = (TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE)
