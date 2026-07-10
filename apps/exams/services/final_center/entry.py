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
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
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


def _candidate_tickets(user):
    """
    İstifadəçinin girişə namizəd biletləri: yekunlaşmamış, PIN-i etibarlı olan
    biletlər (oturum sisteminin ləğvindən sonra — 2026-07 — SESSION FİLTRİ YOX,
    çünki bilet giriş anında zala qoşulur, əvvəldən bağlı deyil).

    İstifadəçi eyni anda birdən çox finala təyin ola bilər → HAMISI qaytarılır;
    PIN doğrulaması hansı biletə uyğun gəldiyini müəyyən edir (``validate_entry``).
    ``ACTIVE`` da daxildir — yenidən giriş üçün (nəzarətçi yeni PIN verib).
    """
    now = timezone.now()
    return list(
        FinalExamTicket.objects.filter(
            student=user,
            status__in=(
                TICKET_STATUS_ASSIGNED,
                TICKET_STATUS_WAITING,
                TICKET_STATUS_READY,
                TICKET_STATUS_ACTIVE,
            ),
        )
        .filter(Q(pin_expires_at__isnull=True) | Q(pin_expires_at__gt=now))
        .select_related("session", "session__room", "exam", "organization", "student")
        .order_by("-created_at")
    )


