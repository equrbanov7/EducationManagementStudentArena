"""Kim elan idarə edir və hansı auditoriyaya ünvanlaya bilər (FAIL-CLOSED).

* ``announcement.manage`` əhatəsi ``organizations.scoping.get_permission_scope``-dan gəlir:
  ORGANIZATION rolu / sahib / superadmin → bütün təşkilat; UNIT rolu (dekan, kafedra
  müdiri) → yalnız ``scope_unit`` alt-ağacı; açarsız → heç nə.
* Əhatəli (unit) menecer YALNIZ öz alt-ağacındakı bölmələri hədəfləyə bilər və boş
  (bütün təşkilat) auditoriya seçə BİLMƏZ — server tərəfdə ``validate_units`` yoxlayır,
  formaya heç vaxt etibar edilmir.
* Siyahı/redaktə: org-wide menecer hamısını; unit menecer öz yazdığını VƏ ya bütün hədəf
  bölmələri öz əhatəsində olanları görür.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, get_permission_scope
from core.permissions import is_superadmin_user

from ..constants import PERM_MANAGE


def manage_scope(user, organization, request=None):
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return EMPTY_SCOPE
    if getattr(request, "is_view_as", False):
        return EMPTY_SCOPE  # baxış rejimi heç vaxt yazmır
    if is_superadmin_user(user):
        return ORG_WIDE_SCOPE
    return get_permission_scope(user, organization, PERM_MANAGE, request=request)


def can_manage(user, organization, request=None) -> bool:
    return manage_scope(user, organization, request=request).has_structure_access


def unit_rows(organization, unit_ids) -> dict:
    """``{id: (name, path, unit_type)}`` — yalnız bu təşkilatın aktiv bölmələri."""
    if not unit_ids:
        return {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return {
        str(pk): (name, path or "", unit_type)
        for pk, name, path, unit_type in OrgUnit.objects.filter(
            organization=organization, pk__in=list(unit_ids), is_active=True
        ).values_list("pk", "name", "path", "unit_type")
    }


def unit_in_scope(scope, unit_id, path) -> bool:
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    if str(unit_id) in {str(pk) for pk in scope.unit_ids}:
        return True
    return any((path or "").startswith(f"{prefix}/") for prefix in scope.unit_paths)


def validate_units(scope, organization, unit_ids) -> tuple[list, list]:
    """``(etibarlı id-lər, xəta mətnləri)`` — başqa təşkilatın / əhatədən kənar bölmə rədd olunur."""
    from django.utils.translation import pgettext

    wanted = [str(unit) for unit in unit_ids or []]
    rows = unit_rows(organization, wanted)
    errors = []
    if len(rows) != len(set(wanted)):
        errors.append(pgettext("announcements.manage", "Seçilmiş bölmələrdən biri tapılmadı."))
    outside = [rows[pk][0] for pk in rows if not unit_in_scope(scope, pk, rows[pk][1])]
    if outside:
        errors.append(
            pgettext("announcements.manage", "Bu bölmələr sizin əhatənizdən kənardadır: %(names)s")
            % {"names": ", ".join(sorted(outside))}
        )
    if not wanted and not scope.is_org_wide:
        errors.append(
            pgettext(
                "announcements.manage",
                "Bütün təşkilata elan yalnız təşkilat səviyyəli səlahiyyətlə verilir — öz bölmənizi seçin.",
            )
        )
    return [pk for pk in wanted if pk in rows], errors


def manageable_q(scope, user) -> Q:
    """İdarə siyahısının filtri (``Announcement`` üçün)."""
    if scope.is_org_wide:
        return Q()
    if not scope.is_unit_scoped:
        return Q(pk__in=[])
    allowed = {str(pk) for pk in scope.unit_ids}
    q = Q(created_by=user)
    if allowed:
        q |= Q(audience_units__has_any_keys=sorted(allowed))
    return q


def can_edit(scope, user, announcement, organization) -> bool:
    """Bu elanı redaktə/dərc edə bilərmi — bütün hədəf bölmələri əhatədə olmalıdır."""
    if announcement.organization_id != getattr(organization, "pk", None):
        return False
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    units = [str(unit) for unit in announcement.audience_units or []]
    if not units:
        return False
    rows = unit_rows(organization, units)
    return len(rows) == len(units) and all(unit_in_scope(scope, pk, rows[pk][1]) for pk in rows)


def scope_unit_choices(scope, organization) -> list:
    """Auditoriya seçicisinin bölmələri: fakültə → kafedra/şöbə → ixtisas → qrup (əhatə ilə süzülür)."""
    from core.constants import OrgUnitType

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    if not scope.has_structure_access:
        return []
    wanted = [
        OrgUnitType.FACULTY,
        OrgUnitType.CHAIR,
        OrgUnitType.DEPARTMENT,
        OrgUnitType.SPECIALTY,
        OrgUnitType.GROUP,
    ]
    queryset = OrgUnit.objects.filter(organization=organization, unit_type__in=wanted, is_active=True)
    if not scope.is_org_wide:
        queryset = queryset.filter(scope.unit_subtree_q())
    rows = queryset.order_by("path").values_list("pk", "name", "unit_type", "level")[:2000]
    from ..constants import UNIT_TYPE_LABELS

    return [
        {"id": str(pk), "label": name, "type": unit_type, "type_label": UNIT_TYPE_LABELS.get(unit_type, ""), "level": level or 0}
        for pk, name, unit_type, level in rows
    ]


__all__ = [
    "can_edit",
    "can_manage",
    "manage_scope",
    "manageable_q",
    "scope_unit_choices",
    "unit_in_scope",
    "unit_rows",
    "validate_units",
]
