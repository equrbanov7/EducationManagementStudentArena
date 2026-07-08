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
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamRoom
from apps.exams.services.access_policy import can_assign_invigilators
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
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_staff_queryset, supervisor_org_or_403


def _user_is_room_invigilator(user, room) -> bool:
    """İstifadəçi bu zala (zal-səviyyəsində) nəzarətçi kimi təyin olunubmu?"""
    return room.invigilators.filter(id=user.id).exists()


def _get_room_and_sessions(request, room_id):
    """
    Zalı tenant daxilində tapır və istifadəçinin nəzarət edə bildiyi canlı
    oturumları qaytarır.

    Giriş: imtahan mərkəzi HƏMİŞƏ; zala təyin olunmuş nəzarətçi canlı oturum
    olmasa da (zalı boşkən də) daxil olub kompüter xəritəsinə baxa bilər.
    """
    organization = supervisor_org_or_403(request)
    room = get_object_or_404(ExamRoom, pk=room_id, organization=organization)
    sessions = [s for s in room_live_sessions(room) if can_supervise_session(request.user, s)]
    if not sessions and not can_manage_final_center(request.user) and not _user_is_room_invigilator(request.user, room):
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


def _room_computer_grid(room, snapshot):
    """Qeydli kompüterlər + hər birində canlı tələbə/imtahan (seat üzrə overlay).

    Registrə edilmiş ``ExamRoomComputer`` sətirlərinin üstünə snapshot-un canlı
    tələbə sətirlərini ``seat_number`` uyğunluğu ilə yerləşdirir — nəzarətçi
    hansı kompüterdə hansı imtahanın getdiyini birbaşa görür.
    """
    seat_map = {}
    for row in snapshot.get("students", []):
        seat = row.get("seat")
        if seat is not None and seat not in seat_map:
            seat_map[seat] = row
    computers = []
    for comp in room.computers.all():
        computers.append({"computer": comp, "occupant": seat_map.get(comp.seat_number)})
    return computers


@login_required
def exam_center_room_monitor(request, room_id):
    """Zal monitoru — bütün canlı oturumların birləşmiş görüntüsü + kompüter xəritəsi."""
    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    snapshot = room_monitor_snapshot(room)
    can_manage = can_manage_final_center(request.user)

    room = ExamRoom.objects.prefetch_related("computers", "invigilators").get(pk=room.pk)
    invigilators = list(room.invigilators.all())
    # Nəzarətçi təyini YALNIZ imtahan mərkəzi RƏHBƏRİ üçün (işçi görmür).
    can_assign = can_assign_invigilators(request.user)

    return render(
        request,
        "exams/exam_center/room_monitor.html",
        {
            "room": room,
            "snapshot": snapshot,
            "heartbeat_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "can_manage": can_manage,
            "can_assign_invigilators": can_assign,
            "monitor_labels": _monitor_labels(),
            "room_computers": _room_computer_grid(room, snapshot),
            "room_invigilators": invigilators,
            # Namizədlər AJAX ilə yüklənir (sistemi yükləməmək üçün) — səhifə
            # açılışında bütün istifadəçilər render olunmur; bax user_search lookup.
            "invigilator_search_url": reverse("exams:invigilator_search"),
        },
    )


@login_required
@require_POST
def exam_center_room_assign_invigilators(request, room_id):
    """Zala nəzarətçi(lər) təyin edir — yalnız imtahan mərkəzi.

    ``ExamRoom.invigilators`` M2M-ni POST-dakı istifadəçi id-ləri ilə əvəz edir.
    Yalnız org-un tələbə olmayan aktiv üzvləri qəbul edilir (kənar id-lər atılır).
    İcazə: yalnız imtahan mərkəzi RƏHBƏRİ (``can_assign_invigilators``) — işçi YOX.
    """
    organization = supervisor_org_or_403(request)
    if not can_assign_invigilators(request.user):
        raise PermissionDenied(
            pgettext("exams.final_center.permission", "Zala nəzarətçi təyini yalnız imtahan mərkəzi rəhbəri üçündür.")
        )
    room = get_object_or_404(ExamRoom, pk=room_id, organization=organization)

    requested_ids = set()
    for raw in request.POST.getlist("invigilators"):
        raw = (raw or "").strip()
        if raw.isdigit():
            requested_ids.add(int(raw))
    valid_users = list(center_staff_queryset(organization).filter(id__in=requested_ids)) if requested_ids else []
    room.invigilators.set(valid_users)

    log_action(
        AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=room,
        reason="final_room_invigilators_set",
        request=request,
        changes={"invigilator_ids": sorted(u.id for u in valid_users)},
        resource_type="exam_room",
        resource_id=str(room.pk),
    )
    messages.success(
        request,
        pgettext("exams.final_center.message", "Zala {count} nəzarətçi təyin olundu.").format(count=len(valid_users)),
    )
    return redirect("exams:exam_center_room_monitor", room_id=room.pk)


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
    "exam_center_room_assign_invigilators",
    "exam_center_room_monitor",
    "exam_center_room_open_all",
    "exam_center_room_snapshot",
    "exam_center_room_start_all",
]
