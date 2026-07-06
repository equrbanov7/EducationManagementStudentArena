"""final_center paketi — zal oturumu həyat dövrü.

Rəsmi start/son vaxtının mənbəyi YALNIZ backend-dir: state keçidləri şərti
(atomik, idempotent) UPDATE ilə aparılır — iki nəzarətçinin eyni anda "başlat"
basması, təkrar kliklər və çoxlu app instansı təhlükəsizdir.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_CANCELLED,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import ExamAttempt, ExamRoomSession, FinalExamTicket
from core.audit import log_action
from core.constants import AuditAction

from .events import broadcast_to_staff, broadcast_to_students
from .presence import connected_count

logger = logging.getLogger("exams.final_center")

# Oturum planlaşdırılan başlanğıcdan bu qədər ƏVVƏL başladıla bilməz
# (override qeydə alınmadan) — bax start_room(override=...).
START_EARLY_TOLERANCE = timedelta(minutes=15)


class RoomSessionStateError(ValueError):
    """Yanlış state keçidi — istifadəçiyə lokalizə edilmiş mesajla qaytarılır."""


def _audit_session(session, *, action, user=None, request=None, reason="", changes=None):
    log_action(
        action,
        user=user,
        organization=session.organization,
        obj=session,
        changes=changes,
        reason=reason,
        request=request,
        resource_type="exam_room_session",
        resource_id=str(session.pk),
        resource_repr=str(session),
    )


def validate_session_plan(*, room, exam, scheduled_start, scheduled_end, exclude_pk=None):
    """
    Oturum planının yoxlamaları:
    * imtahan və zal eyni təşkilatda olmalıdır;
    * bitmə vaxtı başlama vaxtından sonra olmalıdır;
    * zaldakı üst-üstə düşən oturumların ümumi tutumu zal tutumunu aşmamalıdır.

    QEYD: bir zalda EYNİ ANDA çoxlu (fərqli fənn) oturum ola bilər — bu,
    imtahan zalı ssenarisinin əsasıdır (nəzarətçi hamısını birlikdə idarə edir).
    Ona görə üst-üstə düşmə ÖZLÜYÜNDƏ xəta deyil; yalnız tutum aşılması bloklanır.
    Xəta halında ``RoomSessionStateError`` atılır.
    """
    if room.organization_id != exam.organization_id:
        raise RoomSessionStateError(
            pgettext("exams.final_center.error", "Zal və imtahan eyni təşkilata aid olmalıdır.")
        )
    if scheduled_end <= scheduled_start:
        raise RoomSessionStateError(
            pgettext("exams.final_center.error", "Oturumun bitmə vaxtı başlama vaxtından sonra olmalıdır.")
        )

    capacity = room.capacity or 0
    if capacity:
        overlapping = (
            ExamRoomSession.objects.filter(room=room)
            .exclude(state__in=(ROOM_SESSION_STATE_ENDED, ROOM_SESSION_STATE_CANCELLED))
            .filter(scheduled_start__lt=scheduled_end, scheduled_end__gt=scheduled_start)
        )
        if exclude_pk:
            overlapping = overlapping.exclude(pk=exclude_pk)
        # Üst-üstə düşən oturumlara artıq təyin olunmuş tələbələr zal tutumunu
        # aşırsa yeni oturum bloklanır (kompüterlər çatmır).
        assigned_total = FinalExamTicket.objects.filter(session__in=overlapping).exclude(status="removed").count()
        if assigned_total >= capacity:
            raise RoomSessionStateError(
                pgettext(
                    "exams.final_center.error",
                    "Bu zalda seçilmiş vaxt aralığında tutum dolub ({total}/{capacity}).",
                ).format(total=assigned_total, capacity=capacity)
            )


def _live_ticket_ids(session):
    return list(
        session.tickets.filter(
            status__in=(TICKET_STATUS_ASSIGNED, TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE)
        ).values_list("id", flat=True)
    )


def open_entry(session, by, *, request=None) -> bool:
    """prepared → entry_open. İdempotent: artıq açıqdırsa False."""
    now = timezone.now()
    updated = ExamRoomSession.objects.filter(pk=session.pk, state=ROOM_SESSION_STATE_PREPARED).update(
        state=ROOM_SESSION_STATE_ENTRY_OPEN, entry_opened_at=now, updated_at=now
    )
    if not updated:
        return False
    session.refresh_from_db(fields=["state", "entry_opened_at"])
    _audit_session(
        session,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_room_entry_opened",
        changes={"state": [ROOM_SESSION_STATE_PREPARED, ROOM_SESSION_STATE_ENTRY_OPEN]},
    )
    broadcast_to_staff(session.pk, {"event": "entry_opened", "session_id": session.pk})
    return True


def start_room(session, by, *, request=None, override=False) -> bool:
    """
    entry_open → active. Sinxron start:

    1. İcazə view qatında yoxlanılıb; burada state + vaxt pəncərəsi yoxlanır.
    2. Şərti UPDATE — təkrar start / paralel start təhlükəsizdir.
    3. Rəsmi server start vaxtı yazılır; qoşulu tələbə sayı snapshot alınır.
    4. Tələbələrə YÜNGÜL "room_started" eventi yayılır — sual seti WS ilə
       GÖNDƏRİLMİR; hər tələbə öz attempt-ini autentifikasiyalı HTTP ilə açır.
    """
    now = timezone.now()
    if not override and now < session.scheduled_start - START_EARLY_TOLERANCE:
        raise RoomSessionStateError(
            pgettext(
                "exams.final_center.error",
                "Oturum planlaşdırılan vaxtdan çox tez başladıla bilməz (override tələb olunur).",
            )
        )
    if not override and now > session.scheduled_end:
        raise RoomSessionStateError(
            pgettext(
                "exams.final_center.error", "Oturumun planlaşdırılan sonu keçib — start üçün override tələb olunur."
            )
        )

    connected = connected_count(session.pk, _live_ticket_ids(session))
    updated = ExamRoomSession.objects.filter(pk=session.pk, state=ROOM_SESSION_STATE_ENTRY_OPEN).update(
        state=ROOM_SESSION_STATE_ACTIVE,
        started_at=now,
        started_by=by,
        start_connected_count=connected,
        updated_at=now,
    )
    if not updated:
        return False
    session.refresh_from_db(fields=["state", "started_at", "started_by", "start_connected_count"])

    _audit_session(
        session,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_room_started" + ("_override" if override else ""),
        changes={
            "state": [ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE],
            "connected_students": [None, connected],
        },
    )
    payload = {
        "event": "room_started",
        "session_id": session.pk,
        "started_at": session.started_at.isoformat(),
        "server_now": timezone.now().isoformat(),
    }
    broadcast_to_students(session.pk, payload)
    broadcast_to_staff(session.pk, payload)
    return True


def _finalize_session_attempts(session) -> dict:
    """
    Oturum bitəndə aktiv attempt-ləri yekunlaşdırır (autosave cavabları qorunur).
    Tələbənin paralel submit-i ilə yarış attempt sətrinin lock-u ilə həll olunur
    (take_exam POST-u da select_for_update işlədir).
    """
    finalized = 0
    attempts = (
        ExamAttempt.objects.select_for_update()
        .filter(final_tickets__session=session)
        .exclude(status__in=("submitted", "expired"))
        .select_related("exam")
    )
    for attempt in attempts:
        attempt.mark_finished(status="submitted")
        finalized += 1
    return {"finalized_attempts": finalized}


def end_room(session, by, *, request=None, auto=False) -> bool:
    """
    active → ended. Atomik + idempotent:

    * aktiv attempt-lər avtomatik təhvil verilir (cavablar qorunur);
    * aktiv biletlər ``completed``, imtahana başlamayanlar ``absent`` olur;
    * PIN-lərin şifrəli nüsxələri silinir (hash tarixçə üçün qalır);
    * otağa yüngül ``room_ended`` eventi yayılır.
    """
    now = timezone.now()
    with transaction.atomic():
        updated = ExamRoomSession.objects.filter(pk=session.pk, state=ROOM_SESSION_STATE_ACTIVE).update(
            state=ROOM_SESSION_STATE_ENDED, ended_at=now, ended_by=by, updated_at=now
        )
        if not updated:
            return False

        stats = _finalize_session_attempts(session)

        stats["completed_tickets"] = session.tickets.filter(status=TICKET_STATUS_ACTIVE).update(
            status=TICKET_STATUS_COMPLETED, completed_at=now, updated_at=now
        )
        stats["absent_tickets"] = session.tickets.filter(
            status__in=(TICKET_STATUS_ASSIGNED, TICKET_STATUS_WAITING, TICKET_STATUS_READY)
        ).update(status=TICKET_STATUS_ABSENT, updated_at=now)
        # Şifrəli PIN nüsxələri artıq lazım deyil — minimallaşdırma.
        session.tickets.exclude(pin_cipher="").update(pin_cipher="")

    session.refresh_from_db(fields=["state", "ended_at", "ended_by"])
    _audit_session(
        session,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason="final_room_ended_auto" if auto else "final_room_ended",
        changes={"state": [ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_ENDED], **stats},
    )
    payload = {
        "event": "room_ended",
        "session_id": session.pk,
        "ended_at": session.ended_at.isoformat(),
        "auto": auto,
    }
    broadcast_to_students(session.pk, payload)
    broadcast_to_staff(session.pk, payload)
    return True


def cancel_session(session, by, *, request=None, reason="") -> bool:
    """prepared/entry_open → cancelled. Biletlər saxlanır, PIN-lər ləğv olunur."""
    now = timezone.now()
    updated = ExamRoomSession.objects.filter(
        pk=session.pk, state__in=(ROOM_SESSION_STATE_PREPARED, ROOM_SESSION_STATE_ENTRY_OPEN)
    ).update(state=ROOM_SESSION_STATE_CANCELLED, ended_at=now, ended_by=by, updated_at=now)
    if not updated:
        return False
    session.tickets.update(pin_revoked_at=now, pin_cipher="", updated_at=now)
    session.refresh_from_db(fields=["state", "ended_at", "ended_by"])
    _audit_session(
        session,
        action=AuditAction.UPDATE,
        user=by,
        request=request,
        reason=f"final_room_cancelled: {reason}"[:500],
        changes={"state": [None, ROOM_SESSION_STATE_CANCELLED]},
    )
    payload = {"event": "session_cancelled", "session_id": session.pk}
    broadcast_to_students(session.pk, payload)
    broadcast_to_staff(session.pk, payload)
    return True


def maybe_auto_end(session) -> bool:
    """
    Rəsmi server deadline-ı: aktiv oturum planlaşdırılan sonu keçibsə
    avtomatik bitirilir. Monitor snapshot-ı və tələbə state endpoint-i
    tərəfindən "lazy" çağırılır — ayrıca yüksək tezlikli cron tələb olunmur.
    """
    if session.state != ROOM_SESSION_STATE_ACTIVE:
        return False
    if timezone.now() < session.scheduled_end:
        return False
    return end_room(session, None, auto=True)


__all__ = [
    "RoomSessionStateError",
    "START_EARLY_TOLERANCE",
    "cancel_session",
    "end_room",
    "maybe_auto_end",
    "open_entry",
    "start_room",
    "validate_session_plan",
]
