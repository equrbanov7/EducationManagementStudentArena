"""RİM: fix one mistaken lab affiliation via role-assignment authority (API ``move_staff_scope``).

2026-11-04: the detail card no longer renders a lab-only block — «Vəzifə və bölmə» (``placement.py``) places every
teacher / unit-scoped staff membership, lab assistants included. This endpoint stays for API compatibility.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.public import log_action
from apps.organizations.models import Membership, OrgUnit
from apps.organizations.public import correct_membership_unit, kafedra_q, membership_assignment_scope
from core.constants import AuditAction

from .lifecycle import normalize_reason
from .policy import PERM_EDIT, RimAccessError, assert_can_manage, require_permission


def units_for(actor):
    """Only authorized destinations; personal editing alone never grants scope."""
    units = OrgUnit.objects.none()
    if (
        actor.organization is None
        or not actor.has(PERM_EDIT)
        or not (actor.is_superadmin or actor.has("role.assign") or actor.has("org.manage_members"))
    ):
        return units
    units = OrgUnit.objects.filter(kafedra_q(), organization=actor.organization, is_active=True)
    if actor.is_superadmin:
        return units
    scope = membership_assignment_scope(actor.user, actor.organization)
    if not scope.has_structure_access:
        return units.none()
    return units if scope.is_org_wide else units.filter(scope.unit_subtree_q())


@transaction.atomic
def move(actor, target, *, membership_id, unit_id, expected_unit_id, reason, request=None):
    require_permission(actor, PERM_EDIT)
    assert_can_manage(actor, target)
    reason = normalize_reason(reason)
    try:
        source = (
            Membership.objects.select_related("user", "role", "scope_unit")
            .filter(
                pk=membership_id,
                organization=actor.organization,
                user=target,
                role__organization=actor.organization,
                role__is_active=True,
                role__name="lab_assistant",
            )
            .first()
        )
        unit = units_for(actor).filter(pk=unit_id).first()
    except (ValidationError, ValueError, TypeError):
        source, unit = None, None
    if source is None or unit is None or source.scope_unit_id not in set(units_for(actor).values_list("pk", flat=True)):
        raise RimAccessError("staff_scope_not_found", "Təyinat və ya kafedra idarə sahənizdə deyil.", status=404)
    previous = str(source.scope_unit_id)
    previous_state = {
        "scope_unit_id": previous,
        "membership_id": str(source.pk),
        "is_active": source.is_active,
        "is_primary": source.is_primary,
    }
    try:
        result, changed, archived = correct_membership_unit(
            membership=source, unit=unit, expected_unit_id=expected_unit_id
        )
    except ValidationError:
        raise RimAccessError("staff_scope_stale", "Təyinat dəyişib. Kartı yenidən açın.", status=409) from None
    if changed:
        log_action(
            AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=result,
            request=request,
            reason=reason,
            old_values=previous_state,
            new_values={
                "scope_unit_id": str(unit.pk),
                "membership_id": str(result.pk),
                "is_active": result.is_active,
                "is_primary": result.is_primary,
            },
            changes={
                "action": "rim.staff_scope_corrected",
                "source_membership": str(source.pk),
                "archived_membership": str(archived) if archived else None,
            },
        )
    return {"membership_id": str(result.pk), "changed": changed}
