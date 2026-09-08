"""«Struktur üzvləri» kabinet reyestri — «Üzv kartı» çekmecəsinin JSON endpoint-i (2026-09-08).

``structure_member_detail`` (GET) şəxsin bu təşkilatdakı rollarını, rəhbərlik
etdiyi bölmələri və əlaqə məlumatını qaytarır; `org_members.js` onu DOM ilə
render edir (innerHTML-ə istifadəçi mətni yazılmır).

QAPI (fail-closed) — reyestr bölməsi ilə EYNİ (`resolve_members_access`):
  * giriş yoxdursa → 403;
  * şəxs aktorun GÖRDÜYÜ üzvlüklər arasında deyilsə → 404 (başqa fakültənin
    adamı dekanın çekmecəsində açılmır);
  * bölməyə bağlı aktor şəxsin yalnız öz alt-ağacındakı və əhatəsiz
    (org-səviyyəli) rollarını görür — başqa fakültəyə bağlı rol sətirləri sızmır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.constants import RoleScopeType

from .models import Membership, Organization
from .structure_views.members import (
    UnitIndex,
    format_date,
    is_leader_role,
    resolve_members_access,
    role_label,
)
from .structure_views.registry import _display_name, _initials, unit_type_label

_CTX = "organizations.members"


def _error(message, *, status, code):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


def _membership_row(membership, index):
    scope_unit = membership.scope_unit
    scope_missing = scope_unit is None and membership.role.scope_type == RoleScopeType.UNIT
    return {
        "id": str(membership.id),
        "role": membership.role.name,
        "role_label": role_label(membership.role),
        "is_leader": is_leader_role(membership.role),
        "title": membership.title or "",
        "employee_id": membership.employee_id or "",
        "is_primary": bool(membership.is_primary),
        "scope_unit": scope_unit.name if scope_unit is not None else "",
        "scope_type_label": unit_type_label(scope_unit.unit_type) if scope_unit is not None else "",
        "scope_trail": " · ".join(index.trail(scope_unit.id)) if scope_unit is not None else "",
        "scope_missing": scope_missing,
        "scope_all": scope_unit is None and not scope_missing,
        "since": format_date(membership.created_at),
    }


@login_required
@require_GET
def structure_member_detail(request, slug, user_id):
    """Şəxsin rolları, rəhbərlik etdiyi bölmələr və əlaqə — «Üzv kartı» (JSON)."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    access = resolve_members_access(request, organization)
    if not access.has_access:
        return _error(pgettext(_CTX, "Üzv siyahısına baxış səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    visible_ids = list(access.memberships.filter(user_id=user_id).order_by().values_list("pk", flat=True))
    if not visible_ids:
        return _error(pgettext(_CTX, "Üzv tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")

    memberships_qs = Membership.objects.filter(organization=organization, user_id=user_id, is_active=True)
    if not access.is_org_wide:
        memberships_qs = memberships_qs.filter(Q(pk__in=visible_ids) | Q(scope_unit__isnull=True))
    memberships = list(
        memberships_qs.select_related("user", "role", "scope_unit").order_by("-role__level", "created_at", "pk")
    )
    user = memberships[0].user
    name = _display_name(user)

    unit_ids = None if access.is_org_wide else set(access.units.order_by().values_list("id", flat=True))
    index = UnitIndex(organization, unit_ids)
    headed = index.head_lines(user.id)
    rows = [_membership_row(membership, index) for membership in memberships]

    return JsonResponse(
        {
            "ok": True,
            "person": {
                "id": user.id,
                "name": name,
                "initials": _initials(name),
                "username": user.username,
                "email": user.email or "",
                "is_active": bool(user.is_active),
                "is_leader": bool(headed) or any(row["is_leader"] for row in rows),
                "joined": format_date(min(m.created_at for m in memberships if m.created_at)) if memberships else "",
                "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
            },
            "memberships": rows,
            "headed_units": headed,
        }
    )


__all__ = ["structure_member_detail"]
