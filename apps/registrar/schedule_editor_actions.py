"""Cədvəl redaktoru — YAZMA qatı (yarat / redaktə / köçür / park / yerləşdir).

Oxu/validasiya qatı ayrıdır: :mod:`apps.registrar.schedule_editor`.

Hər əməl köhnə axınla eyni üç şeyi edir — icazə + əhatə yoxlaması, audit sətri
(``core.audit.log_action``) və müəllim/tələbə bildirişi
(``schedule_manage_actions.notify_schedule_change``).

──────────────────────────────────────────────────────────────────────────────
MƏCBURİ DƏYİŞİKLİK («force») — SLOT İTMİR, PARKLANIR
──────────────────────────────────────────────────────────────────────────────
Sahibin tələbi: «məcburi dəyişiklik edəndə digər qrupdan müəllimin dərsi donsun,
ya da haradasa qalsın ki onu başqa yerə dəyişmək mümkün olsun».

Həyata keçirilməsi: toqquşan BAŞQA slot silinmir və üstündən yazılmır —
``is_parked=True`` alır. Parklanmış slot:

* cədvəldə (müəllim/tələbə/redaktor grid-ində) GÖRÜNMÜR;
* konflikt hesabına GİRMİR (yeri boşalır);
* redaktorun «Yenidən yerləşdirilməli» çekmecəsində QALIR və bir klikə yeni
  hüceyrəyə qoyulur (``place_parked``);
* auditə SƏBƏBİ ilə yazılır və sahiblərinə bildiriş gedir.

Fail-closed: aktorun əhatəsi toqquşan slotun qrupunu ÖRTMÜRSƏ məcburi
dəyişiklik 403-dür — başqasının cədvəlini icazəsiz sındırmaq olmaz.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import schedule_conflicts, schedule_editor, schedule_manage
from apps.registrar import schedule_manage_actions as base
from apps.registrar.models import ScheduleSlot

_CTX = "registrar.schedule_editor"
_RESOURCE_TYPE = "registrar.ScheduleSlot"

#: Məcburi dəyişikliyin səbəbi audit üçün MƏNALI olmalıdır (boş «ok» yox).
MIN_REASON = 10


def _audit(action, *, actor, organization, slot, request, reason="", old=None, new=None):
    from core.audit import log_action

    log_action(
        action,
        user=actor,
        organization=organization,
        obj=slot,
        old_values=old,
        new_values=new,
        reason=reason,
        request=request,
        resource_type=_RESOURCE_TYPE,
        resource_id=str(slot.pk),
        resource_repr=str(slot),
    )


def _slot_queryset(organization):
    return ScheduleSlot.objects.filter(organization=organization).select_related(
        "offering",
        "offering__organization",
        "offering__subject",
        "offering__group",
        "offering__period",
        "offering__instructor",
    )


def get_slot(organization, slot_id):
    return _slot_queryset(organization).filter(pk=str(slot_id or "").strip() or None).first()


def parked_rows(*, organization, period=None, group=None, actor=None) -> list[dict]:
    """«Yenidən yerləşdirilməli» siyahısı — parklanmış slotlar (silinmiş yox).

    ⚠️ ``actor`` verilibsə siyahı onun ``schedule.manage`` alt-ağacı ilə
    MƏHDUDLAŞIR (fail-closed): koordinator başqa fakültənin parklanmış dərsini
    görməməlidir. ``group`` QƏSDƏN default olaraq süzülmür — məcburi
    dəyişiklikdə yerindən çıxan dərs adətən BAŞQA qrupundur və istifadəçi onu
    dərhal görməlidir (sahibin tələbi: «haradasa qalsın ki onu başqa yerə
    dəyişmək mümkün olsun»).
    """
    queryset = _slot_queryset(organization).filter(is_parked=True)
    if period is not None:
        queryset = queryset.filter(offering__period=period)
    if group is not None:
        queryset = queryset.filter(offering__group=group)
    if actor is not None:
        scoped = schedule_manage.scoped_groups(actor, organization)
        queryset = queryset.filter(offering__group__in=scoped.values("pk"))
    return [base.slot_row(slot) for slot in queryset.order_by("weekday", "start_time")]


# ── Park ─────────────────────────────────────────────────────────────────────


def park_slot(*, actor, organization, slot, reason, request=None) -> dict:
    """Slotu yerindən çıxar, amma SAXLA (yenidən yerləşdirilməli vəziyyət)."""
    if slot.is_parked:
        return base.slot_row(slot)
    if not schedule_manage.can_manage_offering(actor, organization, slot.offering):
        raise schedule_editor.CellError(
            "permission_denied",
            pgettext(_CTX, "Toqquşan dərs sizin səlahiyyət sahənizdən kənardadır — məcburi dəyişiklik mümkün deyil."),
            status=403,
        )
    old = base.slot_row(slot)
    slot.is_parked = True
    slot.parked_at = timezone.now()
    slot.parked_by = actor if getattr(actor, "pk", None) else None
    slot.park_reason = reason or ""
    slot.save(update_fields=["is_parked", "parked_at", "parked_by", "park_reason", "updated_at"])
    row = base.slot_row(slot)
    _audit(
        "update", actor=actor, organization=organization, slot=slot, request=request, reason=reason, old=old, new=row
    )
    base.notify_schedule_change(offering=slot.offering, row=old, removed=True)
    return row


def _force_park(*, actor, organization, conflicts, reason, request):
    """Toqquşan slotları parkla — məcburi dəyişikliyin YEGANƏ yolu."""
    parked = []
    for conflict in conflicts:
        other = get_slot(organization, conflict.get("slot_id"))
        if other is None or other.is_parked:
            continue
        parked.append(park_slot(actor=actor, organization=organization, slot=other, reason=reason, request=request))
    return parked


def _require_reason(reason) -> str:
    text = (reason or "").strip()
    if len(text) < MIN_REASON:
        raise schedule_editor.CellError(
            "reason_required",
            pgettext(_CTX, "Məcburi dəyişiklik üçün ən azı 10 simvolluq səbəb yazılmalıdır (auditə düşür)."),
            errors={"reason": pgettext(_CTX, "Səbəb qısadır.")},
        )
    return text


def _apply(slot, cleaned):
    slot.weekday = cleaned["weekday"]
    slot.start_time = cleaned["start_time"]
    slot.end_time = cleaned["end_time"]
    slot.week_type = cleaned["week_type"]
    slot.kind = cleaned["kind"]
    slot.room = cleaned["room"]


def _guarded_check(*, organization, offering, cleaned, exclude_id, force, actor, reason, request):
    """Konflikt yoxlaması + (force olduqda) toqquşanların parklanması."""
    verdict = schedule_editor.check_cell(
        organization=organization, offering=offering, cleaned=cleaned, exclude_id=exclude_id
    )
    if verdict["errors"]:
        raise schedule_editor.CellError(
            "invalid",
            pgettext(_CTX, "Slot yadda saxlanılmadı — məlumatları yoxlayın."),
            errors=verdict["errors"],
        )
    if not verdict["conflicts"]:
        return []
    if not force:
        raise schedule_editor.CellError(
            "conflict",
            verdict["conflicts"][0]["message"],
            status=409,
            extra={"conflicts": verdict["conflicts"], "suggestions": verdict["suggestions"]},
        )
    return _force_park(
        actor=actor,
        organization=organization,
        conflicts=verdict["conflicts"],
        reason=_require_reason(reason),
        request=request,
    )


# ── Yarat / redaktə et ───────────────────────────────────────────────────────


def save_cell(*, actor, organization, group, period, data, request=None) -> dict:
    """Boş hüceyrədə slot yarat və ya mövcud slotu redaktə et.

    ``slot_id`` verilibsə redaktədir (fənn/müəllim/növ/həftə/otaq dəyişə bilər),
    verilməyibsə yeni slotdur. Hər iki halda açılış
    ``schedule_editor.resolve_offering`` ilə tapılır/yaradılır.
    """
    from django.contrib.auth import get_user_model

    from apps.registrar.models import Subject

    slot = get_slot(organization, data.get("slot_id")) if data.get("slot_id") else None
    cleaned, errors = schedule_editor.parse_cell(data, organization=organization)
    if errors:
        raise schedule_editor.CellError(
            "invalid", pgettext(_CTX, "Slot yadda saxlanılmadı — məlumatları yoxlayın."), errors=errors
        )

    # ⚠️ ƏHATƏ ƏVVƏL: açılış yaradılmazdan ƏVVƏL qrupun aktorun `schedule.manage`
    # alt-ağacında olduğu yoxlanılır — əks halda icazəsiz aktor rədd edilməzdən
    # əvvəl boş `CourseOffering` doğura bilərdi.
    if group is None or not schedule_manage.scoped_groups(actor, organization).filter(pk=group.pk).exists():
        raise schedule_editor.CellError(
            "permission_denied", pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."), status=403
        )

    subject = Subject.objects.filter(organization=organization, pk=str(data.get("subject_id") or "").strip()).first()
    instructor_id = str(data.get("instructor_id") or "").strip()
    instructor = get_user_model().objects.filter(pk=instructor_id).first() if instructor_id else None
    offering, _created, _assigned = schedule_editor.resolve_offering(
        actor=actor, organization=organization, group=group, period=period, subject=subject, instructor=instructor
    )
    if not schedule_manage.can_manage_offering(actor, organization, offering):
        raise schedule_editor.CellError(
            "permission_denied", pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."), status=403
        )

    force = bool(data.get("force"))
    with transaction.atomic():
        parked = _guarded_check(
            organization=organization,
            offering=offering,
            cleaned=cleaned,
            exclude_id=str(slot.pk) if slot is not None else None,
            force=force,
            actor=actor,
            reason=data.get("reason"),
            request=request,
        )
        if slot is None:
            slot = ScheduleSlot(organization=organization, offering=offering, created_by=actor)
            _apply(slot, cleaned)
            slot.save()
            row = base.slot_row(slot)
            _audit("create", actor=actor, organization=organization, slot=slot, request=request, new=row)
        else:
            old = base.slot_row(slot)
            slot.offering = offering
            _apply(slot, cleaned)
            slot.is_parked = False
            slot.parked_at = None
            slot.park_reason = ""
            slot.save()
            row = base.slot_row(slot)
            _audit("update", actor=actor, organization=organization, slot=slot, request=request, old=old, new=row)
        base.notify_schedule_change(offering=offering, row=row, removed=False)
    return {"slot": row, "parked": parked}


def move_slot(*, actor, organization, slot, data, request=None) -> dict:
    """Sürüklə-burax köçürməsi — yalnız YER dəyişir (fənn/müəllim toxunulmur)."""
    payload = {
        "slot_id": str(slot.pk),
        "subject_id": str(slot.offering.subject_id),
        "instructor_id": str(slot.offering.instructor_id or ""),
        "weekday": data.get("weekday"),
        "time_slot": data.get("time_slot"),
        "week_type": data.get("week_type") or slot.week_type,
        "slot_kind": slot.kind,
        "room": data.get("room") if data.get("room") is not None else slot.room,
        "force": data.get("force"),
        "reason": data.get("reason"),
    }
    return save_cell(
        actor=actor,
        organization=organization,
        group=slot.offering.group,
        period=slot.offering.period,
        data=payload,
        request=request,
    )


def place_parked(*, actor, organization, slot, data, request=None) -> dict:
    """Parklanmış slotu yeni hüceyrəyə qaytar (bir kliklə yenidən yerləşdirmə)."""
    if not slot.is_parked:
        raise schedule_editor.CellError("invalid", pgettext(_CTX, "Bu slot parklanmayıb."))
    return move_slot(actor=actor, organization=organization, slot=slot, data=data, request=request)


def suggestions_for(*, organization, slot=None, group=None, instructor_id=None, shift="", week_type=None, limit=8):
    """Boş hüceyrə tövsiyələri — həm slot üçün, həm də sərbəst sorğu üçün."""
    from apps.registrar.models import WeekType

    if slot is not None:
        group_id = slot.offering.group_id
        instructor_id = slot.offering.instructor_id
        week_type = week_type or slot.week_type
        exclude = (str(slot.pk),)
    else:
        group_id = getattr(group, "pk", None)
        exclude = ()
    return schedule_conflicts.suggest(
        organization=organization,
        group_id=group_id,
        instructor_id=instructor_id or None,
        week_type=week_type or WeekType.ALL,
        shift=shift,
        exclude_ids=exclude,
        limit=limit,
    )


__all__ = [
    "MIN_REASON",
    "get_slot",
    "move_slot",
    "park_slot",
    "parked_rows",
    "place_parked",
    "save_cell",
    "suggestions_for",
]
