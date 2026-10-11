"""Müəllimin illik yük profilinin «Forma 7» siyahısından sinxronlaşdırılması (sahib 2026-10-11).

``TeacherWorkloadProfile`` (təşkilat × müəllim × tədris ili) üçün YALNIZ üç sahə yazılır: ``position``,
``staff_fraction``, ``is_external``. Norma (``annual_norm_hours``) və təsdiq bayrağına TOXUNULMUR —
norma tenant siyasətidir (spec §8), təsdiq isə müəllimin öz əməlidir.

* ``sync_roster_profile(..., dry_run=True)`` — fərqi hesablayır; ``dry_run=False`` ilə yazır və audit edir;
* ``restore_roster_profile(...)`` — geri qaytarma: yalnız HƏLƏ də bizim yazdığımız dəyərdə qalan sahələri
  bərpa edir (sonradan əl ilə dəyişilmiş sahəyə toxunmur); bizim yaratdığımız, təsdiqlənməmiş və
  dəyişilməmiş profil silinir.
"""

from __future__ import annotations

from decimal import Decimal

from core.audit import log_action
from core.constants import AuditAction

from ..constants import DEFAULT_ANNUAL_NORM_HOURS, TeacherPosition
from ..models import TeacherWorkloadProfile

FIELDS = ("position", "staff_fraction", "is_external")
_AUDIT_RESOURCE = "workload.TeacherWorkloadProfile"


def _plain(field: str, value):
    if field == "staff_fraction" and value is not None:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    return value


def _snapshot(profile) -> dict:
    return {field: _plain(field, getattr(profile, field)) for field in FIELDS}


def sync_roster_profile(
    *,
    organization,
    teacher,
    academic_year: str,
    position: str | None = None,
    staff_fraction=None,
    is_external: bool | None = None,
    actor=None,
    reason: str = "",
    dry_run: bool = True,
) -> dict:
    """Profil sahələrini siyahıya uyğunlaşdırır. ``None`` verilən sahə dəyişmir.

    Qaytarır: ``{"created": bool, "changed": bool, "before": dict|None, "after": dict}``.
    """
    if position is not None and position not in TeacherPosition.values:
        raise ValueError(f"workload.position_invalid: {position!r}")
    wanted = {"position": position, "staff_fraction": staff_fraction, "is_external": is_external}
    wanted = {field: _plain(field, value) for field, value in wanted.items() if value is not None}
    profile = TeacherWorkloadProfile.objects.filter(
        organization=organization, teacher=teacher, academic_year=academic_year
    ).first()
    before = _snapshot(profile) if profile is not None else None
    base = before or {
        "position": TeacherPosition.MUELLIM,
        "staff_fraction": _plain("staff_fraction", 1),
        "is_external": False,
    }
    after = {**base, **wanted}
    created = profile is None
    changed = created or after != before
    if dry_run or not changed:
        return {"created": created, "changed": changed, "before": before, "after": after}

    if profile is None:
        profile = TeacherWorkloadProfile(
            organization=organization,
            teacher=teacher,
            academic_year=academic_year,
            annual_norm_hours=DEFAULT_ANNUAL_NORM_HOURS,
        )
    profile.position = after["position"]
    profile.staff_fraction = Decimal(after["staff_fraction"])
    profile.is_external = bool(after["is_external"])
    profile.save()
    log_action(
        AuditAction.CREATE if created else AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=profile,
        old_values=before or {},
        new_values=after,
        reason=reason or "workload.roster_sync",
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(profile.pk),
        resource_repr=academic_year,
    )
    return {"created": created, "changed": True, "before": before, "after": after}


def restore_roster_profile(*, organization, teacher, academic_year: str, before, after, actor=None, reason="") -> str:
    """``sync_roster_profile`` yazısını geri qaytarır. Qaytarır: ``deleted`` / ``restored`` / ``kept``."""
    profile = TeacherWorkloadProfile.objects.filter(
        organization=organization, teacher=teacher, academic_year=academic_year
    ).first()
    if profile is None:
        return "kept"
    current = _snapshot(profile)
    if before is None:
        if current == after and profile.load_confirmed_at is None:
            profile_id = str(profile.pk)
            profile.delete()
            log_action(
                AuditAction.DELETE,
                user=actor,
                organization=organization,
                old_values=current,
                reason=reason or "workload.roster_sync_undo",
                resource_type=_AUDIT_RESOURCE,
                resource_id=profile_id,
                resource_repr=academic_year,
            )
            return "deleted"
        return "kept"
    restore = {field: before[field] for field in FIELDS if current.get(field) == after.get(field) != before[field]}
    if not restore:
        return "kept"
    for field, value in restore.items():
        setattr(profile, field, Decimal(value) if field == "staff_fraction" else value)
    profile.save(update_fields=[*restore.keys(), "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=profile,
        old_values={field: current[field] for field in restore},
        new_values=restore,
        reason=reason or "workload.roster_sync_undo",
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(profile.pk),
        resource_repr=academic_year,
    )
    return "restored"


__all__ = ["FIELDS", "restore_roster_profile", "sync_roster_profile"]
