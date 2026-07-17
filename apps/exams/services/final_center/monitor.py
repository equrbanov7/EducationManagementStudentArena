"""final_center paketi — nəzarətçi monitoru üçün kompakt snapshot.

Tək sorğu + presence cache oxunuşu ilə qurulur (N+1 yoxdur). Snapshot həm
ilkin səhifə render-i, həm WS-siz fallback polling üçün eyni formatda
istifadə olunur ki, iki mənbə heç vaxt ayrılmasın.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.exams.domain.final_center import (
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)

from .presence import presence_map
from .sessions import maybe_auto_end
from .tickets import sync_ticket_completion

# Bitmiş tələbənin nəticəsi kompüter xəritəsində maks bu qədər saniyə görünür,
# sonra hücrə boşalır (yeni tələbə üçün). Seat yeni aktiv tələbə ilə tutulubsa
# köhnə nəticə DƏRHAL düşür.
FINAL_RESULT_VISIBLE_SECONDS = 180

# Biletsiz (ExamStudentPin) cəhdin bitmiş nəticəsi zal monitorunda bu qədər
# saat görünür (canlı cəhdlər həmişə görünür).
ROOM_ATTEMPT_FINISHED_VISIBLE_HOURS = 8


def _visible_grid_tickets(tickets):
    """
    Kompüter xəritəsi (grid) üçün GÖRÜNƏN biletləri süzür — sayğaclara TOXUNMUR
    (sayğaclar bütün biletlərdən hesablanır, bu yalnız görüntü qatıdır):

    * bitmiş (``completed``) bilet nəticəsi maks ``FINAL_RESULT_VISIBLE_SECONDS``
      görünür, sonra xəritədən düşür;
    * həmin seat-i (fiziki kompüteri) yeni aktiv/gözləyən tələbə tutubsa, köhnə
      bitmiş bilet dərhal gizlənir ki, xəritədə yeni tələbə görünsün.
    """
    now = timezone.now()
    occupied_seats = {
        t.seat_number
        for t in tickets
        if t.seat_number is not None and t.status in (TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE)
    }
    visible = []
    for ticket in tickets:
        if ticket.status == TICKET_STATUS_COMPLETED:
            if ticket.seat_number is not None and ticket.seat_number in occupied_seats:
                continue
            if ticket.completed_at and (now - ticket.completed_at).total_seconds() > FINAL_RESULT_VISIBLE_SECONDS:
                continue
        visible.append(ticket)
    return visible


def _ticket_row(ticket, presence, exam_title=None):
    """Yalnız əməliyyat üçün lazım olan kompakt sahələr — cavablar/ballar YOX.
    ``exam_title`` biletin öz imtahanından götürülür (hər tələbə öz imtahanı) —
    oturum artıq imtahandan asılı deyil (oturum sisteminin ləğvi)."""
    if exam_title is None and ticket.exam_id:
        exam_title = ticket.exam.title
    attempt = ticket.attempt
    remaining_seconds = None
    if attempt and not attempt.is_finished and attempt.deadline_at:
        remaining_seconds = max(0, int((attempt.deadline_at - timezone.now()).total_seconds()))
    return {
        "ticket_id": ticket.pk,
        "attempt_id": ticket.attempt_id,
        "student_id": ticket.student_id,
        "name": ticket.student.get_full_name() or ticket.student.username,
        "username": ticket.student.username,
        "seat": ticket.seat_number,
        # Cəhd hansı fiziki kompüterlə möhürlənib — zal xəritəsi overlay-ı
        # seat_number NULL olsa belə (kompüterin seat-i yoxdursa/seat toqquşması)
        # doğru kompüteri tapsın deyə birbaşa computer id.
        "computer_id": attempt.room_computer_id if attempt else None,
        "status": ticket.status,
        "language": ticket.language,
        "connected": ticket.pk in presence,
        "pin_issued": bool(ticket.pin_hash and not ticket.pin_revoked_at),
        "pin_locked": ticket.is_pin_locked,
        "reconnect_count": ticket.reconnect_count,
        "last_seen_at": ticket.last_seen_at.isoformat() if ticket.last_seen_at else None,
        "started_at": ticket.started_at.isoformat() if ticket.started_at else None,
        "completed_at": ticket.completed_at.isoformat() if ticket.completed_at else None,
        "remaining_seconds": remaining_seconds,
        "supervision_status": attempt.supervision_status if attempt else None,
        "violation_count": attempt.supervision_violation_count if attempt else 0,
        "removal_action": ticket.removal_action,
        "session_id": ticket.session_id,
        "exam_title": exam_title,
    }


def session_monitor_snapshot(session):
    """Oturumun canlı vəziyyəti: sayğaclar + tələbə sətirləri (kompakt)."""
    # Rəsmi server deadline-ı lazily tətbiq olunur.
    maybe_auto_end(session)

    tickets = list(
        session.tickets.select_related("student", "attempt", "exam").order_by(
            "seat_number", "student__first_name", "id"
        )
    )
    # Attempt bitmiş, bilet hələ "active" qalmış sətirləri sinxonlaşdır (lazy).
    for ticket in tickets:
        if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
            sync_ticket_completion(ticket)

    presence = presence_map(session.pk, [t.pk for t in tickets])

    counts = {
        "assigned": 0,
        "waiting": 0,
        "ready": 0,
        "active": 0,
        "completed": 0,
        "removed": 0,
        "absent": 0,
        "connected": len(presence),
        "total": len(tickets),
    }
    for ticket in tickets:
        if ticket.status in counts:
            counts[ticket.status] += 1
    counts["offline"] = max(
        0,
        counts["waiting"] + counts["ready"] + counts["active"] - counts["connected"],
    )
    # İmtahan verib (iştirak edən) = cəhdə başlamış hər kəs (aktiv + bitirmiş).
    counts["participated"] = counts["active"] + counts["completed"]

    return {
        "session_id": session.pk,
        "state": session.state,
        "room_name": session.room.name,
        "room_capacity": session.room.capacity,
        "scheduled_start": session.scheduled_start.isoformat(),
        "scheduled_end": session.scheduled_end.isoformat(),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "server_now": timezone.now().isoformat(),
        "counts": counts,
        "students": [_ticket_row(t, presence) for t in _visible_grid_tickets(tickets)],
    }


def room_live_sessions(room):
    """Zalda canlı (giriş açıq / aktiv) oturumlar — fənn üzrə sıralı."""
    from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_ENTRY_OPEN
    from apps.exams.models import ExamRoomSession

    sessions = list(
        ExamRoomSession.objects.filter(
            room=room, state__in=(ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
        ).order_by("scheduled_start", "id")
    )
    # Rəsmi deadline-ı lazily tətbiq et, sonra hələ canlı qalanları saxla.
    for session in sessions:
        maybe_auto_end(session)
    return [s for s in sessions if s.state in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)]


def _room_attempt_rows(room):
    """
    Biletsiz (ExamStudentPin) canlı cəhdlər — zal kompüterindən girişdə cəhd
    ``room``/``room_computer`` ilə möhürlənir (bax final_center view). Oturum/
    bilet sistemi işlədilməyən imtahanlar da zal monitorunda görünsün deyə
    snapshot-a bu sətirlər əlavə olunur. Bitmiş cəhdlər son
    ``ROOM_ATTEMPT_FINISHED_VISIBLE_HOURS`` saat ərzində göstərilir.
    """
    from datetime import timedelta

    from apps.exams.models import ExamAttempt

    since = timezone.now() - timedelta(hours=ROOM_ATTEMPT_FINISHED_VISIBLE_HOURS)
    attempts = (
        ExamAttempt.objects.filter(room=room, is_trial=False)
        .filter(Q(status="in_progress") | Q(finished_at__gte=since))
        # Biletli cəhdlər bilet sətri kimi göstərilir — dublikat olmasın.
        .filter(final_tickets__isnull=True)
        .select_related("user", "exam", "room_computer")
        .order_by("exam__title", "id")
    )
    rows = []
    for attempt in attempts:
        # Lazy auto-finish: deadline-ı keçmiş cəhd monitor oxunanda dərhal
        # bitmiş görünsün (periodik sweep-i gözləmədən). Cavablar qorunur.
        if attempt.status == "in_progress":
            attempt.expire_if_time_limit_reached()
        remaining_seconds = None
        if not attempt.is_finished and attempt.deadline_at:
            remaining_seconds = max(0, int((attempt.deadline_at - timezone.now()).total_seconds()))
        live = attempt.status == "in_progress"
        rows.append(
            {
                # Bilet yoxdur — JS bilet əməliyyatlarını (data-ticket) bu
                # sətirlər üçün göstərmir (ticket_id=None).
                "ticket_id": None,
                "attempt_id": attempt.id,
                "student_id": attempt.user_id,
                "name": attempt.user.get_full_name() or attempt.user.username,
                "username": attempt.user.username,
                "seat": attempt.room_computer.seat_number if attempt.room_computer else None,
                "computer_id": attempt.room_computer_id,
                "status": TICKET_STATUS_ACTIVE if live else TICKET_STATUS_COMPLETED,
                "language": attempt.language,
                "connected": live,
                "pin_issued": True,
                "pin_locked": False,
                "reconnect_count": 0,
                "last_seen_at": None,
                "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                "completed_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                "remaining_seconds": remaining_seconds,
                "supervision_status": attempt.supervision_status,
                "violation_count": attempt.supervision_violation_count,
                "removal_action": "",
                "session_id": f"exam-{attempt.exam_id}",
                "exam_title": attempt.exam.title,
            }
        )
    return rows


def room_monitor_snapshot(room):
    """
    Zal-səviyyəli aqreqasiya: zaldakı BÜTÜN canlı oturumların (imtahanların)
    tələbələrini birləşdirir. Hər sətir fənn/imtahan adı ilə etiketlənir;
    nəzarətçi bir zalda neçə imtahan varsa hamısını bir ekranda görür.
    Oturumsuz (biletsiz PIN) cəhdlər də zal kompüterinə görə əlavə olunur.
    """
    from collections import defaultdict

    from apps.exams.models import FinalExamTicket

    sessions = room_live_sessions(room)
    session_ids = [s.pk for s in sessions]

    tickets = list(
        FinalExamTicket.objects.filter(session_id__in=session_ids)
        .select_related("student", "attempt", "session", "exam")
        .order_by("exam__title", "seat_number", "id")
    )
    for ticket in tickets:
        if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
            sync_ticket_completion(ticket)

    # Presence hər oturum üçün ayrıca cache açarındadır; bilet id-ləri qlobal
    # unikaldır, ona görə birləşdirilə bilər.
    by_session = defaultdict(list)
    for ticket in tickets:
        by_session[ticket.session_id].append(ticket.pk)
    presence = {}
    for sid, ids in by_session.items():
        presence.update(presence_map(sid, ids))

    counts = {
        "assigned": 0,
        "waiting": 0,
        "ready": 0,
        "active": 0,
        "completed": 0,
        "removed": 0,
        "absent": 0,
        "connected": len(presence),
        "total": len(tickets),
    }
    for ticket in tickets:
        if ticket.status in counts:
            counts[ticket.status] += 1

    # Biletsiz (PIN) cəhdlər: sayğaclara və tələbə siyahısına əlavə olunur;
    # hər imtahan üçün psevdo-oturum çipi göstərilir (filter də işləsin).
    attempt_rows = _room_attempt_rows(room)
    for row in attempt_rows:
        counts["total"] += 1
        counts[row["status"]] += 1
        if row["connected"]:
            counts["connected"] += 1
    attempt_exams = {}
    for row in attempt_rows:
        if row["status"] == TICKET_STATUS_ACTIVE:
            attempt_exams.setdefault(row["session_id"], row["exam_title"])

    counts["offline"] = max(0, counts["waiting"] + counts["ready"] + counts["active"] - counts["connected"])
    counts["participated"] = counts["active"] + counts["completed"]

    return {
        "room_id": room.pk,
        "room_name": room.name,
        "room_code": room.code,
        "server_now": timezone.now().isoformat(),
        "counts": counts,
        "sessions": [
            {
                "session_id": s.pk,
                "state": s.state,
                "scheduled_start": s.scheduled_start.isoformat(),
                "scheduled_end": s.scheduled_end.isoformat(),
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in sessions
        ]
        + [
            {
                "session_id": sid,
                "state": "active",
                "exam_title": title,
                "scheduled_start": None,
                "scheduled_end": None,
                "started_at": None,
            }
            for sid, title in attempt_exams.items()
        ],
        "students": [_ticket_row(t, presence) for t in _visible_grid_tickets(tickets)] + attempt_rows,
    }


def session_list_annotations(queryset):
    """Oturum siyahısı üçün sayğac annotasiyaları (tək sorğu, N+1 yox)."""
    return queryset.annotate(
        ticket_total=Count("tickets", distinct=True),
        ticket_waiting=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_WAITING), distinct=True),
        ticket_ready=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_READY), distinct=True),
        ticket_active=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_ACTIVE), distinct=True),
        ticket_completed=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_COMPLETED), distinct=True),
        ticket_removed=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_REMOVED), distinct=True),
        ticket_absent=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_ABSENT), distinct=True),
        ticket_assigned=Count("tickets", filter=Q(tickets__status=TICKET_STATUS_ASSIGNED), distinct=True),
    )


__all__ = [
    "room_live_sessions",
    "room_monitor_snapshot",
    "session_list_annotations",
    "session_monitor_snapshot",
]
