"""Yalnız legacy388→367: sübut edilmiş, tam boş132 F dublikatı.

Legacy source: eyni specialty21/curricula117/cohort2022/department11,
bachelor/full_time/az;388 tələbəsizdir,367 tarixi tələbələri saxlayır.
Başqa oxşar adlar bu əməliyyatın icazə sahəsinə daxil deyil.
"""

import hashlib
import json
import uuid

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SOURCE = "6edca0eb-0ad6-4c2d-aa5e-83cbec3e69d1"
TARGET = "86a79572-7de8-45d0-a800-bec9d918d58e"
PARENT = "2dd89119-36e4-4d52-b023-2fb3b3141d95"
RESOURCE = "organizations.empty_132f_alias"
SETTINGS = {"degree_level": "bachelor", "education_form": "full_time", "sector": "az"}


class RepairError(ValueError):
    pass


def _json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def references(unit):
    """Bütün FK/one-to-one və gizli avtomatik M2M through-ları, filtrsiz base manager."""
    found = {}
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.local_fields:
            if not field.is_relation or field.remote_field.model != type(unit):
                continue
            ids = list(
                model._base_manager.filter(**{field.attname: unit.pk}).order_by("pk").values_list("pk", flat=True)
            )
            if ids:
                found[f"{model._meta.label}.{field.name}"] = [str(pk) for pk in ids]
    return found


def _snapshot(unit):
    return _json({field.attname: getattr(unit, field.attname) for field in unit._meta.concrete_fields})


def _settings_identity(settings, legacy):
    """Pin reviewed identity fields; unrelated metadata stays in the full snapshot."""
    if not isinstance(settings, dict) or settings.get("parent_group"):
        return False
    expected = {**SETTINGS, "admission_year": 2022, "language_sector": "az"}
    embedded = settings.get("legacy")
    legacy_expected = {
        "id": int(legacy),
        "table": "groups",
        "curricula_id": 117,
        "department_id": 11,
        "kollec_or_uni": "University",
        "source_system": "myedu_mariadb",
        "speciality_id": 21,
    }
    return (
        all(settings.get(key) == value for key, value in expected.items())
        and isinstance(embedded, dict)
        and all(embedded.get(key) == value for key, value in legacy_expected.items())
    )


def _identity(source, target):
    for unit, name, legacy in ((source, "132 F", "388"), (target, "132F", "367")):
        if (
            str(unit.organization_id) != ORG
            or str(unit.parent_id) != PARENT
            or unit.unit_type != "group"
            or unit.name != name
            or unit.code
            or unit.is_service_unit
        ):
            raise RepairError("identity_changed")
        mapping = apps.get_model("legacy_import", "LegacyEntityMap")
        identities = list(
            mapping._base_manager.filter(target_model_label="organizations.orgunit", target_pk=str(unit.pk))
            .order_by("pk")
            .values_list("organization_id", "source_system", "entity_type", "legacy_pk")
        )
        if [(str(org), system, kind, pk) for org, system, kind, pk in identities] != [
            (ORG, "myedu_mariadb", "group_unit", legacy)
        ]:
            raise RepairError("legacy_identity_changed")
    if (
        not _settings_identity(target.settings, "367")
        or not target.is_active
        or target.settings.get("canonical_group") is not None
    ):
        raise RepairError("target_changed")
    if not _settings_identity(source.settings, "388") or source.settings.get("canonical_group") not in (None, TARGET):
        raise RepairError("source_settings_changed")
    if source.is_active != (source.settings.get("canonical_group") is None):
        raise RepairError("source_state_changed")


@transaction.atomic
def run(*, user, organization, apply=False, expected_baseline="", undo=""):
    """Dry-run defoltdur; apply exact baseline tələb edir, undo audit snapshot-ını qaytarır."""
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise RepairError("active_tenant_superadmin_required")
    if apply and connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    unit_model = apps.get_model("organizations", "OrgUnit")
    units = {
        str(unit.pk): unit
        for unit in unit_model._base_manager.select_for_update().filter(organization_id=ORG, pk__in=(SOURCE, TARGET))
    }
    if set(units) != {SOURCE, TARGET}:
        raise RepairError("exact_pair_missing")
    source, target = units[SOURCE], units[TARGET]
    _identity(source, target)
    refs = references(source)
    before = {"source": _snapshot(source), "target": _snapshot(target), "references": refs}
    baseline = _digest(before)
    result = {"baseline": baseline, "snapshot": before, "blocked": bool(refs)}
    if not apply:
        return result
    if not expected_baseline or baseline != expected_baseline:
        raise RepairError("baseline_changed")
    if refs:
        raise RepairError("source_has_references")
    audit_model = apps.get_model("audit", "AuditLog")
    if undo:
        receipt = audit_model._base_manager.filter(
            organization_id=ORG, resource_type=RESOURCE, resource_id=undo
        ).first()
        if receipt is None or (receipt.new_values or {}).get("operation") != "apply":
            raise RepairError("apply_receipt_missing")
        if (receipt.new_values or {}).get("snapshot") != before:
            raise RepairError("undo_state_changed")
        prior = (receipt.old_values or {}).get("source", {})
        prior_settings = prior.get("settings")
        if (
            not _settings_identity(prior_settings, "388")
            or prior_settings.get("canonical_group") is not None
            or prior.get("is_active") is not True
            or {**prior, "is_active": False, "settings": {**prior_settings, "canonical_group": TARGET}}
            != before["source"]
        ):
            raise RepairError("undo_snapshot_invalid")
        settings, active = prior["settings"], True
    else:
        if not source.is_active:
            raise RepairError("already_applied")
        settings, active = {**source.settings, "canonical_group": TARGET}, False
    unit_model._base_manager.filter(pk=source.pk).update(settings=settings, is_active=active)
    source.refresh_from_db()
    after = {"source": _snapshot(source), "target": _snapshot(target), "references": references(source)}
    if after["references"] or after["target"] != before["target"]:
        raise RepairError("preservation_failed")
    batch = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=batch,
        reason="reviewed_legacy388_367_empty_group_alias",
        old_values=before,
        new_values={"operation": "undo" if undo else "apply", "snapshot": after, "undo_of": undo},
    )
    return {"batch": batch, "baseline": _digest(after), "snapshot": after, "blocked": False}
