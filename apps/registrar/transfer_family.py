"""Ana qrup ↔ alt qrup köçürməsi: ana qrupun jurnalı TƏK jurnal qalır (sahib 2026-11-07/08).

Sahib: «ana qrup alt qrupların cəmidir»; ana jurnal 0 göstərirsə, alt qruplarda isə tələbə varsa — bu, xətadır.
Mühazirə bir dəfə ana jurnalda yazılır, alt qruplar həmin jurnalın İÇİNDƏ seminar alt qrupudur
(:class:`~apps.registrar.models.SeminarGroup`, ``Enrollment.seminar_group``). Ailə yalnız reyestr bölgüsünün
izi ilə tanınır (``OrgUnit.settings["parent_group"]``) — ad oxşarlığı burada SAYILMIR.

Rəsmi köçürmə xidməti (:func:`apps.registrar.transfer.transfer_student_group`) bu köməkçiləri çağırır:

* :func:`return_to_parent` — «ana qrupu alt qruplara böl» (``keep_parent_journal=True``). DB qapısı (0045,
  ``registrar_finalize_student_group_transfer``) köçürmənin özündə ana qrup açılışlarında aktiv sətir QOYMUR — hər
  sətir alt qrupun açılışındakı varisə keçməlidir. Ona görə köçürmə adi qaydada yekunlaşır, SONRA eyni
  tranzaksiyada forma çevrilir (köçürmənin tərsi ilə eyni naxış): ana sətir yenidən ``enrolled`` olur (qeydləri
  yerində; provenans ``source_group`` = alt qrup, yalnız boşdursa — 0056 trigger-i bir dəfə yazmağa icazə verir),
  boş varis ``dropped`` + ``superseded_by`` = ana sətir; bu köçürmədə yaranmış alt qrup açılışı müəllimsiz və
  dərssiz qalır və passivləşdirilir (``is_active=False``) — müəllimin siyahısında ikinci jurnal görünmür;
* :func:`sync_seminar_groups` — ailə daxilində hər köçürmədən sonra ana jurnaldakı seminar yeri: alt qrupa
  keçəndə həmin alt qrupun seminar sırası (yoxdursa yaradılır), qardaş alt qrupa keçəndə yeni sıraya, ana qrupa
  qayıdanda boşaldılır. Əl ilə başqa sıraya qoyulmuş tələbəyə toxunulmur;
* :func:`is_chain_undo` — köhnə formada (alt qrup jurnalları) A → A1 → A2 → A kimi zəncirin geri qaytarılması:
  ana jurnalın tarixçə sətri məhz cari sətirlə (zəncir boyu) əvəzlənibsə, yenidən aktivləşdirilir.

Silmə yoxdur; bütün iz köçürmənin audit sətrinə yazılır.
"""

from __future__ import annotations

from apps.registrar.models import Enrollment, Lesson, SeminarGroup
from apps.registrar.models.lab_group import LAB_GROUP_MAX_NUMBER, LAB_GROUP_NAME_MAX_LENGTH
from core import audit as audit_service
from core.constants import AuditAction

#: Zəncir yoxlamasında ən çox addım (dövr və ya çox uzun zəncir — yoxlama tələb olunur).
CHAIN_LIMIT = 20
RESOURCE = "registrar.subgroup_parent_journal"
REASON = "Sahib 2026-11-08: ana qrup alt qrupların cəmidir — ana jurnal tək jurnal qalır (seminar alt qrupu)"


def trail_parent_id(group) -> str:
    """Reyestr bölgüsünün izi: alt qrupun ana qrupunun id-si (yoxdursa boş sətir)."""
    raw = group.settings if isinstance(getattr(group, "settings", None), dict) else {}
    return str(raw.get("parent_group") or "")


def family_parent_id(old_group, new_group) -> str:
    """Köçürmə bir ailə daxilindədirsə ana qrupun id-si: bölmə, geri qayıdış və ya qardaş alt qruplar arası."""
    if old_group is None or new_group is None:
        return ""
    old_trail, new_trail = trail_parent_id(old_group), trail_parent_id(new_group)
    if new_trail == str(old_group.pk):
        return new_trail
    if old_trail == str(new_group.pk):
        return old_trail
    if old_trail and old_trail == new_trail:
        return old_trail
    return ""


def _save(enrollment, fields) -> None:
    enrollment.full_clean(validate_unique=False, validate_constraints=False)
    enrollment.save(update_fields=[*fields, "updated_at"])


def return_to_parent(kept, *, subgroup) -> tuple[list, list]:
    """``kept`` = ``[(ana sətir, varis, açılış yeni)]`` → ana sətir aktiv, varis tarixçə; boş yeni açılış passiv.

    Qaytarır ``(bərpa olunan ana sətir id-ləri, passivləşən açılış id-ləri)``."""
    restored, fresh = [], {}
    for parent_row, successor, offering_is_new in kept:
        # Sıra vacibdir: ana sətrin ``superseded_by``-ı əvvəl boşalır ki, zəncirdə dövr yaranmasın.
        parent_row.status = Enrollment.Status.ENROLLED
        parent_row.superseded_by = None
        fields = ["status", "superseded_by"]
        if parent_row.source_group_id is None:
            parent_row.source_group = subgroup
            fields.append("source_group")
        _save(parent_row, fields)
        successor.status = Enrollment.Status.DROPPED
        successor.superseded_by = parent_row
        _save(successor, ["status", "superseded_by"])
        restored.append(parent_row.pk)
        if offering_is_new:
            fresh[successor.offering_id] = successor.offering
    retired = []
    for offering in fresh.values():
        busy = (
            Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED).exists()
            or Lesson.objects.filter(offering=offering).exists()
        )
        if offering.is_active and not busy:
            offering.is_active = False
            offering.save(update_fields=["is_active", "updated_at"])
            retired.append(offering.pk)
    return restored, retired


