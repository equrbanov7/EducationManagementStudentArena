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
    RoomSessionStateError,
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


def _monitor_labels():
    """JS-də render olunan etiketlərin TƏRCÜMƏLƏRİ (server-side gettext).

    Şablonun ``{% trans %}`` sətirləri ilə eyni mənbədən gəlir ki, kompüter
    xəritəsi/statistika legend ilə eyni dildə və uyğun olsun (JS-də sabit AZ
    mətn qalmasın — bax "dil problemi").
    """
    from django.utils.translation import gettext as _

    return {
        "stat": {
            "total": _("Təyin olunmuş"),
            "participated": _("İmtahan verib"),
            "connected": _("Qoşulu"),
            "waiting": _("Gözləyir"),
            "ready": _("Hazır"),
            "active": _("İmtahanda"),
            "completed": _("Bitirib"),
            "offline": _("Oflayn"),
            "removed": _("Çıxarılıb"),
            "absent": _("Gəlməyib"),
        },
        "status": {
            "assigned": _("Təyin olunub"),
            "waiting": _("Gözləyir"),
            "ready": _("Hazır"),
            "active": _("İmtahanda"),
            "completed": _("Bitirib"),
            "removed": _("Çıxarılıb"),
            "absent": _("Gəlməyib"),
        },
        "noLiveExams": _("Zalda canlı imtahan yoxdur."),
        "noResults": _("Nəticə yoxdur"),
        "allExams": _("Bütün imtahanlar"),
        "confirmStartAll": _("Zaldakı bütün hazır imtahanlar eyni anda başladılsın?"),
        "live": _("Canlı"),
        "disconnected": _("Bağlantı kəsildi"),
        "updatedAt": _("Yeniləndi"),
        "start": {
            "title": _("İmtahanı başlat"),
            "confirm": _("Başlat"),
            "failed": _("Başlatmaq mümkün olmadı."),
            "override": _("Vaxt pəncərəsindən asılı olmayaraq məcburi başlat"),
        },
        "violations": {
            "view": _("Bax"),
            "block": _("Blokla"),
            "grantChance": _("Şans ver"),
            "empty": _("Qayda pozan yoxdur"),
            "word": _("pozuntu"),
            "locked": _("Dayandırılıb"),
            "blockReason": _("Bloklama səbəbi:"),
            "confirmGrant": _("Tələbəyə əlavə şans verilib imtahan bərpa edilsin?"),
        },
    }


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
            "monitor_labels": _monitor_labels(),
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
    # Override yalnız imtahan mərkəzi üçün (vaxt pəncərəsindən kənar məcburi start).
    override = request.POST.get("override") == "1" and can_manage_final_center(request.user)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    started = 0
    last_error = ""
    for session in sessions:
        if session.state == "entry_open":
            try:
                if start_room(session, request.user, request=request, override=override):
                    started += 1
            except RoomSessionStateError as exc:
                # Vaxt pəncərəsi (tez/gec) — 500 vermə, mesaj göstər.
                last_error = str(exc)
    if is_ajax:
        payload = {"success": started > 0, "started": started, "can_override": can_manage_final_center(request.user)}
        if last_error and not started:
            payload["error"] = last_error
        return JsonResponse(payload, status=200 if started or not last_error else 409)
    if started:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Zaldakı {count} imtahan birlikdə başladıldı.").format(
                count=started
            ),
        )
    elif last_error:
        messages.error(request, last_error)
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
