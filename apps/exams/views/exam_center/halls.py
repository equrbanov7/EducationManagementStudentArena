"""exam_center paketi — otağı imtahan zalı kimi qeyd et / çıxar (AJAX, sahib 2026-10-01).

``POST /exams/center/rooms/<room_id>/exam-hall/`` — gövdə JSON
``{"is_exam_hall": true|false, "confirm": true|false}`` (və ya form sahələri).
Cavab həmişə JSON-dur:

* 200 ``{ok, changed, room_id, is_exam_hall, hall_count, message}`` — ``hall_count``
  otağın təşkilatındakı bayraqlı zalların sayıdır (KPI plitəsi yenilənir);
* 409 ``{ok: false, code, message, needs_confirm}`` — canlı oturum / aktiv
  kompüter (rədd) və ya planlaşdırılmış oturum (``needs_confirm`` → UI
  ``EMSConfirm`` ilə soruşub ``confirm: true`` ilə təkrarlayır);
* 403 / 404 / 400 ``{ok: false, message}``.

İcazə: ``can_designate_exam_halls`` (zal idarəçisi, RİM rəhbəri, superadmin,
imtahan mərkəzinin rəhbəri). Otaq aktiv təşkilat daxilində axtarılır; yalnız
superadmin başqa təşkilatın otağını dəyişə bilər (profil bölməsinin org seçicisi).
CSRF — standart middleware (``EMSCore.fetchJSON`` ``X-CSRFToken`` göndərir).
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import ExamRoom
from apps.exams.services.final_center.halls import (
    ERROR_NEEDS_CONFIRM,
    ExamHallChangeError,
    can_designate_exam_halls,
    set_exam_hall,
)
from apps.exams.views.shared.tenant import ensure_teacher_exam_tenant_context, get_active_organization
from core.http_ids import parse_int

_CTX = "exams.final_center.halls"
_TRUE = {"1", "true", "on", "yes"}


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE


def _payload(request) -> dict:
    content_type = (request.content_type or "").lower()
    if content_type.startswith("application/json"):
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:  # UnicodeDecodeError da ValueError-dur
            return {}
        return data if isinstance(data, dict) else {}
    return {key: request.POST.get(key) for key in ("is_exam_hall", "confirm")}


def _error(message, status, **extra):
    return JsonResponse({"ok": False, "message": message, **extra}, status=status)


def _resolve_room(request, room_id):
    user = request.user
    pk = parse_int(room_id)
    if pk is None:
        raise Http404
    if user.is_superuser or getattr(user, "is_superadmin", False):
        room = ExamRoom.objects.filter(pk=pk).first()
    else:
        ensure_teacher_exam_tenant_context(request)
        organization = get_active_organization(request)
        room = ExamRoom.objects.filter(pk=pk, organization=organization).first() if organization else None
    if room is None:
        raise Http404
    return room


@login_required
@require_POST
def exam_center_room_exam_hall(request, room_id):
    if not can_designate_exam_halls(request.user):
        return _error(pgettext(_CTX, "İmtahan zallarını yalnız zal idarəçiləri dəyişə bilər."), 403)
    try:
        room = _resolve_room(request, room_id)
    except Http404:
        return _error(pgettext(_CTX, "Otaq tapılmadı."), 404)

    data = _payload(request)
    if "is_exam_hall" not in data or data.get("is_exam_hall") is None:
        return _error(pgettext(_CTX, "Sorğu natamamdır: is_exam_hall göstərilməyib."), 400)
    wanted = _flag(data.get("is_exam_hall"))
    try:
        changed = set_exam_hall(room, wanted, by=request.user, request=request, confirmed=_flag(data.get("confirm")))
    except ExamHallChangeError as exc:
        return _error(str(exc), 409, code=exc.code, needs_confirm=exc.code == ERROR_NEEDS_CONFIRM)

    if wanted:
        message = pgettext(_CTX, "«%(room)s» imtahan zalı kimi qeyd edildi.") % {"room": room.name}
    else:
        message = pgettext(_CTX, "«%(room)s» imtahan zallarından çıxarıldı.") % {"room": room.name}
    hall_count = ExamRoom.objects.filter(organization_id=room.organization_id, is_exam_hall=True).count()
    return JsonResponse(
        {
            "ok": True,
            "changed": changed,
            "room_id": room.pk,
            "is_exam_hall": room.is_exam_hall,
            "hall_count": hall_count,
            "message": message,
        }
    )


__all__ = ["exam_center_room_exam_hall"]
