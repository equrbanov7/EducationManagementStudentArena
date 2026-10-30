"""Explicit canonical pointer: UI/import vahid qrupu, tarixi row isə öz FK-sini saxlayır."""

import re
import uuid

from django.apps import apps as django_apps

from . import ke233_alias_spec as spec


def _name_key(name):
    return re.sub(r"\s+", "", name or "").casefold().removesuffix("az")


def verified_aliases(groups):
    """Ad oxşarlığı pointer YARATMIR; yalnız idarə edilmiş exact alias metadata-sını yoxlayır."""
    groups = list({g.pk: g for g in groups}.values())
    candidates = {}
    for group in groups:
        pointer = (group.settings or {}).get("canonical_group")
        if str(group.organization_id) != spec.ORG or str(group.pk) != spec.SOURCE or pointer != spec.TARGET:
            continue
        if group.unit_type != "group" or group.is_active or (group.settings or {}).get("parent_group"):
            continue
        try:
            candidates[group.pk] = uuid.UUID(str(pointer))
        except (ValueError, TypeError, AttributeError):
            continue
    if not candidates:
        return {}
    model = django_apps.get_model("organizations", "OrgUnit")
    targets = {
        g.pk: g
        for g in model.objects.filter(
            organization_id=spec.ORG, pk__in=candidates.values(), is_active=True, unit_type="group"
        )
    }
    found = {}
    for source in groups:
        target = targets.get(candidates.get(source.pk))
        if target is None or target.organization_id != source.organization_id or target.parent_id != source.parent_id:
            continue
        if (target.settings or {}).get("parent_group") or _name_key(source.name) != _name_key(target.name):
            continue
        keys = ("degree_level", "education_form", "sector")
        if any((source.settings or {}).get(key) != (target.settings or {}).get(key) for key in keys):
            continue
        if (source.settings or {}).get("sector") != "az":
            continue
        found[source.pk] = target
    return found


def preserve_historical_bindings(row, requested_groups):
    """Canonical seçim eyni tarixi qrupu fiziki əvəz etmir; başqa qrupa normal keçid qalır."""
    if row._state.adding:
        return requested_groups
    existing = list(row.groups.all())
    aliases = verified_aliases(existing)
    by_target = {}
    for source in existing:
        if source.pk in aliases:
            by_target.setdefault(aliases[source.pk].pk, []).append(source)
    result = {}
    for group in requested_groups:
        originals = by_target.get(group.pk, ())
        chosen = originals[0] if len(originals) == 1 else group
        result[chosen.pk] = chosen
    return list(result.values())
