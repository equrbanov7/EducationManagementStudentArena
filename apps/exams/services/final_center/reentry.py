"""final_center paketi — kabinet (fərdi) PIN-i ilə DAVAM EDƏN final cəhdinə yenidən giriş (2026-10-13, gecə).

Sahibin tələbi: «tələbəyə yeni pin verilməsi, bir kompdan qalxıb digər kompa keçərkən yeni pin
veriləndə olduğu yerdən davam etməsi, köhnə pin etibarsızlığı».

Problem: 2026-07 qaydası ilə fərdi ``ExamStudentPin`` imtahan başlayanda ləğv EDİLMİR — tələbə
istənilən qeydli zal kompüterindən yenidən girə bilirdi. Giriş isə ``attach_ticket_to_room_sitting``
ilə cəhdin ``room_computer``-ini YENİ kompüterə köçürürdü və take səhifəsindəki cihaz qapısı
(``device_binding``: «eyni qeydli zal kompüteri») bunu «eyni kompüter» sayıb keçirirdi — yəni
nəzarətçinin «yenidən giriş» PIN-i olmadan kompüter dəyişmək mümkün idi, köhnə PIN isə yeni PIN
verildikdən sonra da işləyirdi.

Qayda (kabinet PIN-i ilə, cəhd DAVAM EDİRSƏ):

1. Nəzarətçi cəhd başlayandan sonra YENİ PIN verib (``regenerate_pin`` / «yenidən giriş») →
   köhnə kabinet PIN-i bu cəhd üçün ETİBARSIZDIR (rədd + audit). Tələbə yeni PIN-lə girir.
2. Eyni qeydli kompüter (cəhdin ``room_computer``-i) və ya eyni brauzer (cihaz cookie-si) →
   davam (brauzer çöküşü). Cəhd yerindən tərpənmir.
3. Nəzarətçi/imtahan mərkəzinin «cihaz dəyişikliyi» təsdiqi açıqdır → davam, cəhd yeni
   kompüterə köçür (təsdiq take səhifəsində sərf olunur).
4. Qalan hər hal (başqa kompüter) → rədd: «nəzarətçidən yeni PIN istəyin». Köhnə kompüterin
   sessiyası TOXUNULMAZ qalır (giriş nəsli dəyişmir).

Cəhd hələ başlamayıbsa (bilet yoxdur / aktiv deyil) heç nə dəyişmir.
"""

from __future__ import annotations

import logging

from django.utils.translation import pgettext

from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE
from apps.exams.models import FinalExamTicket
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls

from .device_binding import device_change_approval_open, request_matches_bound_device

logger = logging.getLogger("exams.final_center.reentry")

REASON_STALE_PIN = "final_entry_stale_pin_refused"
REASON_OTHER_COMPUTER = "final_entry_other_computer_refused"

_CTX = "exams.final_center.entry"


def stale_pin_message() -> str:
    return pgettext(
        _CTX,
        "Sizə nəzarətçi tərəfindən yeni PIN verilib — köhnə PIN artıq etibarsızdır. Yeni PIN ilə daxil olun.",
    )


def other_computer_message() -> str:
    return pgettext(
        _CTX,
        "İmtahanınız başqa kompüterdə davam edir. Kompüteri dəyişmək üçün nəzarətçidən yeni PIN istəyin — "
        "imtahan qaldığı yerdən davam edəcək.",
    )


def _reentry_pin_issued_since_start(ticket) -> bool:
    issued = ticket.pin_issued_at
    if not issued or not ticket.pin_hash:
        return False
    started = ticket.started_at or getattr(ticket.attempt, "started_at", None)
    return started is None or issued > started


def _audit_refusal(ticket, request, reason, computer):
    try:
        with bypass_rls():
            log_action(
                AuditAction.DENY,
                user=ticket.student,
                organization=ticket.organization,
                obj=ticket,
                reason=reason,
                request=request,
                resource_type="final_exam_ticket",
                resource_id=str(ticket.pk),
                changes={
                    "attempt_id": ticket.attempt_id,
                    "computer_id": getattr(computer, "pk", None),
                    "attempt_computer_id": getattr(ticket.attempt, "room_computer_id", None),
                },
            )
    except Exception:  # noqa: BLE001 — audit xətası girişi sındırmasın (rədd onsuz da qüvvədədir)
        logger.exception("reentry audit yazılmadı: ticket=%s reason=%s", ticket.pk, reason)


def cabinet_pin_resume_denial(request, exam, student, computer):
    """Kabinet PIN-i ilə davam edən final cəhdinə giriş qərarı.

    Qaytarır: ``(rədd_mesajı | None, move_attempt)`` — ``move_attempt`` girişin cəhdi yeni
    kompüterə köçürüb-köçürməməsidir (``ensure_pin_ticket``-ə ötürülür).
    """
    with bypass_rls():
        ticket = (
            FinalExamTicket.objects.select_related("attempt", "organization", "student")
            .filter(exam=exam, student=student)
            .first()
        )
    if ticket is None or ticket.status != TICKET_STATUS_ACTIVE or not ticket.attempt_id:
        return None, True
    attempt = ticket.attempt
    if attempt is None or attempt.is_finished:
        return None, True

    if _reentry_pin_issued_since_start(ticket):
        _audit_refusal(ticket, request, REASON_STALE_PIN, computer)
        return stale_pin_message(), False

    if computer is not None and attempt.room_computer_id == computer.pk:
        return None, False
    device_match = request_matches_bound_device(request, attempt)
    if device_match is None:
        # Cəhd hələ heç bir cihazda açılmayıb — köçürmək təhlükəsizdir (bağlanacaq ilk cihaz budur).
        return None, True
    if device_match:
        return None, False
    if device_change_approval_open(attempt):
        return None, True
    _audit_refusal(ticket, request, REASON_OTHER_COMPUTER, computer)
    return other_computer_message(), False


__all__ = [
    "REASON_OTHER_COMPUTER",
    "REASON_STALE_PIN",
    "cabinet_pin_resume_denial",
    "other_computer_message",
    "stale_pin_message",
]
