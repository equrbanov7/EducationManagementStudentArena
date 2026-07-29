"""final_center paketi — hesabat filtrləri.

Server-tərəfli filtrasiya + səhifələmə üçün org-scoped queryset qurucuları.
Bütün sorğular ``select_related`` ilə optimallaşdırılıb; siyahılar view
qatında paginator-a verilir (yaddaşa tam yüklənmir).
"""

from django.db.models import Q

from apps.exams.models import ExamRoomSession, FinalExamTicket

from .monitor import session_list_annotations


def filter_sessions(organization, params):
    """
    Zal oturumu tarixçəsi (imtahandan asılı deyil). Filtrlər: state, room (id),
    invigilator (id), tarix aralığı (date_from/date_to, ISO), axtarış (q — zal).
    """
    qs = (
        ExamRoomSession.objects.filter(organization=organization)
        .select_related("room", "invigilator", "started_by", "ended_by")
        .order_by("-scheduled_start", "-id")
    )
    state = (params.get("state") or "").strip()
    if state:
        qs = qs.filter(state=state)
    room_id = (params.get("room") or "").strip()
    if room_id.isdigit():
        qs = qs.filter(room_id=int(room_id))
    invigilator_id = (params.get("invigilator") or "").strip()
    if invigilator_id.isdigit():
        qs = qs.filter(invigilator_id=int(invigilator_id))
    date_from = (params.get("date_from") or "").strip()
    if date_from:
        qs = qs.filter(scheduled_start__date__gte=date_from)
    date_to = (params.get("date_to") or "").strip()
    if date_to:
        qs = qs.filter(scheduled_start__date__lte=date_to)
    query = (params.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(room__name__icontains=query) | Q(room__code__icontains=query))
    return session_list_annotations(qs)


def filter_tickets(organization, params):
    """
    Bilet (tələbə iştirakı) hesabatı. Filtrlər: status, exam, session, room,
    language, removal (removal_action), tarix aralığı (date_from/date_to),
    axtarış (q — tələbə adı/username).

    Tarix "imtahan günü" mənasındadır: tələbə zala nə vaxt girib. Giriş hələ
    baş verməyibsə (təyin olunub, amma gəlməyib) oturumun planlaşdırılan günü
    götürülür — əks halda "gəlməyib" sətirləri gün hesabatından düşərdi.
    """
    qs = (
        FinalExamTicket.objects.filter(organization=organization)
        .select_related(
            "student",
            "exam",
            "exam__subject",
            "session",
            "session__room",
            "session__invigilator",
            "attempt",
            "removed_by",
        )
        .order_by("session__room__name", "seat_number", "student__last_name", "id")
    )
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    exam_id = (params.get("exam") or "").strip()
    if exam_id.isdigit():
        qs = qs.filter(exam_id=int(exam_id))
    session_id = (params.get("session") or "").strip()
    if session_id.isdigit():
        qs = qs.filter(session_id=int(session_id))
    room_id = (params.get("room") or "").strip()
    if room_id.isdigit():
        qs = qs.filter(session__room_id=int(room_id))
    language = (params.get("language") or "").strip()
    if language:
        qs = qs.filter(language=language)
    removal = (params.get("removal") or "").strip()
    if removal:
        qs = qs.filter(removal_action=removal)
    date_from = (params.get("date_from") or "").strip()
    if date_from:
        qs = qs.filter(
            Q(entry_validated_at__date__gte=date_from)
            | Q(entry_validated_at__isnull=True, session__scheduled_start__date__gte=date_from)
        )
    date_to = (params.get("date_to") or "").strip()
    if date_to:
        qs = qs.filter(
            Q(entry_validated_at__date__lte=date_to)
            | Q(entry_validated_at__isnull=True, session__scheduled_start__date__lte=date_to)
        )
    query = (params.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(student__username__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(exam__title__icontains=query)
            | Q(session__room__name__icontains=query)
            | Q(session__room__code__icontains=query)
        )
    return qs


__all__ = [
    "filter_sessions",
    "filter_tickets",
]
