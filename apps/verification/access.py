"""Kim «Sənəd yoxlaması» səhifəsini görür və kim ləğv edir (FAIL-CLOSED).

* Açar: ``document_seal.manage`` (kataloq: ``organizations/permissions_document_seal.py``).
* Əhatə ``get_permission_scope`` ilə: ORGANIZATION rolu / sahib / superadmin → bütün təşkilat;
  UNIT rolu → yalnız ``DocumentSeal.scope_path`` öz alt-ağacında olan möhürlər; açarsız → heç nə.
* Açar yoxdursa səhifə **403**; açar var, amma möhür əhatədən kənardadırsa **404** (mövcudluq sızmır).
* «Başqasının adından» (view-as) rejimində siyahı oxunur, ləğv BAĞLIDIR.
"""

from __future__ import annotations

from django.db.models import Q

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, get_permission_scope
from core.permissions import is_superadmin_user

from .models import DocumentSeal

PERM_MANAGE = "document_seal.manage"


def manage_scope(user, organization, request=None):
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return EMPTY_SCOPE
    if is_superadmin_user(user):
        return ORG_WIDE_SCOPE
    return get_permission_scope(user, organization, PERM_MANAGE, request=request)


def can_manage(user, organization, request=None) -> bool:
    return manage_scope(user, organization, request=request).has_structure_access


def is_read_only(request) -> bool:
    return bool(getattr(request, "is_view_as", False))


def scoped_seals(scope, organization):
    """Aktorun görə bildiyi möhürlər (təşkilat süzgəci + struktur əhatəsi)."""
    base = DocumentSeal.objects.filter(organization=organization)
    if scope.is_org_wide:
        return base
    if not scope.is_unit_scoped or not scope.unit_paths:
        return base.none()
    condition = Q()
    for root in scope.unit_paths:
        if root:
            condition |= Q(scope_path=root) | Q(scope_path__startswith=f"{root}/")
    return base.filter(condition) if condition else base.none()


__all__ = ["PERM_MANAGE", "can_manage", "is_read_only", "manage_scope", "scoped_seals"]