def validate_entry(request, username: str, raw_pin: str):
    """
    Final girişinin tam yoxlaması (yalnız PIN + istifadəçi — ZAL YOX).

    Zal həlli (kompüter IP → zal) və oturuma qoşulma view qatındadır (bax
    ``final_center.py`` + ``attach_ticket_to_room_sitting``).

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

    candidates = _candidate_tickets(user)
    if not candidates:
        equalize_verification_timing(raw_pin)
        return None, ERROR_INVALID

    ticket = None
    for cand in candidates:
        if cand.is_pin_locked:
            verify_ticket_pin(cand, raw_pin)  # timing bərabərləşməsi; nəticə nəzərə alınmır
            continue
        if verify_ticket_pin(cand, raw_pin):
            ticket = cand
            break

    if ticket is None:
        # Heç bir biletə uyğun gəlmədi — kilidli bilet varsa xüsusi mesaj.
        if any(c.is_pin_locked for c in candidates):
            _log_suspicious(request, candidates[0], "pin_locked_attempt")
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


# PIN axını üçün avtomatik yaradılan zal oturumunun standart müddəti.
# start_room vaxt pəncərəsi və maybe_auto_end bu intervala baxır.
AUTO_SITTING_DURATION_HOURS = 6


def ensure_open_room_sitting(room):
    """
    Otağın canlı (giriş-açıq/aktiv) oturumunu qaytarır; yoxdursa PIN axını
    üçün AVTOMATİK giriş-açıq oturum yaradır — imtahan mərkəzi əvvəlcədən
    oturum planlaşdırmalı deyil. Nəzarətçi zal monitorunda «Başlat» vuranda
    bu oturum aktivləşir və gözləyən tələbələr imtahana keçir.
    """
    from datetime import timedelta

    from apps.exams.models import ExamRoomSession
    from core.rls import bypass_rls

    live_states = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
    now = timezone.now()
    # Public giriş axını (tələbə hələ login olmayıb) — RLS bypass (bax
    # attach_ticket_to_room_sitting).
    with bypass_rls():
        sitting = (
            ExamRoomSession.objects.filter(room=room, state__in=live_states).order_by("scheduled_start", "id").first()
        )
        if sitting is not None:
            return sitting
        return ExamRoomSession.objects.create(
            organization_id=room.organization_id,
            room=room,
            state=ROOM_SESSION_STATE_ENTRY_OPEN,
            entry_opened_at=now,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=AUTO_SITTING_DURATION_HOURS),
        )


def ensure_pin_ticket(exam, student, room, computer=None):
    """
    ExamStudentPin girişi üçün bileti tapır/yaradır və otağın oturumuna qoşur.

    Bilet burada yalnız DAXİLİ vəziyyət daşıyıcısıdır (gözləmə otağı, sinxron
    start, zal monitoru) — autentifikasiya artıq ExamStudentPin ilə aparılıb,
    biletin öz PIN sahələri istifadə olunmur/doldurulmur.

    Qaytarır: ``(ticket, None)`` uğurda, ``(None, error_message)`` rədd halında.
    """
    from django.utils.translation import pgettext

    from core.rls import bypass_rls

    with bypass_rls():
        ticket, _created = FinalExamTicket.objects.get_or_create(
            exam=exam,
            student=student,
            defaults={"organization_id": exam.organization_id},
        )
    if ticket.status == TICKET_STATUS_COMPLETED:
        return None, pgettext("exams.final_center.entry", "Bu imtahanı artıq bitirmisiniz.")
    if ticket.status in (TICKET_STATUS_REMOVED, TICKET_STATUS_ABSENT):
        return None, pgettext(
            "exams.final_center.entry",
            "İmtahana girişiniz bağlanıb — imtahan mərkəzinə müraciət edin.",
        )
    ensure_open_room_sitting(room)
    sitting = attach_ticket_to_room_sitting(ticket, room, computer)
    if sitting is None:  # yarış halı — oturum elə indicə bağlandı
        return None, pgettext(
            "exams.final_center.entry",
            "Bu zalda hazırda açıq imtahan oturumu yoxdur — nəzarətçinin oturumu açmasını gözləyin.",
        )
    return ticket, None


def attach_ticket_to_room_sitting(ticket, room, computer=None):
    """
    Bileti otağın AÇIQ zal oturumuna qoşur (giriş anında — oturum sisteminin
    ləğvindən sonra).

    Tələbə qeydli kompüterdən (IP → zal) girəndə həmin otağın ``entry_open``/
    ``active`` oturumu tapılır, ``ticket.session`` set olunur və seat kompüterin
    ``seat_number``-indən götürülür (boşdursa). Nəzarətçi bu otağı başladanda
    tələbə öz təyin olunmuş imtahanına (``ticket.exam``) başlayır.

    * İdempotent: bilet artıq həmin otağın canlı oturumuna qoşulubsa onu qaytarır.
    * Otaqda açıq oturum yoxdursa ``None`` qaytarır (view "nəzarətçini gözləyin"
      xətası göstərir).
    """
    from apps.exams.models import ExamRoomSession
    from core.rls import bypass_rls

    live_states = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
    if (
        ticket.session_id
        and ticket.session
        and ticket.session.room_id == room.id
        and ticket.session.state in live_states
    ):
        return ticket.session

    # Public giriş axını — aktiv-org RLS konteksti yoxdur; oturum otağa görə
    # açıq filtrlənir (bax resolve_room_computer). Bypass ilə oxuyuruq.
    with bypass_rls():
        sitting = (
            ExamRoomSession.objects.filter(room=room, state__in=live_states).order_by("scheduled_start", "id").first()
        )
    if sitting is None:
        return None

    update_fields = ["session", "updated_at"]
    ticket.session = sitting
    seat = getattr(computer, "seat_number", None)
    if seat and not sitting.tickets.filter(seat_number=seat).exclude(pk=ticket.pk).exists():
        ticket.seat_number = seat
        update_fields.append("seat_number")
    ticket.save(update_fields=update_fields)
    return sitting


__all__ = [
    "ENTRY_SESSION_KEY",
    "ERROR_INVALID",
    "ERROR_LOCKED",
    "ERROR_NO_ACTIVE_SESSION",
    "ERROR_RATE_LIMITED",
    "attach_ticket_to_room_sitting",
    "clear_entry_session",
    "ensure_open_room_sitting",
    "ensure_pin_ticket",
    "entry_ticket_id",
    "store_entry_session",
    "validate_entry",
]
