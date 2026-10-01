"""exam_center paketi — zal siyahısı (GİRİŞ səhifəsi).

Zal YARATMA/REDAKTƏ artıq imtahan mərkəzində DEYİL — o, superadmin (yaxud
``can_manage_exam_rooms`` bayraqlı idarəçi) tərəfindən profil «İmtahan zalları»
bölməsində idarə olunur. Burada nəzarətçi/mərkəz yalnız zalları görür və birbaşa
zal monitoruna («Zala daxil ol») keçir.
"""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import render
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.access_policy import can_manage_exam_rooms
from apps.exams.services.final_center import can_manage_final_center, sessions_visible_to
from apps.exams.services.final_center.halls import (
    can_designate_exam_halls,
    exam_hall_scope_q,
    group_by_building,
    natural_key,
    room_sort_key,
)
from core.search_text import tolerant_q

from ._shared import supervisor_org_or_403

_LIVE_STATES = ("entry_open", "active")
#: Səhifə ölçüsü: zal kartları (ağır) / «Hamısı» plitələri (yığcam — bütün korpuslar bir səhifədə).
_PAGE_SIZE = {"halls": 24, "all": 400}


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

    2026-10-01 (sahib): siyahı YALNIZ imtahan zallarıdır (``is_exam_hall`` +
    canlı oturumu olan otaq), korpuslar üzrə qruplaşdırılır. Zal təyin edə
    bilən (``can_designate_exam_halls``) «Hamısı» görünüşündə BÜTÜN otaqları
    görür və otağı bir kliklə zal kimi qeyd edir / zallardan çıxarır.
    """
    organization = supervisor_org_or_403(request)
    can_manage = can_manage_final_center(request.user)
    can_manage_rooms = can_manage_exam_rooms(request.user)
    can_designate = can_designate_exam_halls(request.user)
    scope = "all" if (can_designate and request.GET.get("scope") == "all") else "halls"

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
    if scope == "halls":
        rooms = rooms.filter(exam_hall_scope_q())

    query = (request.GET.get("q") or "").strip()
    # Otaq adı/kodu — ayırıcıya dözümlü («101a» → «101-A»), korpus — adi (sahib 2026-09-26).
    room_q = tolerant_q(query, ("building",), compact_fields=("name", "code"))
    if room_q is not None:
        rooms = rooms.filter(room_q)

    # Status filtri: canlı (giriş açıq/aktiv oturumu var) / boş / deaktiv.
    status = (request.GET.get("status") or "").strip()
    if status == "live":
        rooms = rooms.filter(live_session_count__gt=0)
    elif status == "idle":
        rooms = rooms.filter(live_session_count=0, is_active=True)
    elif status == "inactive":
        rooms = rooms.filter(is_active=False)

    # Korpus seçimi — seçimlər korpus süzgəcindən ƏVVƏLKİ siyahıdandır.
    room_rows = sorted(rooms, key=room_sort_key)
    buildings = sorted({(room.building or "").strip() for room in room_rows} - {""}, key=natural_key)
    building = (request.GET.get("building") or "").strip()[:120]
    if building:
        room_rows = [room for room in room_rows if (room.building or "").strip() == building]

    # "Hazırda gedən imtahanlar" bölməsi — axtarış/status filtrindən ASILI DEYİL
    # (filtr zal kartlarını süzür, canlı mənzərə isə tam qalmalıdır).
    live_scope = ExamRoom.objects.filter(organization=organization)
    if not can_manage:
        live_scope = live_scope.filter(pk__in=visible_room_ids)
    live_exams = _live_exam_rows(live_scope)

    # KPI — səhifənin başındakı rəqəmlər. Süzgəcdən ASILI DEYİL (canlı mənzərə
    # ilə eyni əhatə): ucuz aqreqat sorğular. «Zal» = imtahan zalı əhatəsi.
    kpi_rooms = live_scope.filter(is_exam_hall=True).count()
    kpi_live_rooms = live_scope.filter(sessions__state__in=_LIVE_STATES).distinct().count()

    # «Hamısı» görünüşü yığcam plitələrdir — bir səhifədə bütün korpuslar.
    page_obj = Paginator(room_rows, _PAGE_SIZE[scope]).get_page(request.GET.get("page"))
    pagination_query = urlencode(
        {
            key: value
            for key, value in (
                ("q", query),
                ("status", status),
                ("scope", scope if scope == "all" else ""),
                ("building", building),
            )
            if value
        }
    )
    building_groups = group_by_building(
        page_obj.object_list,
        room_rows,
        empty_label=pgettext("exams.final_center.halls", "Korpus göstərilməyib"),
    )
    return render(
        request,
        "exams/exam_center/room_list.html",
        {
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "building_groups": building_groups,
            "live_exams": live_exams,
            "search_query": query,
            "active_status": status,
            "active_scope": scope,
            "active_building": building,
            "buildings": buildings,
            "organization": organization,
            "can_manage": can_manage,
            "can_manage_rooms": can_manage_rooms,
            "can_designate": can_designate,
            "kpi_rooms": kpi_rooms,
            "kpi_org_rooms": live_scope.count() if can_designate else None,
            "kpi_live_rooms": kpi_live_rooms,
            "kpi_live_exams": len(live_exams),
            "kpi_live_students": sum(row["students"] for row in live_exams),
        },
    )


__all__ = [
    "exam_center_room_list",
]
