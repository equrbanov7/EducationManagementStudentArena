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
#: Müəllim / heyət hesabları — AYRI açar (rol auditi 2026-10-13 B3). Əvvəl müəllim idxalı da `user.import`-dan
#: keçirdi və tələbə qəbulu üçün açarı alan Tələbə xidmətləri toplu MÜƏLLİM hesabı yarada bilirdi.
PERM_IMPORT_STAFF = "user.import_staff"


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


def can_import(user, organization, permission: str = PERM_IMPORT) -> bool:
    """Aktorun bu təşkilatda idxal səlahiyyəti varmı (default: TƏLƏBƏ — ``user.import``)."""

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
        for key in membership.role.permissions or []:
            # `grant:<perm>` delegasiya prefiksidir — icazəni AKTİV ETMİR.
            if not str(key).startswith("grant:"):
                permissions.add(key)
    return has_permission(list(permissions), permission)


def can_import_staff(user, organization) -> bool:
    """Müəllim / heyət hesablarının yaradılması — ``user.import_staff`` (B3, 2026-10-13)."""

    return can_import(user, organization, PERM_IMPORT_STAFF)


def require_import(user, organization) -> None:
    """İcazə yoxdursa ``IntakeAccessError``."""

    if not can_import(user, organization):
        raise IntakeAccessError(
            "permission_denied",
            "Toplu tələbə əlavəsi üçün icazəniz yoxdur.",
        )


__all__ = ["PERM_IMPORT", "PERM_IMPORT_STAFF", "IntakeAccessError", "can_import", "can_import_staff", "require_import"]
