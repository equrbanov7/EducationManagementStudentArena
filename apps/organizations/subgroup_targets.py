"""Reuse only validated children of the selected registry parent.

Imported empty children may lack ``settings.parent_group``. Name inference is
limited to one unambiguous parent in the same specialty, sector and metadata;
explicit links to another parent are never overridden.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.constants import OrgUnitType

from .models import OrgUnit

_SECTOR = re.compile(r"\s+(az|ing|en|eng|ru|rus)$", re.IGNORECASE)
_SECTORS = {"en": "ing", "eng": "ing", "ru": "rus"}
_KEYS = ("course_year", "admission_year", "education_form", "degree_level", "curriculum_id")


def settings(unit):
    return unit.settings if isinstance(unit.settings, dict) else {}


def name_key(name):
    return re.sub(r"\s+", "", str(name or "")).casefold()


def _sector(value):
    value = str(value or "").strip().casefold()
    return _SECTORS.get(value, value)


def _label(name):
    text = " ".join(str(name or "").split())
    match = _SECTOR.search(text)
    return (text[: match.start()], _sector(match[1])) if match else (text, "az")


def subgroup_number(parent, child):
    base, sector = _label(parent.name)
    compact = name_key(base)
    # A numeric parent requires a separator: 0361 cannot mean child 1 of 036.
    sep = r"[-/\s]+" if compact[-1:].isdigit() else r"[-/\s]*"
    loose = r"\s*".join(re.escape(char) for char in compact)
    match = re.fullmatch(
        rf"{loose}(?:\s+(?P<before>az|ing|en|eng|ru|rus))?{sep}"
        r"(?P<number>[1-9]\d*)(?:\s+(?P<after>az|ing|en|eng|ru|rus))?",
        " ".join(str(child.name).split()).casefold(),
    )
    if not match:
        return None
    sectors = {_sector(value) for value in (match["before"], match["after"]) if value}
    if len(sectors) > 1 or (next(iter(sectors)) if sectors else "az") != sector:
        return None
    return int(match["number"])


def _compatible(parent, child):
    if (
        parent.pk == child.pk
        or not parent.is_active
        or not child.is_active
        or not parent.parent_id
        or parent.organization_id != child.organization_id
        or parent.parent_id != child.parent_id
        or parent.unit_type != OrgUnitType.GROUP
        or child.unit_type != OrgUnitType.GROUP
    ):
        return False
    left, right = settings(parent), settings(child)
    for key in _KEYS:
        a, b = str(left.get(key) or "").strip(), str(right.get(key) or "").strip()
        if a and b and a != b:
            return False
    # Metadata and explicit name sectors must agree as well as each other.
    for unit in (parent, child):
        explicit = _SECTOR.search(" ".join(unit.name.split()))
        metadata = {_sector(settings(unit).get(key)) for key in ("language_sector", "sector")} - {""}
        if len(metadata) > 1 or (explicit and metadata and _sector(explicit[1]) not in metadata):
            return False
    a = _sector(left.get("language_sector") or left.get("sector")) or _label(parent.name)[1]
    b = _sector(right.get("language_sector") or right.get("sector")) or _label(child.name)[1]
    return a == b


def sibling_groups(unit):
    return list(
        OrgUnit.objects.filter(
            organization_id=unit.organization_id, parent_id=unit.parent_id, unit_type=OrgUnitType.GROUP
        ).order_by("name", "pk")
    )


def validated_parent(child, *, siblings=None):
    """Read-only, tenant-safe parent resolver for the individual-add selector."""
    units = sibling_groups(child) if siblings is None else siblings
    trail = str(settings(child).get("parent_group") or "")
    if trail:
        parent = next((unit for unit in units if str(unit.pk) == trail and _compatible(unit, child)), None)
        if parent is not None and re.match(r"^\d", parent.name) and subgroup_number(parent, child) is None:
            return None
        return parent
    # Legacy inference is only for empty children; a populated historical group
    # with no relationship metadata must not silently become another family.
    candidates = [unit for unit in units if _compatible(unit, child) and subgroup_number(unit, child) is not None]
    if len(candidates) != 1:
        return None
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    if Record.objects.filter(organization_id=child.organization_id, group=child).exists():
        return None
    return candidates[0]


def reusable_children(parent):
    units = sibling_groups(parent)
    result = [unit for unit in units if validated_parent(unit, siblings=units) == parent]
    return sorted(result, key=lambda unit: (subgroup_number(parent, unit) or 999, unit.name))


def resolve_split_targets(parent, names):
    """Resolve existing children without writes; reject aliases and foreign links."""
    # The parent is locked by split_group, serializing splits in this family.
    units = list(OrgUnit.objects.filter(organization_id=parent.organization_id, unit_type=OrgUnitType.GROUP))
    siblings = [unit for unit in units if unit.parent_id == parent.parent_id]
    chosen, seen = [], set()
    for name in names:
        matches = [unit for unit in units if name_key(unit.name) == name_key(name)]
        if not matches:
            chosen.append(None)
            continue
        if len(matches) != 1 or validated_parent(matches[0], siblings=siblings) != parent:
            raise ValidationError(f"«{name}» adlı qrup artıq var və bu ana qrupun uyğun alt qrupu deyil.")
        unit = OrgUnit.objects.select_for_update().get(pk=matches[0].pk)
        if validated_parent(unit, siblings=siblings) != parent:
            raise ValidationError(f"«{name}» alt qrupunun məlumatları dəyişib — siyahını yeniləyin.")
        if unit.pk in seen:
            raise ValidationError("Eyni alt qrup iki dəfə seçilə bilməz.")
        seen.add(unit.pk)
        chosen.append(unit)
    return chosen


def bind_parent(child, parent):
    """Persist a validated legacy relationship inside the caller's transaction."""
    if not settings(child).get("parent_group"):
        child.settings = {**settings(child), "parent_group": str(parent.pk)}
        child.save(update_fields=["settings", "updated_at"])


def eligible_records_q(unit):
    """Groupless students plus students of this child's validated parent."""
    query = Q(group__isnull=True) | Q(group__is_active=False)
    parent = validated_parent(unit)
    if parent is not None:
        query |= Q(group_id=parent.pk)
    return query, parent
