"""exam_center paketi — zal monitorunda BİR tələbəyə əlavə vaxt (sahib 2026-11-17).

Kompüter xəritəsində / siyahıda tələbəyə klik → canlı görüntü modalı (``snapshot_modal.js``) → «Əlavə vaxt»
bloku (``snapshot_time_actions.js``): dəqiqə + səbəb → təsdiq pəncərəsi → bu endpoint. Məntiq
``services/attempt_time_extension.py``-dadır (deadline-ın tək mənbəyi, sətir kilidi, hədlər, audit, WS).

Qapılar: POST + CSRF; tenant + oturuma nəzarət icazəsi (imtahan mərkəzi VƏ YA həmin zala təyin olunmuş nəzarətçi —
«Bərpa et» ilə eyni səviyyə, çünki texniki problemi zalda olan görür); bilet yalnız bu oturumun CANLI
(giriş açıq / aktiv) vəziyyətində; cəhd davam etməlidir. İstifadəçi başına rate-limit.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_ENTRY_OPEN
from apps.exams.services.attempt_time_extension import (
    MAX_STEP_MINUTES,
    MIN_STEP_MINUTES,
    TimeExtensionError,
    can_extend,
    extend_attempt_time,
    extra_minutes,
    remaining_extension_minutes,
)
from apps.exams.services.final_center.events import broadcast_to_staff
from core.rate_limit import record_rate_limit_hit

from ._shared import get_center_session_or_404, get_session_ticket_or_404

_CTX = "exams.time_extension"
_LIVE_SESSION_STATES = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
_RATE = "30/1m"


def ticket_time_actions(ticket, session) -> dict:
    """Modalın «Əlavə vaxt» bloku üçün vəziyyət (snapshot JSON-una qoşulur). Server əməldə yenidən yoxlayır."""
    attempt = ticket.attempt if ticket.attempt_id else None
    live = session.state in _LIVE_SESSION_STATES and attempt is not None
    allowed = bool(live and can_extend(attempt))
    return {
        "extend": allowed,
        "extra_minutes": extra_minutes(attempt) if attempt is not None else 0,
        "max_minutes": min(MAX_STEP_MINUTES, remaining_extension_minutes(attempt)) if allowed else 0,
        "min_minutes": MIN_STEP_MINUTES,
    }


def _refused(message, status=409):
    return JsonResponse({"success": False, "error": message}, status=status)


@login_required
@require_POST
def exam_center_ticket_extra_time(request, session_id, ticket_id):
    """Davam edən cəhdə N dəqiqə əlavə et — yalnız bu tələbənin vaxtı uzanır."""
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ticket = get_session_ticket_or_404(session, ticket_id)
    exceeded, retry_after = record_rate_limit_hit("fxc_monitor_extra_time", _RATE, request.user.id)
    if exceeded:
        response = _refused(pgettext(_CTX, "Çox tez-tez sorğu — bir az sonra yenidən cəhd edin."), status=429)
        response["Retry-After"] = str(retry_after or 30)
        return response
    if session.state not in _LIVE_SESSION_STATES or not ticket.attempt_id:
        return _refused(pgettext(_CTX, "Tələbənin davam edən imtahanı yoxdur."))
    try:
        state = extend_attempt_time(
            ticket.attempt,
            request.user,
            minutes=request.POST.get("minutes"),
            reason=request.POST.get("reason") or "",
            request=request,
        )
    except TimeExtensionError as exc:
        return _refused(str(exc), status=400)
    broadcast_to_staff(
        session.pk,
        {"event": "time_extended", "ticket_id": ticket.pk, "extra_minutes": state["extra_minutes"]},
    )
    message = pgettext(
        _CTX, "Tələbəyə %(added)d dəqiqə əlavə olundu (cəmi əlavə: %(total)d dəq). Yeni bitmə vaxtı: %(time)s."
    ) % {
        "added": state["added_minutes"],
        "total": state["extra_minutes"],
        "time": _local_time(state["deadline_at"]),
    }
    return JsonResponse({"success": True, "message": message, **state})


def _local_time(iso_value: str) -> str:
    from datetime import datetime

    from django.utils import timezone

    try:
        return timezone.localtime(datetime.fromisoformat(iso_value)).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


__all__ = ["exam_center_ticket_extra_time", "ticket_time_actions"]
