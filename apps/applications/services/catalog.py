"""Kataloq seed-i — İDEMPOTENT.

Miqrasiya da, ``seed_application_catalog`` idarəetmə əmri də bu funksiyanı
çağırır. Mövcud sətir varsa TOXUNULMUR: tenant kataloqu redaktə edibsə
(handler rolu dəyişib, SLA artıb) təkrar miqrasiya onu geri qaytarmamalıdır.
"""

from __future__ import annotations

from ..constants import DEFAULT_KIND_SEED, DEFAULT_UNIT_SEED
from ..models import ApplicationKind, ApplicationUnit


def seed_units(organization, *, unit_model=None) -> dict:
    model = unit_model or ApplicationUnit
    existing = {unit.code: unit for unit in model.objects.filter(organization=organization)}
    for order, spec in enumerate(DEFAULT_UNIT_SEED):
        if spec["code"] in existing:
            continue
        existing[spec["code"]] = model.objects.create(
            organization=organization,
            code=spec["code"],
            name=spec["name"],
            note=spec["note"],
            handler_role_names=list(spec["handler_role_names"]),
            resolve_by=spec["resolve_by"],
            default_sla_days=spec["default_sla_days"],
            order=order,
            is_active=True,
        )
    return existing


def seed_kinds(organization, units: dict, *, kind_model=None) -> dict:
    model = kind_model or ApplicationKind
    existing = {kind.code: kind for kind in model.objects.filter(organization=organization)}
    for order, spec in enumerate(DEFAULT_KIND_SEED):
        if spec["code"] in existing:
            continue
        target = units.get(spec["unit_code"])
        if target is None:
            continue
        existing[spec["code"]] = model.objects.create(
            organization=organization,
            code=spec["code"],
            label=spec["label"],
            note=spec["note"],
            allowed_sender_families=list(spec["allowed_sender_families"]),
            target_unit=target,
            route_overrides=dict(spec.get("route_overrides") or {}),
            sla_days=spec["sla_days"],
            badge_palette=spec["badge_palette"],
            order=order,
            is_active=True,
        )
    return existing


def seed_catalog(organization, *, unit_model=None, kind_model=None) -> tuple:
    """Bir təşkilat üçün şöbə + növ kataloqunu doldurur (idempotent)."""
    units = seed_units(organization, unit_model=unit_model)
    kinds = seed_kinds(organization, units, kind_model=kind_model)
    return units, kinds


__all__ = ["seed_catalog", "seed_kinds", "seed_units"]
