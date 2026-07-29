"""exam_center paketi — oturum detalı, tarixçəsi və bilet əməliyyatları.

Oturum SİYAHISI və ƏLLƏ YARATMA səhifələri 2026-07-30-da silindi: oturum artıq
istifadəçinin idarə etdiyi obyekt deyil — zal yaradılır, kompüterlər əlavə olunur,
oturum isə ilk giriş anında avtomatik açılır. Canlı mənzərə zal monitorunda,
tarixi kəsim isə hesabatlardadır.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamRoomSession
from apps.exams.services.final_center import (
    can_view_final_history,
    ensure_can_view_final_history,
    readmit_student,
    session_history,
    set_seat,
)

from ._shared import (
    get_center_session_or_404,
    get_session_ticket_or_404,
    supervisor_org_or_403,
)

User = get_user_model()


@login_required
def exam_center_session_detail(request, session_id):
    """
    Zal oturumu detalı: oturuma QOŞULMUŞ (giriş anında) tələbələr, hərəsi öz
    imtahanı ilə. Oturum imtahandan asılı deyil — təyinat "Final təyinatları"
    bölməsindədir. Nəzarətçi/heyət də görə bilir; idarə düymələri icazəyə görə.
    """
    organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    tickets = session.tickets.select_related("student", "attempt", "exam").order_by("seat_number", "id")

    from apps.exams.services.final_center import can_manage_final_center

    return render(
        request,
        "exams/exam_center/session_detail.html",
        {
            "session": session,
            "tickets": tickets,
            "organization": organization,
            "can_manage": can_manage_final_center(request.user),
            "can_view_history": can_view_final_history(request.user, organization),
        },
    )


@login_required
def exam_center_session_history(request, session_id):
    """
    Oturumun tam ƏMƏLİYYAT TARİXÇƏSİ — PIN yaradılması/verilməsi, giriş, kompüter
    dəyişmələri, yenidən giriş, zal/oturum həyat dövrü, nəzarət hadisələri. Yalnız
    YUXARI səviyyələr (imtahan mərkəzi rəhbəri / rektor / prorektor / superadmin).
    """
    organization = supervisor_org_or_403(request)
    ensure_can_view_final_history(request.user, organization)
    session = get_object_or_404(
        ExamRoomSession.objects.select_related("room", "invigilator"),
        pk=session_id,
        organization=organization,
    )
    events = session_history(session)
    summary = {
        "total": len(events),
        "pins": sum(
            1
            for e in events
            if e["code"] in ("final_tickets_assigned", "final_pin_regenerated", "final_reentry_pin_issued")
        ),
        "reentries": sum(1 for e in events if e["code"] == "final_reentry_pin_issued"),
        "seat_moves": sum(1 for e in events if e["code"] == "final_seat_changed"),
        "entries": sum(1 for e in events if e["code"] == "final_entry_validated"),
        "incidents": sum(1 for e in events if e["code"] == "supervision_incident"),
    }
    return render(
        request,
        "exams/exam_center/session_history.html",
        {"session": session, "events": events, "summary": summary},
    )


@login_required
@require_POST
def exam_center_ticket_seat(request, session_id, ticket_id):
    _organization, session = get_center_session_or_404(request, session_id)
    ticket = get_session_ticket_or_404(session, ticket_id)
    raw_seat = (request.POST.get("seat_number") or "").strip()
    seat = int(raw_seat) if raw_seat.isdigit() else None
    from django.db import IntegrityError

    try:
        set_seat(ticket, seat, request.user, request=request)
    except IntegrityError:
        messages.error(request, pgettext("exams.final_center.message", "Bu yer nömrəsi artıq başqa tələbəyə verilib."))
    return redirect("exams:exam_center_session_detail", session_id=session.pk)


@login_required
@require_POST
def exam_center_ticket_readmit(request, session_id, ticket_id):
    _organization, session = get_center_session_or_404(request, session_id)
    ticket = get_session_ticket_or_404(session, ticket_id)
    if readmit_student(ticket, request.user, request=request):
        messages.success(
            request, pgettext("exams.final_center.message", "Tələbə yenidən buraxıldı və yeni PIN yaradıldı.")
        )
    else:
        messages.error(
            request,
            pgettext("exams.final_center.message", "Yenidən buraxma mümkün olmadı (bilet çıxarılmış statusda deyil)."),
        )
    return redirect("exams:exam_center_session_detail", session_id=session.pk)


__all__ = [
    "exam_center_session_detail",
    "exam_center_session_history",
    "exam_center_ticket_readmit",
    "exam_center_ticket_seat",
]
