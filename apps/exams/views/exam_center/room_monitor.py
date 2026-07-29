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
    end_room,
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
        "confirmEndAll": _("Zaldakı bütün aktiv imtahanlar bitirilsin? Bu əməliyyat geri qaytarıla bilməz."),
        "live": _("Canlı"),
        "disconnected": _("Bağlantı kəsildi"),
        "updatedAt": _("Yeniləndi"),
        "start": {
            "title": _("İmtahanı başlat"),
            "confirm": _("Başlat"),
            "failed": _("Başlatmaq mümkün olmadı."),
        },
        "end": {
            "title": _("İmtahanı bitir"),
            "confirm": _("Bitir"),
            "failed": _("Bitirmək mümkün olmadı."),
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
            "removedBanner": _("İmtahandan uzaqlaşdırılıb"),
            "noRules": _("Qeydə alınmış qayda pozuntusu yoxdur."),
            "loadError": _("Məlumat yüklənmədi."),
        },
        "loading": _("Yüklənir…"),
    }


def _room_computer_grid(room, snapshot):
    """Qeydli kompüterlər + hər birində canlı tələbə/imtahan (seat üzrə overlay).

    Registrə edilmiş ``ExamRoomComputer`` sətirlərinin üstünə snapshot-un canlı
    tələbə sətirlərini ``seat_number`` uyğunluğu ilə yerləşdirir — nəzarətçi
    hansı kompüterdə hansı imtahanın getdiyini birbaşa görür.
    """
    # İki uyğunlaşdırma açarı: (1) birbaşa kompüter id (cəhd hansı kompüterlə
    # möhürlənib) — ƏSAS; (2) seat_number — köhnə/geriyə-uyğun fallback. Birinci
    # sayəsində seat_number NULL olsa belə dolu PC boş görünmür (bug fix).
    by_computer = {}
    seat_map = {}
    for row in snapshot.get("students", []):
        cid = row.get("computer_id")
        if cid is not None and cid not in by_computer:
            by_computer[cid] = row
        seat = row.get("seat")
        if seat is not None and seat not in seat_map:
            seat_map[seat] = row
    computers = []
    # Yalnız AKTİV kompüterlər — deaktiv qeydlər giriş hüququ vermir (bax
    # exam_center_gate), ona görə xəritədə göstərilib nəzarətçini çaşdırmasın.
    for comp in room.computers.filter(is_active=True):
        occupant = by_computer.get(comp.pk) or seat_map.get(comp.seat_number)
        computers.append({"computer": comp, "occupant": occupant})
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
def exam_center_attempt_violations(request, room_id, attempt_id):
    """Bir cəhdin (tələbənin) pozuntu detalları — hansı qaydalar, nə vaxt
    pozulub + varsa imtahandan uzaqlaşdırma səbəbi. Zal nəzarətçisi tələbə
    xanasına və ya "qayda pozanlar" siyahısındakı "Bax"a klik edəndə açılan
    kiçik modal üçün. Yalnız bu zala aid cəhdlər (tenant + zal skopu)."""
    from apps.exams.models import ExamAttempt
    from apps.exams.services.supervision import get_attempt_intervention

    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("user", "exam"),
        pk=attempt_id,
        room_id=room.id,
    )
    incidents = attempt.supervision_incidents.order_by("-timestamp")[:200]
    intervention = get_attempt_intervention(attempt)
    return JsonResponse(
        {
            "student": attempt.user.get_full_name() or attempt.user.username,
            "username": attempt.user.username,
            "exam_title": attempt.exam.title,
            "violation_count": attempt.supervision_violation_count,
            "supervision_status": attempt.supervision_status,
            "removal": (
                {
                    "action": intervention.get("action"),
                    "reason": intervention.get("reason"),
                    "is_terminal": intervention.get("is_terminal"),
                }
                if intervention
                else None
            ),
            "incidents": [
                {
                    "event": inc.get_event_type_display(),
                    "code": inc.event_type,
                    "severity": inc.severity,
                    "at": inc.timestamp.isoformat(),
                }
                for inc in incidents
            ],
        }
    )


@login_required
@require_POST
def exam_center_room_start_all(request, room_id):
    """
    Zaldakı BÜTÜN canlı oturumları birlikdə başladır (giriş açıq olanları
    aktivləşdirir). Nəzarətçi bir dəfə "başlat" deyir — zalda hansı imtahanlar
    varsa hamısı eyni anda başlayır. Hər oturum idempotent şəkildə işlənir.
    """
    _organization, room, sessions = _get_room_and_sessions(request, room_id)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    started = 0
    last_error = ""
    for session in sessions:
        if session.state == "entry_open":
            try:
                if start_room(session, request.user, request=request):
                    started += 1
            except RoomSessionStateError as exc:
                # State yarışı (paralel idarə) — 500 vermə, mesaj göstər.
                last_error = str(exc)
    if is_ajax:
        payload = {"success": started > 0, "started": started}
        if last_error and not started:
            payload["error"] = last_error
        elif not started:
            # Düymə daimi görünür (2026-07-29) — boş halda istifadəçi NİYƏ heç
            # nə başlamadığını bilməlidir.
            payload["error"] = pgettext(
                "exams.final_center.message",
                "Başladılacaq oturum yoxdur — tələbə qeydli kompüterdən PIN ilə girəndə oturum avtomatik yaranır.",
            )
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
def exam_center_room_end_all(request, room_id):
    """
    Zaldakı BÜTÜN aktiv oturumları birlikdə bitirir. Nəzarətçi bir dəfə
    "hamısını bitir" deyir — zalda gedən hansı imtahanlar varsa hamısı
    yekunlaşır (cavablar qorunur; tələbələr ``completed``/``absent`` olur).
    Hər oturum idempotent işlənir.
    """
    _organization, room, sessions = _get_room_and_sessions(request, room_id)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    ended = 0
    for session in sessions:
        if session.state == "active" and end_room(session, request.user, request=request):
            ended += 1
    if is_ajax:
        payload = {"success": ended > 0, "ended": ended}
        if not ended:
            payload["error"] = pgettext(
                "exams.final_center.message", "Bitiriləcək aktiv imtahan yoxdur — zalda gedən oturum tapılmadı."
            )
        return JsonResponse(payload)
    if ended:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Zaldakı {count} imtahan birlikdə bitirildi.").format(count=ended),
        )
    else:
        messages.warning(request, pgettext("exams.final_center.message", "Bitiriləcək aktiv oturum tapılmadı."))
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
    "exam_center_room_end_all",
    "exam_center_room_monitor",
    "exam_center_room_open_all",
    "exam_center_room_snapshot",
    "exam_center_room_start_all",
]
