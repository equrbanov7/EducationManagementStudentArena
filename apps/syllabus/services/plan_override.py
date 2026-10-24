"""Plan saatının əl ilə düzəlişi — kafedra / tədris şöbəsi (sahib 2026-10-25).

«Fənn 75 saatdır … müəllimin dərs yükü 105 saat olsa da, sillabus olaraq 75 saat yazmalıdır. Bu tip məsələləri
tənzimləmək olsun.»  Avtomatik hesab (tədris planı → yükdə bir qrupa düşən pay) qeyri-müəyyən halda (yalnız cəmi
idxal olunmuş birləşmə sətri) səhv çıxa bilər — dosyenin ``plan_hours_override``-u onu ÜSTƏLƏYİR.

* Kim: kafedra müdiri (``syllabus.approve``, kafedra səviyyəli əhatə), ``syllabus.manage`` və ya
  ``workload.manage`` (tədris şöbəsi / kafedra yükü) əhatəsi kafedranı tutan aktor; superadmin.  Müəllif ÖZ
  sillabusunun saatını yalnız org-wide əhatə ilə dəyişə bilər (müəllim saatı əl ilə yazmasın — 2026-10-12).
* Nə yazılır: dosyenin ``plan_hours_override``-u + arxivdən başqa bütün versiyaların ``plan_hours`` sahəsi.
  Redaktəyə açıq versiyada ``set_plan_hours`` (tamamlanma yenidən hesablanır), təqdim/baxış/təsdiqlənmiş
  versiyada YALNIZ plan sahəsi — bölmələrə (müəllimin həftəlik bölgüsünə) toxunulmur; həftəlik cədvəlin sətir
  sayı ``week_plan.expected_week_rows`` ilə plandan özü çıxır.
* Boş saat → düzəliş silinir, versiyalar çağıranın verdiyi avtomatik saata (``auto_hours``) qayıdır.
* Hər əməl ``audit_auditlog``-a düşür (köhnə/yeni dəyər).
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import EDITABLE_STATUSES, PERM_APPROVE, PERM_MANAGE, SyllabusStatus
from ..models import Syllabus, SyllabusVersion
from ..state_machine import TransitionDenied
from .plan_hours import set_plan_hours
from .reuse_rules import normalize_hours
from .scoping import is_author

#: Dərs yükü modulunun açarı (tədris şöbəsi, kafedra) — string, workload import edilmir.
PERM_WORKLOAD_MANAGE = "workload.manage"

#: Ağlabatan yuxarı hədd (bir növ üçün semestr saatı).
MAX_PLAN_HOURS = 300


def _allowed_by(actor, syllabus, permission: str, *, chair_level: bool = False) -> bool:
    if not actor.has(permission):
        return False
    if is_author(actor, syllabus) and not actor.scope_for(permission).is_org_wide:
        return False
    if chair_level:
        return actor.covers_chair_unit(syllabus.chair_unit_id, permission)
    if syllabus.chair_unit_id is None:
        return actor.scope_for(permission).is_org_wide
    return actor.covers_unit(syllabus.chair_unit_id, permission)


def can_override_plan_hours(actor, syllabus) -> bool:
    """Aktor bu dosyenin plan saatını əl ilə düzəldə bilərmi (fail-closed)."""
    if actor is None or syllabus is None:
        return False
    if actor.is_superadmin:
        return True
    return (
        _allowed_by(actor, syllabus, PERM_APPROVE, chair_level=True)
        or _allowed_by(actor, syllabus, PERM_MANAGE)
        or _allowed_by(actor, syllabus, PERM_WORKLOAD_MANAGE)
    )


def clean_override_hours(hours) -> dict:
    """``{növ: 1..MAX}`` — mənfi/yanlış dəyərlər atılır, hədd kəsilir."""
    return {kind: min(value, MAX_PLAN_HOURS) for kind, value in normalize_hours(hours).items()}


def write_version_plan_hours(version, hours) -> bool:
    """Versiyanın plan saatı sahəsini yazır → dəyişdisə ``True``.

    Redaktəyə açıq versiya — ``set_plan_hours`` (kilid + tamamlanma); arxiv — dəyişmir; qalan statuslarda
    (təqdim / baxış / təsdiqlənmiş) YALNIZ ``plan_hours`` sütunu — bölmələr toxunulmaz qalır.
    """
    cleaned = normalize_hours(hours)
    if not cleaned or normalize_hours(version.plan_hours) == cleaned:
        return False
    if version.status == SyllabusStatus.ARCHIVED.value:
        return False
    if version.status in EDITABLE_STATUSES:
        set_plan_hours(version, cleaned)
        return normalize_hours(version.plan_hours) == cleaned
    updated = SyllabusVersion.objects.filter(pk=version.pk, status=version.status).update(plan_hours=cleaned)
    if updated:
        version.plan_hours = cleaned
    return bool(updated)


@transaction.atomic
def set_plan_hours_override(*, syllabus, hours, actor, auto_hours=None, request=None) -> dict:
    """Dosyenin plan saatını əl ilə təyin edir (boş → silir) → ``{override, effective, versions}``."""
    if not can_override_plan_hours(actor, syllabus):
        raise TransitionDenied("transition.permission_denied")
    locked = Syllabus.objects.select_for_update().get(pk=syllabus.pk)
    cleaned = clean_override_hours(hours)
    old = normalize_hours(locked.plan_hours_override)
    if old != cleaned:
        Syllabus.objects.filter(pk=locked.pk).update(plan_hours_override=cleaned)
    syllabus.plan_hours_override = cleaned
    effective = cleaned or normalize_hours(auto_hours)
    touched = []
    if effective:
        versions = SyllabusVersion.objects.filter(syllabus=locked).exclude(status=SyllabusStatus.ARCHIVED.value)
        for version in versions.order_by("created_at"):
            before = normalize_hours(version.plan_hours)
            if write_version_plan_hours(version, effective):
                touched.append({"version": version.label, "status": version.status, "old": before})
    if old != cleaned or touched:
        anchor = locked.current_version or locked.approved_version
        log_action(
            AuditAction.UPDATE,
            user=getattr(actor, "user", None),
            organization=locked.organization,
            obj=anchor or locked,
            request=request,
            resource_type="syllabus.plan_hours",
            resource_id=str(locked.pk),
            resource_repr=f"{locked.subject_id} plan_hours_override",
            old_values={"plan_hours_override": old},
            new_values={"plan_hours_override": cleaned, "effective": effective},
            changes={"versions": touched},
            reason="Plan saatının əl ilə düzəlişi (sahib 2026-10-25)",
        )
    return {"override": cleaned, "effective": effective, "versions": touched}


__all__ = [
    "MAX_PLAN_HOURS",
    "PERM_WORKLOAD_MANAGE",
    "can_override_plan_hours",
    "clean_override_hours",
    "set_plan_hours_override",
    "write_version_plan_hours",
]
