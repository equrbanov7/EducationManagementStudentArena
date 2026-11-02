"""Fixed, reviewed Jalə identity consolidation; never rewrite academic authorship."""

import hashlib
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Q

from core.audit import log_action
from core.constants import AuditAction

from .account_deletion import soft_delete_account
from .duplicate_accounts.apply import _give_role, _handover

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
CANONICAL = 7730
ALIAS = 8388
ACTOR = 8444
CAP = 2000
RESOURCE = "accounts.reviewed_jale_merge"
# Only these current functional relations may move. Collisions are holds.
MOVE = {
    ("registrar.JournalShare", "teacher_id"),
    ("workload.TeacherAssignment", "teacher_id"),
    ("workload.TeacherWorkloadProfile", "teacher_id"),
    ("organizations.OrgUnit", "head_id"),
    ("notifications.InAppNotification", "recipient_id"),
}
# Existing historical actors remain real identities, including the worker949 bridge.
HISTORICAL_FIELDS = {
    "created_by_id",
    "updated_by_id",
    "assigned_by_id",
    "performed_by_id",
    "reverted_by_id",
    "approved_by_id",
    "reviewed_by_id",
    "submitted_by_id",
    "entered_by_id",
    "deleted_by_id",
    "blocked_by_id",
    "resolved_by_id",
    "author_id",
    "from_instructor_id",
    "to_instructor_id",
}
HISTORY = {
    ("registrar.Lesson", "instructor_id"),
    ("audit.AuditLog", "user_id"),
}


class MergeError(ValueError):
    """Stable reason, without private row contents."""


