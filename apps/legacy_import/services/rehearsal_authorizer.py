"""Ledger authorizer and target validators bound to the platform's RBAC.

Models are resolved through ``django.apps`` rather than deep imports so the
module-boundary graph gains no new edge for the rehearsal orchestrator.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from django.apps import apps as django_apps

from core.permissions import has_permission, is_superadmin_user

from .ledger import LedgerAction, LedgerAuthorizer, TargetValidation, TargetValidator, TargetValidatorRegistry

LEDGER_PERMISSION = "member.invite"  # the gate identity_access._assert_tenant_permission uses
# Every label is lower-case app_label.model_name so it satisfies
# ``models.MODEL_LABEL_PATTERN``; the ledger stores the label verbatim.
USER_MODEL_LABEL = "auth.user"  # settings.AUTH_USER_MODEL default; matches MODEL_LABEL_PATTERN
ORG_UNIT_MODEL_LABEL = "organizations.orgunit"
PROGRAM_MODEL_LABEL = "registrar.program"


def build_rehearsal_authorizer() -> LedgerAuthorizer:
    """Return a strict True/False authorizer for every ledger write."""

    def authorize(*, actor: Any, organization: Any, action: LedgerAction) -> bool:
        if not isinstance(action, LedgerAction):
            return False
        if organization is None or getattr(organization, "pk", None) is None:
            return False
        if not getattr(actor, "is_active", False) or getattr(actor, "pk", None) is None:
            return False
        if is_superadmin_user(actor):
            return True
        membership_model = django_apps.get_model("organizations", "Membership")
        permissions = {
            item
            for membership in membership_model.objects.filter(
                user=actor,
                organization=organization,
                is_active=True,
                role__is_active=True,
            ).select_related("role")
            for item in (membership.role.permissions or [])
        }
        return has_permission(list(permissions), LEDGER_PERMISSION)

    return authorize


def _tenant_owned_validator(app_label: str, model_name: str) -> TargetValidator:
    """Validator for a target that carries its own ``organization`` column.

    A malformed primary key makes ``.filter()`` raise, which
    ``ledger._target_validation`` converts into ``legacy_target_validation_failed``
    — fail closed by design, never a silent "not found".
    """

    def validate(*, target_pk: str, organization: Any) -> TargetValidation:
        model = django_apps.get_model(app_label, model_name)
        row = model._default_manager.filter(pk=target_pk).values("organization_id").first()
        return TargetValidation(
            exists=row is not None,
            organization_matches=row is not None and str(row["organization_id"]) == str(organization.pk),
        )

    return validate


def build_target_validators() -> TargetValidatorRegistry:
    """Return the allowlisted target models and their tenant validators."""

    def validate_user(*, target_pk: str, organization: Any) -> TargetValidation:
        user_model = django_apps.get_model("auth", "User")
        profile_model = django_apps.get_model("accounts", "UserProfile")
        membership_model = django_apps.get_model("organizations", "Membership")
        exists = user_model._default_manager.filter(pk=target_pk).exists()
        owned = (
            profile_model.objects.filter(user_id=target_pk, organization=organization).exists()
            or membership_model.objects.filter(user_id=target_pk, organization=organization).exists()
        )
        return TargetValidation(exists=exists, organization_matches=owned)

    return MappingProxyType(
        {
            USER_MODEL_LABEL: validate_user,
            ORG_UNIT_MODEL_LABEL: _tenant_owned_validator("organizations", "OrgUnit"),
            PROGRAM_MODEL_LABEL: _tenant_owned_validator("registrar", "Program"),
        }
    )
