"""Tələbə idarəetməsi — YAZMA qatı: qrup köçürməsi + akademik status.

**MEXANİZM TƏKRAR YARADILMIR** (``actions.py``-dakı qayda ilə eyni):

* Köçürmə → :func:`apps.registrar.transfer.transfer_student_group`. O, iki fazalı
  sübut axınıdır (``registrar_begin_student_group_transfer`` GUC pəncərəsi altında
  ``group_id``-ni dəyişir, sonra hər qeydiyyat üçün varis yaradır, sonda
  ``registrar_finalize_student_group_transfer`` audit + nəsil zəncirini yoxlayır).
  Burada YALNIZ scope qapısı və istifadəçiyə göstərilən nəticə var.
* Status → :mod:`apps.registrar.status` state-machine-i + ``is_active`` ardıcıllığı.

⚠️ ``transfer_student_group`` ``by_user``-ın həmin təşkilatda AKTİV üzvlüyünü
tələb edir (``integrity.validate_same_organization_actor``). Superadmin üzv
olmaya bilər — o halda əməl 409 ilə anlaşılan mesaj qaytarır, 500 ilə çökmür.

⚠️ «Çıxarma» əməli tələbəni SİLMİR. Akademik statusu ``expelled`` /
``academic_leave`` edir və ``is_active``-i ona uyğunlaşdırır; qeydiyyatlar,
bal və davamiyyət tarixçəsi olduğu kimi qalır. Sərt silinmə bu səthdə YOXDUR.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..rim.lifecycle import MAX_REASON_LENGTH, MIN_REASON_LENGTH
from ..rim.policy import RimAccessError
from .academic import STATUS_LABELS, load_record, preview_group_transfer, scoped_groups_qs
from .permissions import PERM_MANAGE_ACADEMIC

_AUDIT_RESOURCE = "accounts.people.academic"

#: Status dəyişikliyi üçün səbəb MƏCBURİ olan hədəflər — dağıdıcı nəticəli
#: keçidlər (tələbə siyahılardan düşür, jurnal sətirləri passivləşir).
REASON_REQUIRED_STATUSES = frozenset({"expelled", "academic_leave"})


def _require(actor):
    if not actor.can_manage_academic:
        raise RimAccessError("permission_denied", "Tələbə idarəetməsi üçün icazəniz yoxdur.")


def _normalize_reason(reason, *, required: bool) -> str:
    text = str(reason or "").strip()
    if not required:
        return text[:MAX_REASON_LENGTH]
    if len(text) < MIN_REASON_LENGTH:
        raise RimAccessError(
            "reason_required",
            f"Bu əməliyyat üçün səbəb tələb olunur (ən azı {MIN_REASON_LENGTH} simvol).",
            status=400,
        )
    return text[:MAX_REASON_LENGTH]


def _validation_error(exc: ValidationError) -> RimAccessError:
    """Domen validasiyasını istifadəçiyə anlaşılan 409-a çevirir (500 DEYİL)."""
    messages = getattr(exc, "messages", None) or [str(exc)]
    return RimAccessError("transfer_rejected", " ".join(str(message) for message in messages), status=409)


# ── Qrup köçürməsi ───────────────────────────────────────────────────────────


def transfer_group(actor, *, record_id, new_group_id, reason="", request=None) -> dict:
    """Tələbəni başqa qrupa köçürür — rəsmi, sübutlu axınla.

    Səbəb MƏCBURİDİR: köçürmə semestr ortasında bal/davamiyyət görünürlüyünü
    dəyişir, ona görə «niyə» sualı audit sətrində cavabsız qalmamalıdır.
    """
    _require(actor)
    reason = _normalize_reason(reason, required=True)

    # Ön baxış həm SCOPE qapısıdır (record + hədəf qrup aktorun sahəsindədir),
    # həm də auditə yazılan «nə dəyişdi» şəklidir — iki dəfə hesablanmır.
    preview = preview_group_transfer(actor=actor, record_id=record_id, new_group_id=new_group_id, request=request)
    if not preview["ok"]:
        raise RimAccessError("transfer_blocked", _blocking_message(preview["blocking"]), status=409)

    record = load_record(actor, record_id, request=request)
    new_group = scoped_groups_qs(actor, request=request).filter(pk=new_group_id).first()
    if new_group is None:  # pragma: no cover — ön baxış onsuz da bloklayır
        raise RimAccessError("target_group_outside_scope", "Hədəf qrup sizin sahənizdə deyil.", status=404)

    from apps.registrar import transfer as group_transfer

    period = record.organization.academic_periods.filter(is_current=True, is_active=True).first()

    try:
        with transaction.atomic():
            result = group_transfer.transfer_student_group(
                record=record,
                new_group=new_group,
                period=period,
                by_user=actor.user,
                reason=reason,
            )
    except ValidationError as exc:
        raise _validation_error(exc) from exc

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        obj=record,
        reason=reason,
        request=request,
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(record.pk),
        resource_repr=preview["student_name"],
        old_values={"group": (preview["from_group"] or {}).get("name", "")},
        new_values={"group": (preview["to_group"] or {}).get("name", "")},
        changes={
            "action": "people.group_transferred",
            "moved": result["moved"],
            "created": result["created"],
            # Ön baxışda istifadəçiyə GÖSTƏRİLƏN rəqəmlərin eynisi auditə düşür:
            # sonradan «nə vəd olunmuşdu / nə oldu» müqayisə edilə bilsin.
            "preview_totals": preview["totals"],
        },
    )
    return {
        "moved": result["moved"],
        "created": result["created"],
        "from_group": preview["from_group"],
        "to_group": preview["to_group"],
        "reason": reason,
    }


def _blocking_message(codes) -> str:
    mapping = {
        "same_group": "Tələbə onsuz da bu qrupdadır.",
        "no_current_period": "Aktiv cari akademik dövr yoxdur — köçürmə aparıla bilməz.",
        "target_group_outside_scope": "Hədəf qrup sizin sahənizdə deyil.",
    }
    return " ".join(mapping.get(code, code) for code in codes) or "Köçürmə mümkün deyil."


# ── Akademik status ──────────────────────────────────────────────────────────


def set_academic_status(actor, *, record_id, status, reason="", request=None) -> dict:
    """Akademik statusu dəyişir (qeydiyyatlı / məzuniyyət / xaric / məzun).

    ``is_active`` statusla AVTOMATİK uyğunlaşdırılır (``status.is_active_for``) —
    konsol formasının etdiyi ilə eyni; iki yerdə fərqli qayda qalmasın.
    """
    _require(actor)
    status = str(status or "").strip()
    if status not in STATUS_LABELS:
        raise RimAccessError("unknown_status", "Naməlum akademik status.", status=400)

    reason = _normalize_reason(reason, required=status in REASON_REQUIRED_STATUSES)
    record = load_record(actor, record_id, request=request)
    previous = record.status
    if previous == status:
        raise RimAccessError("status_unchanged", "Tələbə onsuz da bu statusdadır.", status=409)

    from apps.registrar import status as academic_status

    with transaction.atomic():
        record.status = status
        record.is_active = academic_status.is_active_for(status)
        # ⚠️ `update_fields` MƏCBURİDİR: `ReferenceIdentityValidationMixin.save`
        # tam save-də `group_id`-ni də yoxlayır; sahə siyahısı onu kənarda saxlayır
        # və köçürmə qoruyucusuna toxunmadan status yazılır.
        record.save(update_fields=["status", "is_active", "updated_at"])
        academic_status.audit_status_change(
            record=record,
            previous=previous,
            by_user=actor.user,
            reason=reason,
        )
        log_action(
            AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=record,
            reason=reason or f"Akademik status: {previous} → {status}",
            request=request,
            resource_type=_AUDIT_RESOURCE,
            resource_id=str(record.pk),
            resource_repr=(record.student.get_full_name() or record.student.username).strip(),
            old_values={"status": previous},
            new_values={"status": status},
            changes={"action": "people.academic_status_changed", "is_active": record.is_active},
        )

    return {
        "status": status,
        "status_label": str(STATUS_LABELS[status]),
        "previous": previous,
        "is_active": record.is_active,
        "reason": reason,
    }


__all__ = [
    "PERM_MANAGE_ACADEMIC",
    "REASON_REQUIRED_STATUSES",
    "set_academic_status",
    "transfer_group",
]
