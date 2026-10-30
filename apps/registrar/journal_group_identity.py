"""Journal choices/filter labels use explicit aliases inside the already-authorized queryset."""

from types import SimpleNamespace

from core.group_identity import canonical_aliases

_CACHE = "_journal_canonical_group_aliases"
_FIELDS = ("id", "name", "organization_id", "parent_id", "is_active", "settings", "unit_type")


def choices_for_scope(queryset):
    rows = queryset.exclude(group_id=None).order_by().values(*(f"group__{field}" for field in _FIELDS)).distinct()
    groups = [
        SimpleNamespace(pk=row["group__id"], **{f: row[f"group__{f}"] for f in _FIELDS if f != "id"}) for row in rows
    ]
    aliases = canonical_aliases(groups)
    setattr(queryset, _CACHE, aliases)
    choices = {}
    for group in groups:
        canonical = aliases.get(group.pk, group)
        choices[str(canonical.pk)] = {"value": str(canonical.pk), "label": canonical.name}
    return sorted(choices.values(), key=lambda item: (item["label"].lower(), item["value"]))


def filter_group(queryset, group_id, *, within=None):
    if group_id is None:
        return queryset.none(), ""
    within = queryset if within is None else within
    if not hasattr(within, _CACHE):
        choices_for_scope(within)
    aliases = getattr(within, _CACHE)
    canonical_id = aliases[group_id].pk if group_id in aliases else group_id
    family = {canonical_id} | {source for source, target in aliases.items() if target.pk == canonical_id}
    return queryset.filter(group_id__in=family), str(canonical_id)


def attach_labels(offerings, *, within=None):
    aliases = getattr(within, _CACHE, None) if within is not None else None
    if aliases is None:
        aliases = canonical_aliases(offering.group for offering in offerings if offering.group_id)
    for offering in offerings:
        group = aliases.get(offering.group_id, offering.group)
        offering.journal_group_name = group.name if group is not None else ""
