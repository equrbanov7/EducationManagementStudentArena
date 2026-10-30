"""Müraciət göndərənin cari, tenant-scoped şəxs/vəzifə/bölmə etiketi.

Bu yalnız təqdimatdır: yeni görünüş/əməl icazəsi yaratmır. Əvvəlki application
visibility qapısından keçmiş sətirlər üçün bir JOIN və bir toplu prefetch işləyir.
"""

from django.apps import apps as django_apps
from django.db.models import Prefetch, Q

from core.staff_position import resolve_position_label, visible_role_label

_MEMBERS = "_application_sender_memberships"
_PARENTS = "scope_unit" + "__parent" * 4


def memberships(organization):
    return (
        django_apps.get_model("organizations.Membership")
        .objects.filter(
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
        )
        .filter(Q(scope_unit__isnull=True) | Q(scope_unit__organization=organization, scope_unit__is_active=True))
        .select_related("role", _PARENTS)
        .order_by("-role__level", "-is_primary", "pk")
    )


def sender_queryset(queryset, organization):
    return queryset.select_related("created_by__profile", "sender_scope_unit").prefetch_related(
        Prefetch("created_by__memberships", queryset=memberships(organization), to_attr=_MEMBERS),
    )


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def _unit_chain(unit, organization_id):
    """Only the already joined, same-tenant parent chain; never trigger per-row queries."""
    result = []
    while unit is not None and unit.organization_id == organization_id:
        result.append(unit)
        if not unit._meta.get_field("parent").is_cached(unit):
            break
        unit = unit.parent
    return result


def sender_person(application):
    user, organization = application.created_by, application.organization
    profile = getattr(user, "profile", None)
    if profile is not None and profile.organization_id not in (None, organization.pk):
        profile = None
    patronymic = str(getattr(profile, "patronymic", "") or "").strip()
    full_name = " ".join(user.get_full_name().split())
    if full_name and patronymic and not full_name.casefold().endswith(" " + patronymic.casefold()):
        full_name += " " + patronymic
    full_name = full_name or user.get_username()
    active = getattr(user, _MEMBERS, None)
    if active is None:
        active = list(memberships(organization).filter(user=user))
    # Guard against accidental reuse of a prefetched user object in a different tenant.
    active = [m for m in active if m.organization_id == organization.pk and m.role.organization_id == organization.pk]
    roles = _unique(visible_role_label(m.role.name, m.role.display_name) for m in active)
    titles = _unique(str(m.title or "").strip() for m in active)
    position = (
        " / ".join(titles)
        or resolve_position_label(
            staff_position=getattr(profile, "staff_position", "") if active else "",
        )
        or " / ".join(roles)
    )
    units, chairs, schools = [], [], []
    for member in active:
        for unit in _unit_chain(member.scope_unit, organization.pk):
            if not unit.is_active:
                continue
            units.append(unit.name)
            if unit.unit_type in ("chair", "department"):
                chairs.append(unit.name)
            if unit.unit_type in ("faculty", "deanery"):
                schools.append(unit.name)
    submitted_unit = application.sender_scope_unit
    submitted_unit_name = (
        submitted_unit.name if submitted_unit is not None and submitted_unit.organization_id == organization.pk else ""
    )
    return {
        "id": str(user.pk),
        "name": full_name,
        "full_name": full_name,
        "username": user.get_username(),
        "patronymic": patronymic,
        "position": position,
        "roles": roles,
        "units": _unique(units) or ([submitted_unit_name] if submitted_unit_name else []),
        "chairs": _unique(chairs),
        "schools": _unique(schools),
    }
