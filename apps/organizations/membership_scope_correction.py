"""Auditable correction of one existing staff affiliation; never a role grant."""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Membership
from .scoping import get_permission_scope, invalidate_permission_scope_cache


def membership_assignment_scope(user, organization):
    """Same permission-scoped gate as the canonical role-assignment screen."""
    scope = get_permission_scope(user, organization, "role.assign")
    if not scope.has_structure_access:
        scope = get_permission_scope(user, organization, "org.manage_members")
    return scope


@transaction.atomic
def correct_membership_unit(*, membership, unit, expected_unit_id):
    """Caller authorizes actor, role and both scopes before this bounded write.

    Keep the source PK as inactive history on a unique-key collision. Otherwise
    keep its PK and all non-scope fields. This never copies another role or user.
    """
    # Serialize competing corrections for this same person, including two
    # different source memberships converging onto the same unique target key.
    type(membership.user).objects.select_for_update().get(pk=membership.user_id)
    source = Membership.objects.select_for_update().get(pk=membership.pk)
    if (source.user_id, source.role_id, source.organization_id) != (
        membership.user_id,
        membership.role_id,
        membership.organization_id,
    ):
        raise ValidationError("membership_scope_stale")
    if source.organization_id != unit.organization_id:
        raise ValidationError("membership_scope_cross_tenant")
    if source.scope_unit_id == unit.pk and source.is_active:
        return source, False, None
    if str(source.scope_unit_id or "") != str(expected_unit_id or ""):
        raise ValidationError("membership_scope_stale")
    target = (
        Membership.objects.select_for_update()
        .filter(organization_id=source.organization_id, user_id=source.user_id, role_id=source.role_id, scope_unit=unit)
        .first()
    )
    if not source.is_active:
        if target is not None and target.is_active:
            return target, False, None
        raise ValidationError("membership_scope_stale")
    if target is None:
        source.scope_unit = unit
        source.save(update_fields=["scope_unit", "updated_at"])
        result, archived = source, None
    else:
        target.is_active = True
        # Keep a unique primary designation without affecting other roles.
        target.is_primary = target.is_primary or source.is_primary
        target.save(update_fields=["is_active", "is_primary", "updated_at"])
        source.is_active = False
        source.is_primary = False
        source.save(update_fields=["is_active", "is_primary", "updated_at"])
        result, archived = target, source.pk
    invalidate_permission_scope_cache(membership.user)
    return result, True, archived
