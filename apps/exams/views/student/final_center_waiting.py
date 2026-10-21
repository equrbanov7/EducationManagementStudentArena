"""İmtahan mərkəzi — gözləmə otağı (final + midterm; bilet-id əsaslı URL-lər hər iki növ üçün ortaqdır).

``final_center.py``-dan bölünüb (2026-10-20, modul-ölçü qapısı). Axın: giriş səhifəsi (``/exams/final/`` və ya
``/exams/midterm/``) → qaydalar modalı → **gözləmə otağı** → nəzarətçi zalı başladır → ``begin`` → attempt.
Hər addımda bilet sahibliyi + giriş sessiyası + zal kompüteri backend-də yoxlanır; rədd/çıxış halında tələbə
öz imtahan növünün giriş səhifəsinə qaytarılır (``center_exams.entry_url_for_exam``).
"""

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import FinalExamTicket
from apps.exams.services.center_exams import entry_url_for_exam, exam_kind
from apps.exams.services.exam_center_gate import ensure_hall_computer
from apps.exams.services.exam_network import ExamNetworkDenied, final_entry_network_allowed
from apps.exams.services.final_center import (
    HEARTBEAT_INTERVAL_SECONDS,
    TicketStateError,
    begin_attempt_for_ticket,
    clear_entry_session,
    entry_session_matches,
    student_cancel_waiting,
    sync_ticket_completion,
)
from apps.exams.views.student._final_device import final_entry_network_guarded

from ._center_common import TICKET_SELECT_RELATED, ensure_hall_access, room_access_error, room_access_ok


def _resolve_own_ticket(request, ticket_id):
    """
    Bilet sahibliyi + PIN girişindən keçmə yoxlaması. Girişsiz birbaşa URL
    yığan istifadəçi login səhifəsinə qaytarılır.
    """
    ticket = get_object_or_404(
        FinalExamTicket.objects.select_related(*TICKET_SELECT_RELATED),
        pk=ticket_id,
        student=request.user,
    )
    if not entry_session_matches(request, ticket):
        return ticket, redirect(entry_url_for_exam(ticket.exam))
    return ticket, None


@login_required
@final_entry_network_guarded
def final_exam_waiting(request, ticket_id):
    """
    Gözləmə otağı. Real vaxt WS ilə işləyir (yüksək tezlikli polling YOX);
    WS mümkün olmayanda aşağı tezlikli fallback poll (state endpoint) var.
    """
    ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return deny
    ensure_hall_computer(request, ticket.organization)
    entry_url = entry_url_for_exam(ticket.exam)
    session = ticket.session
    if session is None:
        return redirect(entry_url)
    if not room_access_ok(request, session.room):
        raise PermissionDenied(pgettext("exams.view.final_center.permission", "final_center_ip_not_allowed"))

    if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
        return redirect("exams:take_exam", slug=ticket.exam.slug, attempt_id=ticket.attempt_id)
    if ticket.status not in (TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        # Hələ təsdiqlənməyib — login/modal səhifəsinə qaytar.
        return redirect(entry_url)

    return render(
        request,
        "exams/student/final_waiting.html",
        {
            "ticket": ticket,
            "session": session,
            "exam": ticket.exam,
            "room": session.room,
            "entry_kind": exam_kind(ticket.exam),
            "entry_url": entry_url,
            "ws_path": f"/ws/exams/final/wait/{ticket.pk}/",
            "heartbeat_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "state_url": reverse("exams:final_ticket_state", kwargs={"ticket_id": ticket.pk}),
            "begin_url": reverse("exams:final_exam_begin", kwargs={"ticket_id": ticket.pk}),
            "cancel_url": reverse("exams:final_exam_cancel", kwargs={"ticket_id": ticket.pk}),
            "session_already_active": session.state == ROOM_SESSION_STATE_ACTIVE,
        },
    )


@login_required
@require_POST
@final_entry_network_guarded
def final_exam_cancel(request, ticket_id):
    """Start-dan əvvəl gözləmə otağından imtina — cəhd haqqı yanmır."""
    ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return deny
    ensure_hall_computer(request, ticket.organization)
    entry_url = entry_url_for_exam(ticket.exam)
    student_cancel_waiting(ticket, request=request)
    clear_entry_session(request)
    logout(request)
    return redirect(entry_url)


@login_required
@require_POST
@final_entry_network_guarded
def final_exam_begin(request, ticket_id):
    """
    Oturum AKTİV olduqdan sonra attempt-in yaradılması. Sinxron startda hər
    müştəri kiçik təsadüfi gecikmə ilə bu endpoint-i çağırır — sual seti
    WS broadcast-ı ilə YOX, autentifikasiyalı HTTP ilə yüklənir.
    """
    ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return JsonResponse({"success": False, "redirect_url": entry_url_for_exam(ticket.exam)}, status=403)
    ensure_hall_computer(request, ticket.organization)
    if ticket.session is None or not room_access_ok(request, ticket.session.room):
        return JsonResponse(
            {"success": False, "error": str(room_access_error()), "redirect_url": entry_url_for_exam(ticket.exam)},
            status=403,
        )

    try:
        attempt = begin_attempt_for_ticket(ticket)
    except TicketStateError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=409)

    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("exams:take_exam", kwargs={"slug": ticket.exam.slug, "attempt_id": attempt.pk}),
        }
    )


@login_required
@never_cache
@final_entry_network_guarded
def final_ticket_state(request, ticket_id):
    """
    Aşağı tezlikli fallback poll (WS kəsiləndə). Kompakt payload — sual/cavab
    məlumatı YOXDUR.
    """
    if not final_entry_network_allowed(request):
        raise ExamNetworkDenied()
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return JsonResponse({"error": "entry_required"}, status=403)
    ensure_hall_computer(request, ticket.organization)

    session = ticket.session
    if session is None:
        return JsonResponse({"error": "entry_required", "ticket_status": ticket.status}, status=409)
    session.refresh_from_db(fields=["state", "started_at", "ended_at"])
    if ticket.status == TICKET_STATUS_ACTIVE:
        sync_ticket_completion(ticket)

    return JsonResponse(
        {
            "session_state": session.state,
            "ticket_status": ticket.status,
            "removal_action": ticket.removal_action,
            "removal_reason": ticket.removal_reason,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "server_now": timezone.now().isoformat(),
        }
    )


__all__ = [
    "final_exam_begin",
    "final_exam_cancel",
    "final_exam_waiting",
    "final_ticket_state",
]
