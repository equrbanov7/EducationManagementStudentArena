"""exam_center paketi — zal nəzarətçisi NÖVBƏLƏRİ + nəzarətçi qeydi (2026-10-13, gecə).

* ``POST center/rooms/<room_id>/duties/`` — rəhbər zala vaxtla məhdud növbə yazır
  (nəzarətçilər + gün + saat aralığı). İcazə: ``can_assign_invigilators``.
* ``POST center/rooms/<room_id>/duties/<duty_id>/revoke/`` — növbəni dərhal bağlayır.
* ``POST center/rooms/<room_id>/api/attempts/<attempt_id>/note/`` — zalın nəzarətçisi
  (aktiv növbə) və ya mərkəz tələbə haqqında qısa hadisə qeydi yazır → ``ProctoringLog``
  (``kind=invigilator_note``, ciddilik ``info`` — risk xalını ARTIRMIR, xronologiyada görünür).

Hər üçü obyekt səviyyəsində yoxlanır (zal aktiv təşkilatdadır; cəhd HƏMİN zaldadır);
UI düymələrinin gizlədilməsi təhlükəsizlik deyil.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamAttempt, ExamRoom, InvigilatorDuty
from apps.exams.services.access_policy import can_assign_invigilators
from apps.exams.services.final_center.duty_admin import (
    DutyError,
    create_duties,
    eligible_invigilators,
    parse_duty_window,
    revoke_duty,
)
from core.rate_limit import record_rate_limit_hit

from ._shared import center_staff_queryset, supervisor_org_or_403

_CTX = "exams.final_center.duty"
#: ``sanitize_signal_detail`` sətirləri 200 simvola kəsir — eyni hədd.
_NOTE_MAX_LEN = 200
_NOTE_RATE = "30/10m"


def _head_room_or_403(request, room_id):
    organization = supervisor_org_or_403(request)
    if not can_assign_invigilators(request.user):
        raise PermissionDenied(
            pgettext("exams.final_center.permission", "Zala nəzarətçi təyini yalnız imtahan mərkəzi rəhbəri üçündür.")
        )
    room = get_object_or_404(ExamRoom.objects.select_related("organization"), pk=room_id, organization=organization)
    return organization, room


@login_required
@require_POST
def exam_center_room_duty_create(request, room_id):
    organization, room = _head_room_or_403(request, room_id)
    requested = {int(raw) for raw in request.POST.getlist("invigilators") if (raw or "").strip().isdigit()}
    try:
        starts_at, ends_at = parse_duty_window(
            request.POST.get("duty_date"), request.POST.get("start_time"), request.POST.get("end_time")
        )
        users = eligible_invigilators(center_staff_queryset(organization), requested) if requested else []
        if requested and len(users) != len(requested):
            raise DutyError(
                pgettext(_CTX, "Seçilənlərdən bəziləri nəzarətçi ola bilməz (tələbə və ya kənar istifadəçi).")
            )
        created = create_duties(
            room, users, starts_at, ends_at, by=request.user, note=request.POST.get("note", ""), request=request
        )
    except DutyError as exc:
        messages.error(request, str(exc))
        return redirect("exams:exam_center_room_monitor", room_id=room.pk)
    messages.success(
        request,
        pgettext(_CTX, "%(count)d nəzarətçi növbəsi yazıldı.") % {"count": len(created)},
    )
    return redirect("exams:exam_center_room_monitor", room_id=room.pk)


@login_required
@require_POST
def exam_center_room_duty_revoke(request, room_id, duty_id):
    _organization, room = _head_room_or_403(request, room_id)
    duty = get_object_or_404(InvigilatorDuty.objects.select_related("room__organization"), pk=duty_id, room=room)
    if revoke_duty(duty, by=request.user, request=request):
        messages.success(request, pgettext(_CTX, "Növbə ləğv edildi — nəzarətçinin çıxışı bağlandı."))
    else:
        messages.info(request, pgettext(_CTX, "Növbə artıq ləğv olunub."))
    return redirect("exams:exam_center_room_monitor", room_id=room.pk)


@login_required
@require_POST
def exam_center_attempt_note(request, room_id, attempt_id):
    """Nəzarətçi qeydi — yalnız bu zalın cəhdi, yalnız aktiv növbə/mərkəz."""
    from .room_monitor import _get_room_and_sessions

    _organization, room, _sessions = _get_room_and_sessions(request, room_id)
    attempt = get_object_or_404(ExamAttempt.objects.select_related("exam"), pk=attempt_id, room_id=room.pk)
    text = (request.POST.get("text") or "").strip()
    if not text:
        return JsonResponse({"success": False, "error": pgettext(_CTX, "Qeyd boşdur.")}, status=400)
    exceeded, _retry = record_rate_limit_hit("invigilator_note", _NOTE_RATE, request.user.id)
    if exceeded:
        return JsonResponse(
            {"success": False, "error": pgettext(_CTX, "Çox sayda qeyd — bir az gözləyin.")}, status=429
        )
    from apps.exams.services.supervision.signals import log_proctoring_signal

    log_proctoring_signal(
        attempt,
        "invigilator_note",
        {"text": text[:_NOTE_MAX_LEN], "by": request.user.get_full_name() or request.user.username},
    )
    return JsonResponse({"success": True})


__all__ = ["exam_center_attempt_note", "exam_center_room_duty_create", "exam_center_room_duty_revoke"]