def digest(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def require(ok, code):
    if not ok:
        raise MergeError(code)


def _rows(query):
    rows = list(query.order_by("pk").values()[: CAP + 1])
    require(len(rows) <= CAP, "jale_merge_reference_cap")
    return rows


def _policy(label, field):
    if (label, field) in MOVE:
        return "move"
    if (label, field) == ("organizations.Membership", "user_id"):
        return "membership"
    if (label, field) == ("registrar.CourseOffering", "instructor_id"):
        return "handover"
    if (label, field) in HISTORY or field in HISTORICAL_FIELDS:
        return "historical"
    if (label, field) == ("accounts.UserProfile", "user_id"):
        return "profile"
    return "hold"


def _collision(model, field, row):
    canonical = model._base_manager.filter(**{field: CANONICAL})
    if model._meta.label == "registrar.JournalShare":
        return row["is_active"] and canonical.filter(offering_id=row["offering_id"], is_active=True).exists()
    if model._meta.label == "workload.TeacherAssignment":
        return canonical.filter(row_id=row["row_id"], activity=row["activity"]).exists()
    if model._meta.label == "workload.TeacherWorkloadProfile":
        return canonical.filter(organization_id=row["organization_id"], academic_year=row["academic_year"]).exists()
    return False


def snapshot(organization, actor):
    require(connection.vendor == "postgresql", "jale_merge_postgresql_required")
    require(
        str(organization.pk) == ORG and actor.pk == ACTOR and actor.is_superuser and actor.is_active,
        "jale_merge_actor_scope",
    )
    require(organization.is_active and organization.status == "active", "jale_merge_active_tenant_required")
    require(
        get_user_model()
        .objects.filter(pk=ACTOR, is_active=True, is_superuser=True)
        .filter(Q(profile__organization_id=ORG) | Q(memberships__organization_id=ORG, memberships__is_active=True))
        .exists(),
        "jale_merge_actor_tenant",
    )
    users = get_user_model().objects.select_for_update().filter(pk__in=[ALIAS, CANONICAL]).in_bulk()
    require(len(users) == 2 and users[CANONICAL].is_active, "jale_merge_identity_missing")
    for user in users.values():
        require(str(user.profile.organization_id) == ORG, "jale_merge_profile_tenant")
    require(users[ALIAS].is_active and not users[ALIAS].profile.is_deleted, "jale_merge_alias_not_active")
    # Same-person authorization is external; pin both exact live identity rows opaquely.
    identities = list(
        get_user_model()
        .objects.filter(pk__in=users)
        .order_by("pk")
        .values("id", "username", "first_name", "last_name", "is_active", "is_staff", "is_superuser")
    )
    require(not users[ALIAS].is_superuser and not users[ALIAS].is_staff, "jale_merge_elevated_alias")
    refs, actions, holds = [], [], []
    seen = set()
    for relation in get_user_model()._meta.get_fields(include_hidden=True):
        if not relation.auto_created or relation.concrete or relation.related_model is None:
            continue
        model, field = relation.related_model, relation.field.attname
        key = (model._meta.label, field)
        if key in seen:
            continue
        seen.add(key)
        rows = _rows(model._base_manager.select_for_update().filter(**{field: ALIAS}))
        if not rows:
            continue
        policy = _policy(*key)
        has_org = any(f.name == "organization" for f in model._meta.concrete_fields)
        if has_org and any(str(row["organization_id"]) != ORG for row in rows):
            holds.append({"model": key[0], "field": field, "reason": "other_tenant"})
        elif not has_org and policy not in {"profile", "historical"}:
            holds.append({"model": key[0], "field": field, "reason": "unscoped_reference"})
        elif policy == "hold":
            holds.append({"model": key[0], "field": field, "reason": "unknown_relation"})
        elif policy == "move" and any(_collision(model, field, row) for row in rows):
            holds.append({"model": key[0], "field": field, "reason": "canonical_collision"})
        elif policy in {"move", "membership", "handover"}:
            actions.append(
                {
                    "model": key[0],
                    "field": field,
                    "policy": policy,
                    "ids": [str(row[model._meta.pk.attname]) for row in rows],
                }
            )
        refs.append({"model": key[0], "field": field, "policy": policy, "count": len(rows), "sha256": digest(rows)})
    maps = _rows(
        apps.get_model("legacy_import.LegacyEntityMap").objects.filter(
            organization=organization, target_model_label="auth.user", target_pk=str(ALIAS)
        )
    )
    require(
        any(row["entity_type"] == "worker" and row["legacy_pk"] == "949" for row in maps),
        "jale_merge_worker949_missing",
    )
    body = {
        "organization": ORG,
        "canonical": CANONICAL,
        "alias": ALIAS,
        "identity_sha256": digest(identities),
        "references": sorted(refs, key=lambda r: (r["model"], r["field"])),
        "legacy_maps_sha256": digest(maps),
        "actions": actions,
        "holds": holds,
    }
    return {**body, "baseline_sha256": digest(body), "eligible": not holds}


@transaction.atomic
def execute(organization, actor, baseline_sha256, reason):
    require(len(reason.strip()) >= 20, "jale_merge_reason_required")
    state = snapshot(organization, actor)
    require(state["baseline_sha256"] == baseline_sha256, "jale_merge_stale_baseline")
    require(state["eligible"], "jale_merge_unreviewed_reference")
    users = get_user_model().objects.select_related("profile").in_bulk([ALIAS, CANONICAL])
    alias, canonical = users[ALIAS], users[CANONICAL]
    changed = []
    for action in state["actions"]:
        model = apps.get_model(action["model"])
        rows = model._base_manager.filter(pk__in=action["ids"], **{action["field"]: ALIAS})
        if action["policy"] == "membership":
            for membership in rows.select_related("role"):
                if membership.is_active:
                    _give_role(
                        organization,
                        canonical,
                        {
                            "role_id": membership.role_id,
                            "unit": membership.scope_unit_id,
                            "title": membership.title,
                            "role": membership.role.name,
                        },
                        actor=actor,
                        note=reason,
                    )
        elif action["policy"] == "handover":
            _handover(organization, action["ids"], alias, canonical, actor=actor, note=reason)
        else:
            before = _rows(rows)
            rows.update(**{action["field"]: CANONICAL})
            changed.append(
                {
                    **action,
                    "before": before,
                    "after_sha256": digest(_rows(model._base_manager.filter(pk__in=action["ids"]))),
                }
            )
    # No cascade may erase student links, notifications or pending requests: any
    # such reference was an unknown hold in the exhaustive snapshot above.
    soft_delete_account(alias, actor=actor, reason=reason)
    # Verify all preserved historical rows and typed worker mapping byte-for-byte.
    for ref in state["references"]:
        if ref["policy"] == "historical":
            rows = _rows(apps.get_model(ref["model"])._base_manager.filter(**{ref["field"]: ALIAS}))
            require(digest(rows) == ref["sha256"], "jale_merge_history_changed")
    maps = _rows(
        apps.get_model("legacy_import.LegacyEntityMap").objects.filter(
            organization=organization, target_model_label="auth.user", target_pk=str(ALIAS)
        )
    )
    require(digest(maps) == state["legacy_maps_sha256"], "jale_merge_worker_bridge_changed")
    receipt = {
        "baseline": state,
        "changed": changed,
        "soft_deleted_alias": ALIAS,
        "canonical": CANONICAL,
        "historical_identity_retained": True,
    }
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=json.loads(json.dumps(receipt, default=str)),
        reason=reason,
        resource_type=RESOURCE,
        resource_id=str(ALIAS),
        resource_repr="Reviewed Jalə canonical identity",
    )
    return {
        "canonical": CANONICAL,
        "soft_deleted_alias": ALIAS,
        "moved_relations": len(changed),
        "baseline_sha256": baseline_sha256,
    }
