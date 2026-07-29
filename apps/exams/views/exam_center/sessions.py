"""exam_center paketi — oturum idarəsi (siyahı / yaratma / detal / təyinat)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from apps.exams.forms import ExamRoomSessionForm
from apps.exams.models import ExamRoomSession
from apps.exams.services.final_center import (
    RoomSessionStateError,
    can_view_final_history,
    ensure_can_view_final_history,
    readmit_student,
    session_history,
    session_list_annotations,
    set_seat,
    validate_session_plan,
)
from core.audit import log_action
from core.constants import AuditAction

from ._shared import (
    center_org_or_403,
    get_center_session_or_404,
    get_session_ticket_or_404,
    supervisor_org_or_403,
    visible_sessions_qs,
)

User = get_user_model()


@login_required
def exam_center_session_list(request):
    organization = supervisor_org_or_403(request)
    sessions = session_list_annotations(visible_sessions_qs(request, organization)).order_by("-scheduled_start", "-id")

    # Filtr çipləri üçün vəziyyət sayğacları — status filtri TƏTBİQ OLUNMAMIŞ
    # queryset üzərindən hesablanır ki, hər çip öz faktiki sayını göstərsin
    # (istifadəçi hansı vəziyyətdə oturum olduğunu klikləmədən görsün).
    state_counts = dict(
        visible_sessions_qs(request, organization).values_list("state").annotate(total=Count("id")).order_by()
    )
    # Açar adı şablon üçün "total"-dır: Django alt-xətlə başlayan
    # dəyişən adını oxumur (__all__ TemplateSyntaxError verir).
    state_counts["total"] = sum(state_counts.values())

    state = (request.GET.get("state") or "").strip()
    if state:
        sessions = sessions.filter(state=state)

    from apps.exams.services.final_center import can_manage_final_center

    page_obj = Paginator(sessions, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "exams/exam_center/session_list.html",
        {
            "page_obj": page_obj,
            "active_state": state,
            "state_counts": state_counts,
            "organization": organization,
            # İmtahan mərkəzi zal/oturum/hesabatı idarə edir; nəzarətçi yalnız
            # monitor edir — idarə düymələri gizlədilir ki, 403 alınmasın.
            "can_manage": can_manage_final_center(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def exam_center_session_create(request):
    organization = center_org_or_403(request)
    form = ExamRoomSessionForm(
        request.POST or None,
        organization=organization,
    )
    if request.method == "POST" and form.is_valid():
        session = form.save(commit=False)
        try:
            validate_session_plan(
                room=session.room,
                scheduled_start=session.scheduled_start,
                scheduled_end=session.scheduled_end,
            )
        except RoomSessionStateError as exc:
            form.add_error(None, str(exc))
        else:
            session.organization = organization
            session.created_by = request.user
            session.save()
            form.save_m2m()
            log_action(
                AuditAction.CREATE,
                user=request.user,
                organization=organization,
                obj=session,
                reason="final_session_created",
                request=request,
                resource_type="exam_room_session",
                resource_id=str(session.pk),
            )
            messages.success(request, pgettext("exams.final_center.message", "Zal oturumu yaradıldı."))
            return redirect("exams:exam_center_session_detail", session_id=session.pk)
    return render(
        request,
        "exams/exam_center/session_form.html",
        {"form": form, "organization": organization},
    )


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
    "exam_center_session_create",
    "exam_center_session_detail",
    "exam_center_session_history",
    "exam_center_session_list",
    "exam_center_ticket_readmit",
    "exam_center_ticket_seat",
]
