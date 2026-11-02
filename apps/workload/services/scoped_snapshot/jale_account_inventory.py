"""Fixed two-account reference census before any separately reviewed consolidation."""

import hashlib
import json

from django.apps import apps
from django.contrib.auth import get_user_model

from .data import ORG

TEACHERS = (7730, 8388)
CAP = 2000


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def collect_jale_account_inventory():
    """Counts/opaque digests only; unscoped references stay explicit holds, never guessed."""
    result = []
    for rel in get_user_model()._meta.get_fields(include_hidden=True):
        if not rel.auto_created or rel.concrete or rel.related_model is None:
            continue
        model = rel.related_model
        field = rel.field.attname
        # Export the ORM relation name, not a raw identifier-column label.
        # In particular, the general snapshot never emits a student_id key/value.
        relation_name = rel.field.name
        names = {f.name for f in model._meta.concrete_fields}
        scoped = "organization" in names
        shared_auth = model._meta.app_label == "auth"
        for teacher in TEACHERS:
            query = model._base_manager.filter(**{field: teacher})
            if scoped:
                query = query.filter(organization_id=ORG)
            # No cross-tenant content is read from models lacking an org key.
            if not scoped and not shared_auth:
                result.append(
                    {
                        "model": model._meta.label,
                        "field": relation_name,
                        "user_id": teacher,
                        "classification": "tenant_scope_unresolved_no_rows_read",
                    }
                )
                continue
            rows = list(query.order_by("pk").values()[: CAP + 1])
            result.append(
                {
                    "model": model._meta.label,
                    "field": relation_name,
                    "user_id": teacher,
                    "classification": "tenant_scoped" if scoped else "shared_auth_metadata",
                    "count_or_lower_bound": len(rows),
                    "truncated": len(rows) > CAP,
                    "ids": [str(row[model._meta.pk.attname]) for row in rows] if len(rows) <= CAP else [],
                    "raw_record_sha256": _digest(rows) if len(rows) <= CAP else "",
                }
            )
    maps = list(
        apps.get_model("legacy_import.LegacyEntityMap")
        .objects.filter(organization_id=ORG, target_model_label="auth.user", target_pk__in=[str(v) for v in TEACHERS])
        .order_by("pk")
        .values(
            "id",
            "organization_id",
            "source_system",
            "entity_type",
            "legacy_pk",
            "target_model_label",
            "target_pk",
            "state",
            "source_row_hash",
            "created_at",
            "updated_at",
        )[: CAP + 1]
    )
    return {
        "jale_account_reference_inventory": sorted(result, key=lambda r: (r["model"], r["field"], r["user_id"])),
        "jale_account_typed_legacy_maps": maps if len(maps) <= CAP else [],
        "jale_account_inventory_limits": [{"eligible_for_merge": False, "typed_maps_truncated": len(maps) > CAP}],
    }
