"""Canonical mapping version helpers shared by ledger and review services."""

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityMapVersion

SNAPSHOT_FIELDS = (
    "source_row_hash",
    "transform_version",
    "target_model_label",
    "target_pk",
    "state",
    "reconciliation_status",
)


class InitialVersionConflictError(Exception):
    pass


def ensure_initial_version(entity_map: LegacyEntityMap) -> LegacyEntityMapVersion:
    values = {field: getattr(entity_map, field) for field in SNAPSHOT_FIELDS}
    version, _created = LegacyEntityMapVersion.objects.get_or_create(
        entity_map=entity_map,
        version_number=1,
        defaults={
            "organization": entity_map.organization,
            "recorded_run": entity_map.created_run,
            **values,
        },
    )
    expected = {
        "organization_id": entity_map.organization_id,
        "recorded_run_id": entity_map.created_run_id,
        **values,
    }
    if any(getattr(version, field) != value for field, value in expected.items()):
        raise InitialVersionConflictError
    return version


def latest_version(entity_map: LegacyEntityMap, *, for_update=False) -> LegacyEntityMapVersion:
    queryset = LegacyEntityMapVersion.objects.filter(entity_map=entity_map).order_by("-version_number")
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first() or ensure_initial_version(entity_map)
