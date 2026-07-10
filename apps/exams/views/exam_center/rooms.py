"""exam_center paketi — zal siyahısı (GİRİŞ səhifəsi).

Zal YARATMA/REDAKTƏ artıq imtahan mərkəzində DEYİL — o, superadmin (yaxud
``can_manage_exam_rooms`` bayraqlı idarəçi) tərəfindən profil «İmtahan zalları»
bölməsində idarə olunur. Burada nəzarətçi/mərkəz yalnız zalları görür və birbaşa
zal monitoruna («Zala daxil ol») keçir.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import render

from apps.exams.models import ExamRoom, ExamRoomSession
from apps.exams.services.access_policy import can_manage_exam_rooms
from apps.exams.services.final_center import can_manage_final_center, sessions_visible_to

from ._shared import supervisor_org_or_403

_LIVE_STATES = ("entry_open", "active")


@login_required
def exam_center_room_list(request):
    """
    İmtahan Nəzarət Sisteminin GİRİŞ səhifəsi — nəzarətçi ilk olaraq ZALLARI
    görür. Hər zal kartı zaldakı canlı imtahanları (fənləri) çip kimi göstərir;
    "Zala daxil ol" ilə həmin zalın aqreqasiya monitoruna keçilir (start/nəzarət
    orada). Zal yaratma/redaktə burada YOXDUR — superadmin idarə edir.
    """
    organization = supervisor_org_or_403(request)
    can_manage = can_manage_final_center(request.user)
    can_manage_rooms = can_manage_exam_rooms(request.user)

    # Kartda "bu zalda canlı oturum" çiplərini göstərmək üçün canlı oturumları
    # prefetch edirik (N+1 yox). Oturum imtahandan asılı deyil (zal oturumu).
    live_prefetch = Prefetch(
        "sessions",
        queryset=ExamRoomSession.objects.filter(state__in=_LIVE_STATES).order_by("scheduled_start", "id"),
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
            computer_count_real=Count("computers", distinct=True),
        )
        .prefetch_related(live_prefetch)
        .order_by("name", "id")
    )

    # Nəzarətçi (idarəçi deyil) YALNIZ özünə aid zalları görür: zala təyin
    # olunduğu (ExamRoom.invigilators — oturum olmasa belə) və ya təyinatlı
    # oturumu olan zallar. Təyinatsız istifadəçi heç bir zal görmür.
    # Alt-sorğu ilə süzürük ki, annotasiya sayğacları JOIN-dən təsirlənməsin.
    if not can_manage:
        visible_room_ids = set(
            sessions_visible_to(request.user, ExamRoomSession.objects.filter(organization=organization)).values_list(
                "room_id", flat=True
            )
        ) | set(request.user.invigilated_rooms.filter(organization=organization).values_list("pk", flat=True))
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
            "can_manage_rooms": can_manage_rooms,
        },
    )


__all__ = [
    "exam_center_room_list",
]
