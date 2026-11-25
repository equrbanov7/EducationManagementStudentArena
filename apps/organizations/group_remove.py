"""Ekran 06 «Qruplar» — çekmecədən «Qrupdan çıxar» (sahib 2026-11-25), ``group_action``-ın iki əməli.

* ``remove_student`` — ÖZ qrupunun tələbəsi: qrup → qrupsuz, status «Qeydiyyatlı» qalır (xaric / dondurma /
  məzuniyyət DEYİL). Rəsmi sübutlu axın registrar-dadır (``group_removal.remove_student_from_group``): köhnə
  qrupun cari jurnallarındakı sətirlər köçürmədəki kimi tarixçəyə keçir, bal/davamiyyət silinmir.
* ``remove_extra`` — «Əlavə üzv» (öz qrupu başqadır): yalnız BU qrupun cari jurnallarından çıxır, öz qrupu qalır.

POST: ``id`` (açıq qrup) + ``record_id`` + ``reason`` (≥ ``REASON_MIN_LENGTH``); ``remove_student``-də istəyə
bağlı ``order_number`` / ``order_date`` (audit sətrinə yazılır). QAPI ``_move_student`` ilə eynidir: qrup
``unit.group_manage`` əhatəsində görünməlidir, öz qrupunun tələbəsi üçün tələbənin qrupu da (əhatədən kənar 404);
öz/qrup yoldaşı qadağası ``group_action``-dadır. Əcnəbilər şöbəsinin rolları öz (əcnəbi) qruplarında işləyir —
əhatə ``group_manage_scope``-dan gəlir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from .group_actions import _error, _reason_or_none
from .group_actions import _visible_group as visible_group
from .group_roster_union import roster_group_ids

_CTX = "accounts.groups"


def _record(organization, request):
    record_id = (request.POST.get("record_id") or "").strip()
    if not record_id:
        return None
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    try:
        return (
            StudentAcademicRecord.objects.filter(organization=organization, is_active=True, pk=record_id)
            .select_related("student", "program", "organization", "group")
            .first()
        )
    except (ValueError, ValidationError):
        return None


def _rejected(exc):
    transaction.set_rollback(True)
    messages = getattr(exc, "messages", None) or [str(exc)]
    return _error(" ".join(str(message) for message in messages), status=409, code="remove_rejected")


def _order_date(request):
    raw = (request.POST.get("order_date") or "").strip()
    if not raw:
        return None, None
    try:
        value = parse_date(raw)
    except ValueError:
        value = None
    if value is None:
        return None, _error(pgettext(_CTX, "Əmr tarixi düzgün deyil."), code="order_date_invalid", field="order_date")
    return value, None


@transaction.atomic
def remove_student(request, organization, scope):
    """Öz qrupunun tələbəsini qrupdan çıxar — tələbə qrupsuz qalır, status dəyişmir."""
    unit = visible_group(organization, scope, request.POST.get("id"), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found", field="id")
    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure
    record = _record(organization, request)
    if record is None:
        return _error(pgettext(_CTX, "Tələbə qeydi tapılmadı."), status=404, code="not_found", field="record_id")
    # Ana qrupun çekmecəsi alt qruplarının tələbələrini də göstərir — tələbə öz (alt) qrupundan çıxır.
    if record.group_id is None or record.group_id not in roster_group_ids(organization, [unit])[str(unit.pk)]:
        return _error(pgettext(_CTX, "Tələbə bu qrupun tələbəsi deyil."), status=404, code="not_in_group")
    if visible_group(organization, scope, str(record.group_id), include_archived=True) is None:
        return _error(pgettext(_CTX, "Tələbənin cari qrupu sizin əhatənizdə deyil."), status=404, code="not_found")
    order_date, failure = _order_date(request)
    if failure is not None:
        return failure
    order_number = (request.POST.get("order_number") or "").strip()[:64]

    from . import student_transfer

    old_group = record.group
    period = organization.academic_periods.filter(is_current=True, is_active=True).first()
    try:
        result = student_transfer.remove_student_from_group(
            record=record,
            period=period,
            by_user=request.user,
            reason=reason,
            order_number=order_number,
            order_date=order_date,
        )
    except ValidationError as exc:
        return _rejected(exc)

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=old_group,
        request=request,
        reason=f"groups: student removed from group (groupless, still enrolled) — {reason}",
        old_values={"group": str(old_group.pk)},
        new_values={
            "group": "",
            "student": record.student.username,
            "moved": result.get("moved", 0),
            "order_number": order_number,
            "order_date": order_date.isoformat() if order_date else "",
        },
    )
    moved = result.get("moved", 0) + result.get("carried", 0)
    return JsonResponse(
        {
            "ok": True,
            "id": str(unit.pk),
            "moved": moved,
            "message": pgettext(
                _CTX, "Tələbə qrupdan çıxarıldı — statusu «Qeydiyyatlı» qaldı, %(count)d jurnal sətri tarixçəyə keçdi."
            )
            % {"count": moved},
        }
    )


@transaction.atomic
def remove_extra(request, organization, scope):
    """Əlavə üzvü bu qrupun cari jurnallarından çıxar — öz qrupu toxunulmur."""
    unit = visible_group(organization, scope, request.POST.get("id"), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found", field="id")
    reason, failure = _reason_or_none(request)
    if failure is not None:
        return failure
    record = _record(organization, request)
    if record is None:
        return _error(pgettext(_CTX, "Tələbə qeydi tapılmadı."), status=404, code="not_found", field="record_id")
    if record.group_id in roster_group_ids(organization, [unit])[str(unit.pk)]:
        return _error(
            pgettext(_CTX, "Bu tələbə qrupun öz tələbəsidir — əlavə üzv deyil."), code="not_extra", field="record_id"
        )

    from . import student_transfer

    period = organization.academic_periods.filter(is_current=True, is_active=True).first()
    try:
        result = student_transfer.remove_extra_group_member(
            record=record, group=unit, period=period, by_user=request.user, reason=reason
        )
    except ValidationError as exc:
        return _rejected(exc)

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=unit,
        request=request,
        reason=f"groups: extra member removed from group journals — {reason}",
        new_values={
            "student": record.student.username,
            "home_group": str(record.group_id or ""),
            "removed": result["removed"],
            "skipped": [item["subject"] for item in result["skipped"]],
        },
    )
    return JsonResponse(
        {
            "ok": True,
            "id": str(unit.pk),
            "removed": len(result["removed"]),
            "message": pgettext(_CTX, "Əlavə üzv qrupun %(count)d jurnalından çıxarıldı — öz qrupu dəyişmədi.")
            % {"count": len(result["removed"])},
            "warnings": [f"{item['subject']}: {item['message']}" for item in result["skipped"]],
        }
    )


__all__ = ["remove_extra", "remove_student"]
