"""final_center paketi — final imtahan girişi (istifadəçi adı + PIN).

Təhlükəsizlik xətləri:

* IP + istifadəçi adı üzrə pəncərəli rate limit (cache-əsaslı);
* bilet-səviyyəli uğursuz cəhd sayğacı və müvəqqəti kilid (pins.py);
* generik xəta — istifadəçi adı və ya PIN-in hansının səhv olduğu deyilmir;
* istifadəçi tapılmayanda da hash yoxlaması aparılır (timing bərabərləşmə);
* xam PIN heç vaxt loglara/audit-ə yazılmır.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import FinalExamTicket
from apps.exams.services.exam_center_gate import get_client_ip
from core.audit import log_action
from core.constants import AuditAction

from .pins import equalize_verification_timing, verify_ticket_pin

logger = logging.getLogger("exams.final_center.entry")

User = get_user_model()

# View qatında session-a yazılan açar: PIN yoxlamasından keçmiş bilet id-si.
# Gate/waiting/begin səhifələri yalnız bu təsdiqdən sonra açılır.
ENTRY_SESSION_KEY = "final_exam_ticket_id"

# Generik xəta kodları → lokalizasiya view/template qatında.
ERROR_INVALID = "invalid_credentials"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_LOCKED = "temporarily_locked"
ERROR_NO_ACTIVE_SESSION = "no_active_session"


def _rate_key(kind: str, value: str) -> str:
    return f"finentry:{kind}:{value}"


def _rate_limited(request, username: str) -> bool:
    """Sadə pəncərəli sayğac: IP və istifadəçi adı üzrə dəqiqədə N cəhd."""
    limit = int(getattr(settings, "FINAL_EXAM_ENTRY_RATE_PER_MINUTE", 10))
    keys = [_rate_key("ip", get_client_ip(request) or "unknown")]
    if username:
        keys.append(_rate_key("user", username.strip().lower()[:150]))
    for key in keys:
        added = cache.add(key, 0, 60)
        try:
            count = cache.incr(key)
        except ValueError:  # açar TTL-i incr anında bitibsə
            cache.set(key, 1, 60)
            count = 1
        if added and count == 1:
            continue
        if count > limit:
            return True
    return False


def _candidate_ticket(user):
    """
    İstifadəçinin girişə uyğun bileti: oturumu giriş üçün açıq/aktiv olan,
    yekunlaşmamış bilet. Ən yaxın oturum seçilir.

    ``ACTIVE`` status da daxildir — YENİDƏN GİRİŞ üçün (brauzer çöküb/internet
    gedib/kompüter dəyişib). Amma bu YALNIZ nəzarətçi PIN-i yenidən verəndə
    işləyir: adi aktiv tələbənin PIN-i başlanğıcda ləğv olunur (``has_valid_pin``
    False) → ``verify_ticket_pin`` rədd edir. Yəni PIN hələ də birdəfəlikdir;
    yalnız nəzarətçinin yeni verdiyi PIN ilə olduğu yerdən davam etmək olur.
    """
    now = timezone.now()
    return (
        FinalExamTicket.objects.filter(
            student=user,
            status__in=(
                TICKET_STATUS_ASSIGNED,
                TICKET_STATUS_WAITING,
                TICKET_STATUS_READY,
                TICKET_STATUS_ACTIVE,
            ),
            session__state__in=(ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE),
        )
        .filter(Q(pin_expires_at__isnull=True) | Q(pin_expires_at__gt=now))
        .select_related("session", "session__room", "exam", "organization", "student")
        .order_by("session__scheduled_start")
        .first()
    )


def validate_entry(request, username: str, raw_pin: str):
    """
    Final girişinin tam yoxlaması.

    Qaytarır: ``(ticket, None)`` uğurda, ``(None, error_code)`` xətada.
    Xəta kodları QƏSDƏN generikdir — istifadəçi mövcudluğu sızdırılmır.
    """
    username = (username or "").strip()
    raw_pin = (raw_pin or "").strip()

    if _rate_limited(request, username):
        return None, ERROR_RATE_LIMITED

    if not username or not raw_pin:
        equalize_verification_timing(raw_pin)
        return None, ERROR_INVALID

    user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
    if user is None or not user.is_active:
        equalize_verification_timing(raw_pin)
        return None, ERROR_INVALID

    ticket = _candidate_ticket(user)
    if ticket is None:
        equalize_verification_timing(raw_pin)
        return None, ERROR_INVALID

    if ticket.is_pin_locked:
        # Kilid halında da doğrulama aparılır (timing), amma nəticə nəzərə alınmır.
        verify_ticket_pin(ticket, raw_pin)
        _log_suspicious(request, ticket, "pin_locked_attempt")
        return None, ERROR_LOCKED

    if not verify_ticket_pin(ticket, raw_pin):
        if ticket.is_pin_locked:
            _log_suspicious(request, ticket, "pin_lock_triggered")
            return None, ERROR_LOCKED
        return None, ERROR_INVALID

    now = timezone.now()
    if not ticket.entry_validated_at:
        ticket.entry_validated_at = now
        ticket.save(update_fields=["entry_validated_at", "updated_at"])

    log_action(
        AuditAction.VERIFY,
        user=user,
        organization=ticket.organization,
        obj=ticket,
        reason="final_entry_validated",
        request=request,
        resource_type="final_exam_ticket",
        resource_id=str(ticket.pk),
    )
    return ticket, None


def _log_suspicious(request, ticket, label: str) -> None:
    """Şübhəli giriş davranışı — audit-ə yazılır (PIN dəyəri YAZILMIR)."""
    log_action(
        AuditAction.DENY,
        user=None,
        organization=ticket.organization,
        obj=ticket,
        reason=f"final_entry_{label}",
        request=request,
        resource_type="final_exam_ticket",
        resource_id=str(ticket.pk),
    )


def store_entry_session(request, ticket) -> None:
    request.session[ENTRY_SESSION_KEY] = ticket.pk


def entry_ticket_id(request):
    return request.session.get(ENTRY_SESSION_KEY)


def clear_entry_session(request) -> None:
    request.session.pop(ENTRY_SESSION_KEY, None)


__all__ = [
    "ENTRY_SESSION_KEY",
    "ERROR_INVALID",
    "ERROR_LOCKED",
    "ERROR_NO_ACTIVE_SESSION",
    "ERROR_RATE_LIMITED",
    "clear_entry_session",
    "entry_ticket_id",
    "store_entry_session",
    "validate_entry",
]
