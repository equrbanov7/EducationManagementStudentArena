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

from apps.exams.models import ExamAttempt, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.access_policy import can_manage_exam_rooms
from apps.exams.services.final_center import can_manage_final_center, sessions_visible_to

from ._shared import supervisor_org_or_403

_LIVE_STATES = ("entry_open", "active")


def _live_exam_rows(room_scope):
    """Hazırda GEDƏN imtahanlar: (imtahan, zal) üzrə aktiv tələbə sayı.

    İki mənbə (zal monitoru snapshot-u ilə eyni bölgü, ikiqat sayma yoxdur):
    * bilet axını — ``FinalExamTicket`` aktiv statusda;
    * biletsiz PIN axını — ``final_tickets``-i olmayan in_progress cəhdlər.
    """
    from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE

    merged = {}

    ticket_rows = (
        FinalExamTicket.objects.filter(session__room__in=room_scope, status=TICKET_STATUS_ACTIVE)
        .values("exam_id", "exam__title", "session__room_id", "session__room__name", "session__room__code")
        .annotate(students=Count("id"))
    )
    for row in ticket_rows:
        key = (row["exam_id"], row["session__room_id"])
        merged[key] = {
            "exam_title": row["exam__title"],
            "room_id": row["session__room_id"],
            "room_name": row["session__room__name"],
            "room_code": row["session__room__code"],
            "students": row["students"],
        }

    attempt_rows = (
        ExamAttempt.objects.filter(
            room__in=room_scope, status="in_progress", is_trial=False, final_tickets__isnull=True
        )
        .values("exam_id", "exam__title", "room_id", "room__name", "room__code")
        .annotate(students=Count("id"))
    )
    for row in attempt_rows:
        key = (row["exam_id"], row["room_id"])
        if key in merged:
            merged[key]["students"] += row["students"]
        else:
            merged[key] = {
                "exam_title": row["exam__title"],
                "room_id": row["room_id"],
                "room_name": row["room__name"],
                "room_code": row["room__code"],
                "students": row["students"],
            }

    return sorted(merged.values(), key=lambda r: (r["room_name"], r["exam_title"]))


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

    # "Hazırda gedən imtahanlar" bölməsi — axtarış/status filtrindən ASILI DEYİL
    # (filtr zal kartlarını süzür, canlı mənzərə isə tam qalmalıdır).
    live_scope = ExamRoom.objects.filter(organization=organization)
    if not can_manage:
        live_scope = live_scope.filter(pk__in=visible_room_ids)
    live_exams = _live_exam_rows(live_scope)

    page_obj = Paginator(rooms, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "exams/exam_center/room_list.html",
        {
            "page_obj": page_obj,
            "live_exams": live_exams,
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
