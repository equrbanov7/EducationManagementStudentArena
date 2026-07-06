"""exam_center paketi — ZAL səviyyəli aqreqasiya monitoru.

Nəzarətçi bir zala baxır: o zaldakı BÜTÜN canlı imtahan oturumlarını
(fənnindən asılı olmayaraq) bir ekranda görür, hamısını birlikdə başlada
bilir və hər tələbəyə klik edərək hansı fənn/imtahan olduğunu və canlı
fəaliyyətini görür.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamRoom
from apps.exams.services.final_center import (
    HEARTBEAT_INTERVAL_SECONDS,
    can_manage_final_center,
    can_supervise_session,
    open_entry,
    room_live_sessions,
    room_monitor_snapshot,
    start_room,
)

from ._shared import supervisor_org_or_403


def _get_room_and_sessions(request, room_id):
    """
    Zalı tenant daxilində tapır və istifadəçinin nəzarət edə bildiyi canlı
    oturumları qaytarır. Ən azı bir belə oturum olmalıdır (əks halda 403).
    """
    organization = supervisor_org_or_403(request)
    room = get_object_or_404(ExamRoom, pk=room_id, organization=organization)
    sessions = [s for s in room_live_sessions(room) if can_supervise_session(request.user, s)]
    if not sessions and not can_manage_final_center(request.user):
        raise PermissionDenied(pgettext("exams.final_center.permission", "Bu zala təyin olunmamısınız."))
    return organization, room, sessions


@login_required
def exam_center_room_monitor(request, room_id):
    """Zal monitoru — bütün canlı oturumların birləşmiş görüntüsü."""
    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    snapshot = room_monitor_snapshot(room)
    return render(
        request,
        "exams/exam_center/room_monitor.html",
        {
            "room": room,
            "snapshot": snapshot,
            "heartbeat_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "can_manage": can_manage_final_center(request.user),
        },
    )


@login_required
def exam_center_room_snapshot(request, room_id):
    """Zal monitorunun JSON snapshot-u (aşağı tezlikli polling)."""
    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    return JsonResponse(room_monitor_snapshot(room))


@login_required
@require_POST
def exam_center_room_start_all(request, room_id):
    """
    Zaldakı BÜTÜN canlı oturumları birlikdə başladır (giriş açıq olanları
    aktivləşdirir). Nəzarətçi bir dəfə "başlat" deyir — zalda hansı imtahanlar
    varsa hamısı eyni anda başlayır. Hər oturum idempotent şəkildə işlənir.
    """
    _organization, room, sessions = _get_room_and_sessions(request, room_id)
    started = 0
    for session in sessions:
        if session.state == "entry_open":
            if start_room(session, request.user, request=request):
                started += 1
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "started": started})
    if started:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Zaldakı {count} imtahan birlikdə başladıldı.").format(
                count=started
            ),
        )
    else:
        messages.warning(request, pgettext("exams.final_center.message", "Başladılacaq hazır oturum tapılmadı."))
    return redirect("exams:exam_center_room_monitor", room_id=room.pk)


@login_required
@require_POST
def exam_center_room_open_all(request, room_id):
    """Zaldakı bütün hazır (prepared) oturumların girişini açır."""
    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    from apps.exams.models import ExamRoomSession

    opened = 0
    for session in ExamRoomSession.objects.filter(room=room, state="prepared"):
        if can_supervise_session(request.user, session) and open_entry(session, request.user, request=request):
            opened += 1
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "opened": opened})
    if opened:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Zaldakı {count} oturumda giriş açıldı.").format(count=opened),
        )
    else:
        messages.warning(request, pgettext("exams.final_center.message", "Giriş açılacaq oturum tapılmadı."))
    return redirect("exams:exam_center_room_monitor", room_id=room.pk)


__all__ = [
    "exam_center_room_monitor",
    "exam_center_room_open_all",
    "exam_center_room_snapshot",
    "exam_center_room_start_all",
]
