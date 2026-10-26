"""exam_center paketi — zal monitoru modalında tələbənin PIN-i + «başqa kompüterdə davam et» (sahib 2026-10-26).

Sahibin tələbi (canlı imtahan zamanı): «yenidən üzərinə klik edib belə olarkən PIN vermək olsun
tələbəyə … ola bilər ki komp xarab oldu, nə isə bərpa etmək üçün». Kompüter xəritəsində tələbəyə
klik → canlı görüntü modalı (``snapshot_modal.js``). İmtahana hələ başlamamış tələbə üçün modalda
yalnız «Yenilə» / «Bağla» var idi. İndi imtahan mərkəzi (rəhbər + işçi, ``can_manage_final_center``)
üçün:

* ``exam_center_ticket_pin_reveal``   — tələbənin bu imtahan üzrə CARİ fərdi PIN-i (kabinet PIN-i,
  ``student_pins.student_visible_pin``; sətir yoxdursa yaradılır). Modalda maskalı, klikdə açılır.
* ``exam_center_ticket_pin_reissue``  — TƏZƏ fərdi PIN (``reissue_student_pin``) — yalnız imtahana
  hələ başlamamış tələbəyə (davam edən cəhd üçün mövcud «Yenidən giriş ver» axını var).
* ``exam_center_ticket_device_release`` — davam edən cəhd: kompüter xarab olub. Mövcud «cihaz
  dəyişikliyi» təsdiqi (``device_binding.approve_device_change``) yazılır — tələbə
  ``DEVICE_CHANGE_WINDOW`` ərzində başqa qeydli kompüterdən ÖZ PIN-i ilə girib EYNİ cəhdi davam
  etdirir (vaxt serverdə axır, cavablar yerində qalır; giriş cəhdi yeni kompüterə köçürür — bax
  ``reentry.cabinet_pin_resume_denial`` addım 3).

Qapılar: POST + CSRF, tenant + imtahan mərkəzi (``center_org_or_403``), bilet yalnız bu təşkilatın
CANLI zal oturumunda (monitor əhatəsi). Hər əməl audit-ə yazılır (kim, tələbə, imtahan); xam PIN
yalnız JSON cavabındadır — URL, log və audit-ə düşmür. Göstərmə istifadəçi başına rate-limit-lidir.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)
from apps.exams.services.final_center import can_manage_final_center
from apps.exams.services.final_center.device_binding import (
    SOURCE_PROCTOR,
    approve_device_change,
    device_window_minutes,
)
from apps.exams.services.student_pins import exam_requires_student_pins, reissue_student_pin, student_visible_pin
from core.audit import log_action
from core.constants import AuditAction
from core.rate_limit import record_rate_limit_hit

from ._shared import get_center_session_or_404, get_session_ticket_or_404

_CTX = "exams.final_center.monitor_pin"

#: Monitor əhatəsi — yalnız canlı (giriş açıq / aktiv) zal oturumunun bileti.
_LIVE_SESSION_STATES = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
#: İmtahana hələ başlamamış bilet statusları (PIN göstərmə + yeni PIN).
_PRE_START_STATUSES = (TICKET_STATUS_ASSIGNED, TICKET_STATUS_WAITING, TICKET_STATUS_READY)

#: PIN göstərmə / yeni PIN — istifadəçi başına (bir zalda onlarla tələbə; qaçaq dövrə serveri boğmasın).
_REVEAL_RATE = "30/1m"
_REISSUE_RATE = "10/1m"


def _has_open_attempt(ticket) -> bool:
    attempt = ticket.attempt if ticket.attempt_id else None
    return attempt is not None and not attempt.is_finished


def ticket_pin_actions(user, ticket, session) -> dict:
    """Modalın göstərəcəyi PIN / cihaz düymələri (snapshot JSON-una qoşulur) — yalnız imtahan mərkəzi.

    Sorğu yoxdur (bilet + cəhd artıq yüklənib); server hər əməldə şərtləri yenidən yoxlayır.
    """
    if not can_manage_final_center(user) or session.state not in _LIVE_SESSION_STATES:
        return {"reveal": False, "reissue": False, "device_release": False}
    pins = exam_requires_student_pins(ticket.exam)
    pre_start = ticket.status in _PRE_START_STATUSES and not ticket.attempt_id
    live = ticket.status == TICKET_STATUS_ACTIVE and _has_open_attempt(ticket)
    return {
        "reveal": pins and (pre_start or live),
        "reissue": pins and pre_start,
        "device_release": live,
    }


def _center_ticket(request, session_id, ticket_id):
    """Tenant + imtahan mərkəzi + canlı oturumun bileti; əks halda 403/404."""
    organization, session = get_center_session_or_404(request, session_id)
    ticket = get_session_ticket_or_404(session, ticket_id)
    return organization, session, ticket


def _refused(message, status=409):
    return JsonResponse({"success": False, "error": message}, status=status)


def _rate_limited(scope, rate, user):
    exceeded, retry_after = record_rate_limit_hit(scope, rate, user.id)
    if not exceeded:
        return None
    response = _refused(pgettext(_CTX, "Çox tez-tez sorğu — bir az sonra yenidən cəhd edin."), status=429)
    response["Retry-After"] = str(retry_after or 30)
    return response


def _assignment_warning(exam, student) -> str:
    """Tələbə imtahana artıq təyin olunmayıbsa (məs. bu gün başqa qrupa köçürülüb) xəbərdarlıq.

    PIN girişi ``can_user_start``-dan keçir: təyinatı itmiş tələbə PIN-lə girsə də «imtahana
    girişiniz yoxdur» alır — nəzarətçi bunu PIN verməzdən ƏVVƏL görsün.
    """
    from apps.exams.services.access_policy import can_user_access_exam

    if exam.author_id == student.pk or can_user_access_exam(exam, student):
        return ""
    return pgettext(
        _CTX,
        "Tələbə bu imtahana artıq təyin olunmayıb (qrupu dəyişdirilib və ya imtahandan çıxarılıb) — "
        "PIN ilə girsə də imtahana başlaya bilməyəcək. İmtahan mərkəzində təyinatı yoxlayın.",
    )


def _audit(request, organization, ticket, reason, action=AuditAction.VIEW):
    log_action(
        action,
        user=request.user,
        organization=organization,
        obj=ticket,
        reason=reason,
        request=request,
        resource_type="final_exam_ticket",
        resource_id=str(ticket.pk),
        # Xam PIN YAZILMIR — yalnız kim / kimə / hansı imtahan.
        changes={"student_id": ticket.student_id, "exam_id": ticket.exam_id, "session_id": ticket.session_id},
    )


def _student_payload(ticket):
    return {"student_name": ticket.student.get_full_name() or ticket.student.username}


@login_required
@require_POST
@never_cache
def exam_center_ticket_pin_reveal(request, session_id, ticket_id):
    """Tələbənin bu imtahan üzrə cari fərdi PIN-i (maskalı göstərmə üçün) — hər açılış audit-ə yazılır."""
    organization, session, ticket = _center_ticket(request, session_id, ticket_id)
    limited = _rate_limited("fxc_monitor_pin_reveal", _REVEAL_RATE, request.user)
    if limited is not None:
        return limited
    if not ticket_pin_actions(request.user, ticket, session)["reveal"]:
        return _refused(pgettext(_CTX, "Bu tələbə üçün PIN göstərilə bilməz (imtahan bitib və ya oturum bağlıdır)."))
    pin = student_visible_pin(ticket.exam, ticket.student, provision_missing=True)
    if not pin:
        return _refused(pgettext(_CTX, "PIN tapılmadı — «Yeni PIN ver» ilə tələbəyə təzə PIN verin."))
    _audit(request, organization, ticket, "final_center_monitor_pin_revealed")
    return JsonResponse(
        {"success": True, "pin": pin, "warning": _assignment_warning(ticket.exam, ticket.student)}
        | _student_payload(ticket)
    )


@login_required
@require_POST
@never_cache
def exam_center_ticket_pin_reissue(request, session_id, ticket_id):
    """İmtahana hələ başlamamış tələbəyə TƏZƏ fərdi PIN — köhnəsi dərhal etibarsızdır."""
    organization, session, ticket = _center_ticket(request, session_id, ticket_id)
    limited = _rate_limited("fxc_monitor_pin_reissue", _REISSUE_RATE, request.user)
    if limited is not None:
        return limited
    if not ticket_pin_actions(request.user, ticket, session)["reissue"]:
        return _refused(
            pgettext(
                _CTX,
                "Yeni PIN yalnız imtahana hələ başlamamış tələbəyə verilir. İmtahanda olan tələbə üçün "
                "«Yenidən giriş ver» və ya «Başqa kompüterdə davam et» düyməsindən istifadə edin.",
            )
        )
    reissue_student_pin(ticket.exam, ticket.student)
    pin = student_visible_pin(ticket.exam, ticket.student)
    _audit(request, organization, ticket, "final_center_monitor_pin_reissued", action=AuditAction.UPDATE)
    return JsonResponse(
        {"success": True, "pin": pin or "", "warning": _assignment_warning(ticket.exam, ticket.student)}
        | _student_payload(ticket)
    )


@login_required
@require_POST
def exam_center_ticket_device_release(request, session_id, ticket_id):
    """Davam edən cəhd: kompüter xarab olub — tələbə başqa kompüterdən EYNİ cəhdi davam etdirsin."""
    organization, session, ticket = _center_ticket(request, session_id, ticket_id)
    if not ticket_pin_actions(request.user, ticket, session)["device_release"]:
        return _refused(pgettext(_CTX, "Tələbənin davam edən imtahan cəhdi yoxdur."))
    minutes = device_window_minutes()
    if approve_device_change(ticket.attempt, by=request.user, request=request, source=SOURCE_PROCTOR):
        message = pgettext(
            _CTX,
            "Hazırdır — tələbə %(minutes)d dəqiqə ərzində başqa qeydli kompüterdən öz PIN-i ilə daxil olub "
            "imtahanı qaldığı yerdən davam etdirə bilər (vaxt dayanmır, cavablar qorunur).",
        ) % {"minutes": minutes}
    else:
        message = pgettext(
            _CTX,
            "Cəhd hələ heç bir kompüterə bağlanmayıb — tələbə öz PIN-i ilə istənilən qeydli kompüterdən davam "
            "edə bilər.",
        )
    _audit(request, organization, ticket, "final_center_monitor_device_released", action=AuditAction.UPDATE)
    return JsonResponse({"success": True, "message": message, "window_minutes": minutes} | _student_payload(ticket))


__all__ = [
    "exam_center_ticket_device_release",
    "exam_center_ticket_pin_reissue",
    "exam_center_ticket_pin_reveal",
    "ticket_pin_actions",
]
