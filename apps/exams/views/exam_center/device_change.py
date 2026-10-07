"""exam_center paketi — final cəhdi üçün «cihaz dəyişikliyi» təsdiqi (təhlükəsizlik dizaynı 2026-10-08).

Davam edən final cəhdi başladığı cihaza bağlıdır (``services/final_center/device_binding.py``).
Tələbənin kompüteri sıradan çıxanda / zal dəyişəndə nəzarətçi və ya imtahan mərkəzi bu
endpoint ilə təsdiq verir: ``DEVICE_CHANGE_WINDOW`` ərzində tələbənin YENİ cihazdan ilk
açılışı cəhdi özünə köçürür (birdəfəlik), köhnə cihaz dayanır. Hər təsdiq audit-ə yazılır.

Kim təsdiq edə bilər: imtahan mərkəzi (``can_manage_final_center`` — PIN axtarışı səthi) və ya
bilet axınında cəhdin zal oturumunu idarə edən nəzarətçi (``can_supervise_session``).
Bilet axınında «yenidən giriş» PIN-i (``exam_center_ticket_reentry``) özü də təsdiqdir.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamAttempt, FinalExamTicket
from apps.exams.services.final_center import can_manage_final_center, can_supervise_session
from apps.exams.services.final_center.device_binding import approve_device_change, device_window_minutes

from ._shared import supervisor_org_or_403

_CTX = "exams.final_center.device"


def _ensure_can_approve(user, attempt) -> None:
    if can_manage_final_center(user):
        return
    ticket = FinalExamTicket.objects.select_related("session", "session__room").filter(attempt=attempt).first()
    if ticket is None or ticket.session is None or not can_supervise_session(user, ticket.session):
        raise PermissionDenied(
            pgettext(_CTX, "Cihaz dəyişikliyini yalnız nəzarətçi və ya imtahan mərkəzi təsdiqləyə bilər.")
        )


@login_required
@require_POST
def exam_center_final_device_change(request, attempt_id):
    organization = supervisor_org_or_403(request)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__organization", "user"),
        pk=attempt_id,
        exam__organization=organization,
        exam__exam_type_extended="final",
    )
    _ensure_can_approve(request.user, attempt)
    if attempt.is_finished:
        return JsonResponse(
            {"success": False, "error": pgettext(_CTX, "Tələbənin davam edən final cəhdi yoxdur.")}, status=409
        )
    minutes = device_window_minutes()
    if approve_device_change(attempt, by=request.user, request=request):
        message = pgettext(
            _CTX, "Cihaz dəyişikliyinə icazə verildi — tələbə %(minutes)d dəqiqə ərzində yeni cihazdan davam edə bilər."
        ) % {"minutes": minutes}
    else:
        message = pgettext(_CTX, "Cəhd hələ heç bir cihaza bağlanmayıb — tələbə ilk açdığı cihazdan davam edəcək.")
    return JsonResponse({"success": True, "message": message, "window_minutes": minutes})


__all__ = ["exam_center_final_device_change"]
