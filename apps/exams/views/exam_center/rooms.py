"""exam_center paketi — zal idarəsi (siyahı / yaratma / redaktə)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.exams.forms import ExamRoomForm
from apps.exams.models import ExamRoom, ExamRoomSession
from apps.exams.services.final_center import can_manage_final_center, sessions_visible_to
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403, get_center_room_or_404, supervisor_org_or_403

_LIVE_STATES = ("entry_open", "active")


@login_required
def exam_center_room_list(request):
    """
    İmtahan Nəzarət Sisteminin GİRİŞ səhifəsi — nəzarətçi ilk olaraq ZALLARI
    görür. Hər zal kartı zaldakı canlı imtahanları (fənləri) çip kimi göstərir;
    "Zalı izlə" ilə həmin zalın aqreqasiya monitoruna keçilir (start/nəzarət
    orada). Yaratma/redaktə yalnız imtahan mərkəzi üçündür (``can_manage``).
    """
    organization = supervisor_org_or_403(request)
    can_manage = can_manage_final_center(request.user)

    # Kartda "bu zalda hansı imtahanlar canlıdır" çiplərini göstərmək üçün canlı
    # oturumları fənn adı ilə prefetch edirik (N+1 yox — tək əlavə sorğu).
    live_prefetch = Prefetch(
        "sessions",
        queryset=ExamRoomSession.objects.filter(state__in=_LIVE_STATES)
        .select_related("exam")
        .order_by("scheduled_start", "id"),
        to_attr="live_sessions",
    )
    rooms = (
        ExamRoom.objects.filter(organization=organization)
        .annotate(
            session_count=Count("sessions", distinct=True),
            live_session_count=Count(
                "sessions",
                filter=Q(sessions__state__in=_LIVE_STATES),
                distinct=True,
            ),
        )
        .prefetch_related(live_prefetch)
        .order_by("name", "id")
    )

    # Nəzarətçi (idarəçi deyil) yalnız təyin olunduğu oturumların zallarını görür.
    # Alt-sorğu ilə süzürük ki, annotasiya sayğacları JOIN-dən təsirlənməsin.
    if not can_manage:
        visible_room_ids = sessions_visible_to(
            request.user, ExamRoomSession.objects.filter(organization=organization)
        ).values_list("room_id", flat=True)
        rooms = rooms.filter(pk__in=visible_room_ids)

    query = (request.GET.get("q") or "").strip()
    if query:
        rooms = rooms.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(building__icontains=query))

    # Status filtri: canlı (giriş açıq/aktiv oturumu var) / boş / deaktiv.
    status = (request.GET.get("status") or "").strip()
    if status == "live":
        rooms = rooms.filter(live_session_count__gt=0)
    elif status == "idle":
        rooms = rooms.filter(live_session_count=0, is_active=True)
    elif status == "inactive":
        rooms = rooms.filter(is_active=False)

    page_obj = Paginator(rooms, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "exams/exam_center/room_list.html",
        {
            "page_obj": page_obj,
            "search_query": query,
            "active_status": status,
            "organization": organization,
            "can_manage": can_manage,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def exam_center_room_create(request):
    organization = center_org_or_403(request)
    form = ExamRoomForm(request.POST or None, organization=organization)
    if request.method == "POST" and form.is_valid():
        room = form.save(commit=False)
        room.organization = organization
        room.created_by = request.user
        room.save()
        log_action(
            AuditAction.CREATE,
            user=request.user,
            organization=organization,
            obj=room,
            reason="final_room_created",
            request=request,
            resource_type="exam_room",
            resource_id=str(room.pk),
        )
        messages.success(request, pgettext("exams.final_center.message", "Zal yaradıldı."))
        return redirect("exams:exam_center_room_list")
    return render(
        request,
        "exams/exam_center/room_form.html",
        {"form": form, "room": None, "organization": organization},
    )


@login_required
@require_http_methods(["GET", "POST"])
def exam_center_room_update(request, room_id):
    organization, room = get_center_room_or_404(request, room_id)
    form = ExamRoomForm(request.POST or None, instance=room, organization=organization)
    if request.method == "POST" and form.is_valid():
        changed = list(form.changed_data)
        form.save()
        log_action(
            AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=room,
            reason="final_room_updated",
            request=request,
            changes={"fields": changed},
            resource_type="exam_room",
            resource_id=str(room.pk),
        )
        messages.success(request, pgettext("exams.final_center.message", "Zal yeniləndi."))
        return redirect("exams:exam_center_room_list")
    return render(
        request,
        "exams/exam_center/room_form.html",
        {"form": form, "room": room, "organization": organization},
    )


__all__ = [
    "exam_center_room_create",
    "exam_center_room_list",
    "exam_center_room_update",
]
