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

from apps.exams.domain.final_center import TICKET_STATUS_COMPLETED
from apps.exams.models import ExamRoomSession
from apps.exams.services.final_center import (
    ANNUL_REASONS,
    TicketStateError,
    annul_attempt_result,
    can_view_final_history,
    ensure_can_view_final_history,
    readmit_student,
    reopen_completed_ticket,
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
    from django.db.models import Exists, OuterRef

    from apps.exams.models import SupervisionIncident
    from apps.exams.services.final_center import can_manage_final_center
    from apps.exams.services.final_center.result_annul import ANNUL_ACTION

    # Ləğv işarəsi bilet sorğusunun İÇİNDƏ (Exists) — oturum səhifəsinin sorğu büdcəsi dəyişmir.
    annulled = SupervisionIncident.objects.filter(attempt_id=OuterRef("attempt_id"), teacher_action=ANNUL_ACTION)
    tickets = list(
        session.tickets.select_related("student", "attempt", "exam")
        .annotate(result_annulled=Exists(annulled))
        .order_by("seat_number", "id")
    )
    for t in tickets:
        t.can_annul = bool(t.attempt_id) and not t.result_annulled and t.status in ("completed", "removed")

    return render(
        request,
        "exams/exam_center/session_detail.html",
        {
            "session": session,
            "tickets": tickets,
            "organization": organization,
            "can_manage": can_manage_final_center(request.user),
            "can_view_history": can_view_final_history(request.user, organization),
            "annul_reasons": ANNUL_REASONS,
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
    try:
        # Bitmiş bilet: cəhd haqqı qalıbsa yenidən cəhd (sahib 2026-11-04); çıxarılmış: adi yenidən buraxma.
        done = (
            reopen_completed_ticket(ticket, request.user, request=request)
            if ticket.status == TICKET_STATUS_COMPLETED
            else readmit_student(ticket, request.user, request=request)
        )
    except TicketStateError as exc:
        messages.error(request, str(exc))
        return redirect("exams:exam_center_session_detail", session_id=session.pk)
    if done:
        messages.success(
            request, pgettext("exams.final_center.message", "Tələbə yenidən buraxıldı və yeni PIN yaradıldı.")
        )
    else:
        messages.error(
            request,
            pgettext("exams.final_center.message", "Yenidən buraxma mümkün olmadı (bilet çıxarılmış statusda deyil)."),
        )
    return redirect("exams:exam_center_session_detail", session_id=session.pk)


@login_required
@require_POST
def exam_center_ticket_annul(request, session_id, ticket_id):
    """Sahib 2026-11-16: bitmiş / çıxarılmış biletin nəticəsini izahatla ləğv et (jurnalda 0, tələbəyə qeyd).

    Yalnız imtahan mərkəzi (nəzarətçi yox) — ``get_center_session_or_404`` defolt yoxlaması."""
    _organization, session = get_center_session_or_404(request, session_id)
    ticket = get_session_ticket_or_404(session, ticket_id)
    try:
        done = annul_attempt_result(
            ticket.attempt if ticket.attempt_id else None,
            request.user,
            reason_key=(request.POST.get("reason") or "").strip(),
            note=request.POST.get("note") or "",
            request=request,
        )
    except TicketStateError as exc:
        messages.error(request, str(exc))
        return redirect("exams:exam_center_session_detail", session_id=session.pk)
    if done:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Nəticə ləğv edildi: jurnalda 0 bal, tələbəyə qeyd göstərilir."),
        )
    else:
        messages.info(request, pgettext("exams.final_center.message", "Bu nəticə artıq ləğv olunub."))
    return redirect("exams:exam_center_session_detail", session_id=session.pk)


__all__ = [
    "exam_center_session_detail",
    "exam_center_ticket_annul",
    "exam_center_session_history",
    "exam_center_ticket_readmit",
    "exam_center_ticket_seat",
]
