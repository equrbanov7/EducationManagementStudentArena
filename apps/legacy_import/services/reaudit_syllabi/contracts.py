"""Fixed audit scope and private source packet contracts; no database writes."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from ..exact_syllabus_recovery import RestoreError, digest, model

ROOT = Path(__file__).parent
SCOPE = json.loads((ROOT / "scope.json").read_bytes())
RESOURCE = "legacy_import.reaudit_syllabi_20261109"
KINDS = ("lecture", "seminar", "practical", "lab")


def source_packet(path="", expected=""):
    if not path:
        if expected:
            raise RestoreError("source_packet_required")
        return {"sources": {}, "bindings": {}, "sha256": None}
    raw = Path(path).read_bytes()
    if not expected or len(raw) > 20_000_000 or hashlib.sha256(raw).hexdigest() != expected:
        raise RestoreError("reviewed_source_packet_digest_required")
    try:
        value = json.loads(raw)
        if set(value) != {"format", "organization_id", "period_id", "sources", "bindings"} or (
            value["format"] != "reaudit-syllabi-source/1"
            or value["organization_id"] != SCOPE["organization_id"]
            or value["period_id"] != SCOPE["period_id"]
            or not isinstance(value["sources"], dict)
            or not isinstance(value["bindings"], dict)
            or not set(value["bindings"]) <= set(SCOPE.get("allowed_offering_ids", SCOPE["offering_ids"]))
        ):
            raise RestoreError("reviewed_source_packet_scope")
        value["sha256"] = expected
        return value
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, RestoreError):
            raise
        raise RestoreError("reviewed_source_packet_shape") from None


def hours(value):
    if not isinstance(value, dict) or set(value) - set(KINDS):
        raise RestoreError("official_hours_unknown")
    result = {}
    for kind in KINDS:
        number = value.get(kind, 0)
        try:
            parsed = int(number)
        except (TypeError, ValueError, OverflowError):
            raise RestoreError("official_hours_invalid") from None
        if isinstance(number, bool) or str(number) != str(parsed) or not 0 <= parsed <= 1000:
            raise RestoreError("official_hours_invalid")
        result[kind] = parsed
    if not sum(result.values()):
        raise RestoreError("official_hours_unknown")
    return result


def nonblank(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(nonblank(item) for item in value.values())
    if isinstance(value, list):
        return any(nonblank(item) for item in value)
    return False


def fill_empty(existing, source):
    """Keep every authored leaf/list; never align or replace partial topic rows."""
    if not nonblank(existing) and isinstance(existing, (str, list)):
        return deepcopy(source)
    if isinstance(existing, dict) and isinstance(source, dict):
        return {
            key: fill_empty(value, source[key]) if key in source else deepcopy(value) for key, value in existing.items()
        } | {key: deepcopy(value) for key, value in source.items() if key not in existing}
    if existing is None:
        return deepcopy(source)
    return deepcopy(existing)


def actor_scope(org, actor):
    profile = (
        model("accounts.UserProfile")
        .objects.filter(
            user=actor, access_state="active", is_deleted=False, blocked_at__isnull=True, deleted_at__isnull=True
        )
        .first()
    )
    affiliated = bool(
        profile
        and (
            profile.organization_id == org.pk
            or org.owner_id == actor.pk
            or model("organizations.Membership").objects.filter(organization=org, user=actor, is_active=True).exists()
        )
    )
    if (
        str(org.pk) != SCOPE["organization_id"]
        or not org.is_active
        or org.status != "active"
        or (not actor.is_active or not actor.is_superuser or not affiliated)
    ):
        raise RestoreError("active_fixed_tenant_operator_required")


def selected_ids(values):
    result = tuple(sorted(set(map(str, values or SCOPE["offering_ids"]))))
    if not result or not set(result) <= set(SCOPE.get("allowed_offering_ids", SCOPE["offering_ids"])):
        raise RestoreError("fixed_audit_offering_scope_required")
    return result


__all__ = [
    "KINDS",
    "RESOURCE",
    "SCOPE",
    "RestoreError",
    "actor_scope",
    "digest",
    "fill_empty",
    "hours",
    "model",
    "nonblank",
    "selected_ids",
    "source_packet",
]