def _used_numbers(offering, rows) -> set:
    """Jurnalda tutulmuş seminar nömrələri: ``SeminarGroup`` ∪ siyahı ∪ dərslər (toqquşma olmasın)."""
    used = {row.number for row in rows}
    used.update(
        Enrollment.objects.filter(offering=offering, seminar_group__isnull=False).values_list(
            "seminar_group", flat=True
        )
    )
    used.update(
        Lesson.objects.filter(offering=offering, seminar_group__isnull=False).values_list("seminar_group", flat=True)
    )
    return used


def seminar_number(offering, unit, *, create: bool):
    """Alt qrupun bu jurnaldakı seminar nömrəsi; ``create`` olduqda yoxdursa ilk boş nömrə ilə yaradılır."""
    rows = list(SeminarGroup.objects.select_for_update().filter(offering=offering))
    for row in rows:
        if row.unit_id == unit.pk:
            return row.number
    if not create:
        return None
    used = _used_numbers(offering, rows)
    free = [number for number in range(1, LAB_GROUP_MAX_NUMBER + 1) if number not in used]
    if not free:
        return None
    row = SeminarGroup.objects.create(
        organization_id=offering.organization_id,
        offering=offering,
        number=free[0],
        name=unit.name[:LAB_GROUP_NAME_MAX_LENGTH],
        unit=unit,
    )
    return row.number


def sync_seminar_groups(*, record, old_group, new_group, period) -> dict:
    """Ailə daxilində köçürmədən sonra ana jurnaldakı seminar yeri (bax modul şərhi). Audit üçün id-lər."""
    parent_id = family_parent_id(old_group, new_group)
    if not parent_id or period is None:
        return {}
    entering = str(new_group.pk) != parent_id
    leaving = str(old_group.pk) != parent_id
    rows = (
        Enrollment.objects.select_for_update(of=("self",))
        .filter(
            organization=record.organization,
            student=record.student,
            offering__period=period,
            offering__group_id=parent_id,
            status=Enrollment.Status.ENROLLED,
        )
        .select_related("offering")
    )
    placed, cleared = [], []
    for row in rows:
        old_number = seminar_number(row.offering, old_group, create=False) if leaving else None
        if row.seminar_group is not None and row.seminar_group != old_number:
            continue  # əl ilə başqa seminar sırasına qoyulub — toxunulmur
        target = seminar_number(row.offering, new_group, create=True) if entering else None
        if row.seminar_group == target:
            continue
        row.seminar_group = target
        row.save(update_fields=["seminar_group", "updated_at"])
        (placed if target is not None else cleared).append(str(row.pk))
    return {"seminar_placed_enrollment_ids": placed, "seminar_cleared_enrollment_ids": cleared}


def after_transfer(*, record, old_group, new_group, period, by_user, kept) -> None:
    """Köçürmə yekunlaşdıqdan sonra (eyni tranzaksiya): ana jurnala qayıdış + seminar yeri + audit (fail-closed)."""
    restored, retired = return_to_parent(kept, subgroup=new_group) if kept else ([], [])
    seminar = sync_seminar_groups(record=record, old_group=old_group, new_group=new_group, period=period)
    changes = {
        "kept_in_parent_enrollment_ids": [str(pk) for pk in restored],
        "retired_offering_ids": [str(pk) for pk in retired],
        **seminar,
    }
    if not any(changes.values()):
        return
    audit_service.log_action(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=record.organization,
        obj=record,
        action=AuditAction.UPDATE,
        resource_type=RESOURCE,
        resource_id=str(record.pk),
        old_values={"group_id": str(getattr(old_group, "pk", "") or "")},
        new_values={"group_id": str(new_group.pk)},
        changes=changes,
        reason=REASON,
    )


def is_chain_undo(successor, current) -> bool:
    """Hədəf tarixçə sətri əvəzləmə zənciri boyu MƏHZ cari sətirə çatırmı (A → A1 → A2 → A)."""
    if successor.status != Enrollment.Status.DROPPED or successor.superseded_by_id is None:
        return False
    cursor, seen = successor.superseded_by_id, set()
    for _step in range(CHAIN_LIMIT):
        if cursor == current.pk:
            return True
        if cursor is None or cursor in seen:
            return False
        seen.add(cursor)
        cursor = Enrollment.objects.filter(pk=cursor).values_list("superseded_by_id", flat=True).first()
    return False


__all__ = [
    "after_transfer",
    "family_parent_id",
    "is_chain_undo",
    "return_to_parent",
    "seminar_number",
    "sync_seminar_groups",
    "trail_parent_id",
]
