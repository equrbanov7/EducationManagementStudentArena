"""«Qrupdan çıxar» — tələbəni XARİC ETMƏDƏN / DONDURMADAN qrupdan çıxarmaq (sahib 2026-11-25).

Sahib: «sadəcə qrupdan çıxarmaq istəyirəm» — status «Qeydiyyatlı» qalır, tələbə qrupsuz olur (qrupa əlavə
dialoqu qrupsuzları onsuz da göstərir). İki hal:

* **Öz (əsas) qrupu** — :func:`remove_student_from_group`. Qrup dəyişikliyi DB qapısı ilə yalnız rəsmi köçürmə
  axınına buraxılır (0045 trigger-i + ``registrar_begin/finalize_student_group_transfer``); 0127 həmin axına
  NULL hədəfi (çıxarılma) əlavə edib. Axın :func:`apps.registrar.transfer.transfer_student_group`-un eynidir:
  sübut → köhnə qrupun cari dövr qeydiyyatları ``dropped`` (köçürmədəki kimi tarixçəyə; varis YARANMIR) →
  ``registrar.group_transfer`` audit sətri → yekun (DB nəsil + audit uyğunluğunu yoxlayır) → siqnal. Bal,
  davamiyyət, yekun qiymət sətirləri toxunulmur. Bölünmüş alt qrupun tələbəsinin ANA jurnaldakı sətirləri də
  (``transfer_family``: ailədən kənara köçmə kimi) tarixçəyə keçir — ayrıca audit açarı ilə.
* **Əlavə üzv** (öz qrupu başqadır, yalnız bu qrupun cari jurnallarına əlavə olunub, ``group_extra_member``) —
  :func:`remove_extra_group_member`: əlavənin TƏRSİ, hər jurnal üçün alt qrup «Çıxar»-ının eyni zənciri
  (:func:`guest_roster.remove_guest_student` + yerləşdirmə ``undo`` + :mod:`journal_removal` səbəbi). Öz qrupu
  toxunulmur.

``StudentMovement`` sətri YAZILMIR: o ledger əmr № + tarixi məcburi tələb edir və «Qrupu dəyiş» kimi qrup
reyestrinin səbəbli əməlləri ona yazılmır. İz: köçürmə sübutu + audit (+ jurnal tarixçəsi); çekmecənin
«Tarixçə»si ``dropped`` sətirləri «Çıxarılıb / köçürülüb» kimi göstərir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from apps.registrar import integrity
from apps.registrar import transfer_family as family
from apps.registrar.models import Enrollment, StudentAcademicRecord
from apps.registrar.reference_identity import (
    begin_authorized_group_transfer,
    finalize_authorized_group_transfer,
)
from apps.registrar.signals import student_group_changed
from core import audit as audit_service
from core.constants import AuditAction

_CTX = "registrar.group_removal"
#: DB yekun funksiyası audit sətrini məhz bu resurs növü ilə axtarır (0045/0127).
RESOURCE = "registrar.group_transfer"


def _validate_period(record, period) -> None:
    """Köçürmə ilə EYNİ dövr qaydası: yalnız aktiv cari dövr (yoxdursa — dövrsüz)."""
    if period is not None and getattr(period, "organization_id", None) != record.organization_id:
        raise ValidationError(pgettext(_CTX, "Akademik dövr tələbənin təşkilatına aid deyil."))
    if period is None:
        if record.organization.academic_periods.filter(is_current=True, is_active=True).exists():
            raise ValidationError(pgettext(_CTX, "Aktiv cari akademik dövr göstərilməlidir."))
    elif not getattr(period, "is_current", False) or not getattr(period, "is_active", False):
        raise ValidationError(pgettext(_CTX, "Qrupdan çıxarma yalnız aktiv cari akademik dövrdə aparılır."))


def _locked_rows(record, period, group_id):
    return list(
        Enrollment.objects.select_for_update(of=("self",))
        .filter(
            organization=record.organization,
            student=record.student,
            offering__period=period,
            offering__group_id=group_id,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering__subject")
    )


def _to_history(enrollment) -> None:
    enrollment.status = Enrollment.Status.DROPPED
    enrollment.full_clean(validate_unique=False, validate_constraints=False)
    enrollment.save(update_fields=["status", "updated_at"])


def _audit(record, old_group, moved, carried, by_user, reason, order):
    changes = {
        "removal": True,
        "moved_enrollment_ids": [str(row.pk) for row in moved],
        # Çıxarılmada varis yoxdur — DB yekunu boş siyahı tələb edir.
        "successor_enrollment_ids": [],
        "created_count": 0,
    }
    if carried:
        changes["family_carried_enrollment_ids"] = [str(row.pk) for row in carried]
    changes.update({key: value for key, value in order.items() if value})
    return audit_service.log_action(
        user=by_user,
        organization=record.organization,
        obj=record,
        action=AuditAction.UPDATE,
        resource_type=RESOURCE,
        resource_id=str(record.pk),
        resource_repr=f"{record.student_id} · {record.program.display_label}",
        old_values={"group_id": str(old_group.pk)},
        new_values={"group_id": ""},
        changes=changes,
        reason=reason
        or f"Qrupdan çıxarıldı: {old_group.name} → qrupsuz ({len(moved) + len(carried)} qeydiyyat tarixçəyə keçirildi)",
    )


@transaction.atomic
def remove_student_from_group(*, record, period, by_user, reason="", order_number="", order_date=None) -> dict:
    """Tələbəni ÖZ qrupundan çıxar: qrup → NULL, status «Qeydiyyatlı» qalır, tarixçə silinmir.

    Qaytarır: ``{"moved", "carried", "old_group", "record"}``. Qrupsuz / qeydiyyatsız tələbə üçün
    :class:`ValidationError`.
    """
    _validate_period(record, period)
    record = (
        StudentAcademicRecord.objects.select_for_update(of=("self",))
        .select_related("organization", "student", "program", "group")
        .get(pk=record.pk, organization_id=record.organization_id)
    )
    old_group = record.group
    if old_group is None:
        raise ValidationError(pgettext(_CTX, "Tələbə onsuz da heç bir qrupda deyil."))
    if record.status != "enrolled" or not record.is_active:
        raise ValidationError(
            pgettext(_CTX, "Yalnız qeydiyyatlı tələbə qrupdan çıxarılır — məzuniyyətdə / xaric edilmiş deyil.")
        )
    integrity.validate_same_organization_actor(
        organization=record.organization, user=by_user, field_name="by_user", require_active=True
    )
    if by_user is None:
        raise ValidationError({"by_user": pgettext(_CTX, "Qrupdan çıxarma üçün icraçı tələb olunur.")})

    moved, carried = [], []
    if period is not None:
        moved = _locked_rows(record, period, old_group.pk)
        # Bölünmüş alt qrupun tələbəsinin aktiv sətirləri ANA qrupun jurnalındadır — ailədən çıxır.
        parent_id = family.trail_parent_id(old_group)
        carried = _locked_rows(record, period, parent_id) if parent_id else []

    evidence_id = begin_authorized_group_transfer(record=record, new_group=None, period=period, actor_id=by_user.pk)
    for enrollment in [*moved, *carried]:
        _to_history(enrollment)
    order = {
        "order_number": str(order_number or "").strip()[:64],
        "order_date": order_date.isoformat() if hasattr(order_date, "isoformat") else str(order_date or ""),
    }
    audit = _audit(record, old_group, moved, carried, by_user, reason, order)
    finalize_authorized_group_transfer(evidence_id=evidence_id, audit_id=audit.pk)
    student_group_changed.send(
        sender=StudentAcademicRecord,
        record=record,
        old_group=old_group,
        new_group=None,
        organization=record.organization,
    )
    return {"moved": len(moved), "carried": len(carried), "old_group": old_group, "record": record}


@transaction.atomic
def remove_extra_group_member(*, record, group, period, by_user, reason="") -> dict:
    """Əlavə üzvü bu qrupun cari jurnallarından çıxar (öz qrupu toxunulmur) — əlavənin tərsi.

    Hər jurnal ayrıca savepoint-dədir (əlavədəki kimi): biri alınmasa səbəbi ilə «buraxıldı»ya düşür.
    Qaytarır: ``{"removed": [fənn…], "skipped": [{"subject", "message"}…]}``; heç biri çıxarılmasa
    :class:`ValidationError`.
    """
    from . import guest_roster, journal_removal, subgroup_placement
    from .models import RemovalAction, RemovalReason

    if by_user is None or not getattr(by_user, "pk", None):
        raise ValidationError(pgettext(_CTX, "Qrupdan çıxarma üçün icraçı tələb olunur."))
    if record.group_id == group.pk:
        raise ValidationError(pgettext(_CTX, "Bu tələbənin öz qrupudur — əlavə üzv deyil."))
    if period is None:
        raise ValidationError(pgettext(_CTX, "Cari akademik dövr yoxdur — jurnal siyahısı dəyişdirilmir."))
    rows = list(
        Enrollment.objects.filter(
            organization_id=record.organization_id,
            student_id=record.student_id,
            offering__group=group,
            offering__period=period,
            offering__is_active=True,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering__subject", "offering__organization", "offering__group", "offering__period")
        .order_by("offering__subject__name")
    )
    if not rows:
        raise ValidationError(pgettext(_CTX, "Tələbə bu qrupun cari jurnallarında yoxdur."))
    note = str(reason or "").strip() or pgettext(_CTX, "Qrup reyestrindən əlavə üzvlük götürüldü")
    cleaned = {"reason": RemovalReason.OTHER.value, "note": journal_removal.clean_note(note)}
    removed, skipped = [], []
    for enrollment in rows:
        offering = enrollment.offering
        try:
            with transaction.atomic():
                guest_roster.remove_guest_student(
                    offering=offering, enrollment=enrollment, by_user=by_user, reason=note
                )
                subgroup_placement.record_journal_removal(enrollment=enrollment, actor=by_user, reason=note)
                journal_removal.record(
                    enrollment=enrollment, action=RemovalAction.GUEST_REMOVE, cleaned=cleaned, actor=by_user
                )
        except ValidationError as exc:
            skipped.append({"subject": offering.subject.name, "message": " ".join(str(m) for m in exc.messages)})
            continue
        removed.append(offering.subject.name)
    if not removed:
        raise ValidationError(
            "; ".join(f"{item['subject']}: {item['message']}" for item in skipped)
            or pgettext(_CTX, "Heç bir jurnaldan çıxarılmadı.")
        )
    return {"removed": removed, "skipped": skipped}


__all__ = ["remove_extra_group_member", "remove_student_from_group"]
