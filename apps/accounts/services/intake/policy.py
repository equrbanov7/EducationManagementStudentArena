"""Tələbə idxalı — İCAZƏ QAPISI (`user.import`).

Fail-closed: aktiv təşkilat konteksti + AKTİV üzvlükdən həll olunan açar
(MEMORY «role needs active membership»). Superadmin və təşkilat sahibi
istisnadır. Rol ADINA baxılmır — açar permission-editordan istənilən rola
verilə bilər.

Bu qapı `core/management/command_safety.py`-dakı prod kill-switch-i ƏVƏZ ETMİR:
`import_users_from_excel` management komandası prod-da BAĞLI qalır; nəzarətli
səth məhz bu icazəli UI-dır (hər sətir audit olunur, aktor məlumdur).
"""

from __future__ import annotations

from core.permissions import has_permission, is_superadmin_user

#: Kanonik açar (bax `apps/organizations/permissions.py` «users» kateqoriyası).
PERM_IMPORT = "user.import"


class IntakeAccessError(Exception):
    """İdxal əməliyyatı icazə qapısından keçmədi."""

    def __init__(self, reason_code: str, message: str, status: int = 403):
        super().__init__(reason_code, message, status)
        self.reason_code = reason_code
        self.message = message
        self.status = status

    def __str__(self):
        return self.reason_code


def _is_owner(user, organization) -> bool:
    return bool(organization is not None and getattr(organization, "owner_id", None) == getattr(user, "pk", None))


def can_import(user, organization) -> bool:
    """Aktorun bu təşkilatda tələbə idxalı səlahiyyəti varmı."""

    if user is None or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    if is_superadmin_user(user):
        return True
    if organization is None or not getattr(organization, "pk", None):
        return False
    if _is_owner(user, organization):
        return True

    from apps.organizations.models import Membership

    memberships = Membership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        role__is_active=True,
    ).select_related("role")
    permissions: set = set()
    for membership in memberships:
        for permission in membership.role.permissions or []:
            # `grant:<perm>` delegasiya prefiksidir — icazəni AKTİV ETMİR.
            if not str(permission).startswith("grant:"):
                permissions.add(permission)
    return has_permission(list(permissions), PERM_IMPORT)


def require_import(user, organization) -> None:
    """İcazə yoxdursa ``IntakeAccessError``."""

    if not can_import(user, organization):
        raise IntakeAccessError(
            "permission_denied",
            "Tələbə idxalı üçün icazəniz yoxdur.",
        )


__all__ = ["PERM_IMPORT", "IntakeAccessError", "can_import", "require_import"]
