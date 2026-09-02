"""Müraciət testləri üçün minimal fixture qurucuları.

Struktur qəsdən REAL universitet ağacıdır (fakültə → kafedra → ixtisas → qrup):
marşrutlaşdırmanın bütün mənası əcdad axtarışındadır, düz siyahı ilə yoxlansa
test heç nə sübut etməzdi.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.applications.services.catalog import seed_catalog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()


def make_user(username: str, *, first="Ad", last="Soyad"):
    return User.objects.create_user(username, f"{username}@example.test", "pw12345!", first_name=first, last_name=last)


def make_org(slug: str = "app-org"):
    owner = make_user(f"{slug}-owner")
    return Organization.objects.create(
        name=slug.upper(),
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def make_unit(organization, name, unit_type, parent=None):
    return OrgUnit.objects.create(
        organization=organization,
        parent=parent,
        name=name,
        slug=f"{organization.slug}-{name}".lower().replace(" ", "-"),
        unit_type=unit_type,
    )


def make_tree(organization, tag="a"):
    """fakültə → kafedra → ixtisas → qrup zənciri."""
    faculty = make_unit(organization, f"Fakültə {tag}", OrgUnitType.FACULTY)
    chair = make_unit(organization, f"Kafedra {tag}", OrgUnitType.CHAIR, parent=faculty)
    specialty = make_unit(organization, f"İxtisas {tag}", OrgUnitType.SPECIALTY, parent=chair)
    group = make_unit(organization, f"Qrup {tag}", OrgUnitType.GROUP, parent=specialty)
    return {"faculty": faculty, "chair": chair, "specialty": specialty, "group": group}


def make_role(organization, name, *, level=50, scope_type=RoleScopeType.ORGANIZATION, permissions=None):
    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": scope_type,
            "permissions": list(permissions or []),
        },
    )
    Role.objects.filter(pk=role.pk).update(
        is_active=True,
        level=level,
        scope_type=scope_type,
        permissions=list(permissions or []),
    )
    role.refresh_from_db()
    return role


def add_member(organization, user, role_name, *, scope_unit=None, permissions=None, level=50, scope_type=None):
    """Aktiv üzvlük — rol adı marşrutlaşdırmanın açarıdır."""
    resolved_scope = scope_type or (RoleScopeType.UNIT if scope_unit is not None else RoleScopeType.ORGANIZATION)
    role = make_role(organization, role_name, level=level, scope_type=resolved_scope, permissions=permissions)
    membership, _created = Membership.objects.get_or_create(
        organization=organization, user=user, role=role, scope_unit=scope_unit, defaults={"is_active": True}
    )
    Membership.objects.filter(pk=membership.pk).update(is_active=True)
    _clear_cache(user)
    return membership


def _clear_cache(user):
    for attribute in ("_applications_memberships", "_active_org_memberships"):
        if hasattr(user, attribute):
            delattr(user, attribute)


CREATE = ["application.create"]
HANDLE = ["application.create", "application.handle"]
MANAGE = ["application.create", "application.handle", "application.manage"]


def make_world(slug="app-org"):
    """Bir təşkilat + kataloq + bütün rol daşıyıcıları — testlərin ortaq səhnəsi."""
    organization = make_org(slug)
    tree = make_tree(organization, "a")
    other = make_tree(organization, "b")
    units, kinds = seed_catalog(organization)

    student = make_user(f"{slug}-student")
    add_member(organization, student, "student", scope_unit=tree["group"], permissions=CREATE, level=10)

    teacher = make_user(f"{slug}-teacher")
    add_member(organization, teacher, "teacher", scope_unit=tree["chair"], permissions=CREATE, level=50)

    staff = make_user(f"{slug}-staff")
    add_member(organization, staff, "hr", permissions=HANDLE, level=65)

    coordinator = make_user(f"{slug}-coordinator")
    add_member(
        organization, coordinator, "program_coordinator", scope_unit=tree["specialty"], permissions=HANDLE, level=45
    )

    other_coordinator = make_user(f"{slug}-coordinator-b")
    add_member(
        organization,
        other_coordinator,
        "program_coordinator",
        scope_unit=other["specialty"],
        permissions=HANDLE,
        level=45,
    )

    dean = make_user(f"{slug}-dean")
    add_member(organization, dean, "dean", scope_unit=tree["faculty"], permissions=HANDLE, level=80)

    chair_head = make_user(f"{slug}-chair-head")
    add_member(organization, chair_head, "chair_head", scope_unit=tree["chair"], permissions=HANDLE, level=70)

    rim = make_user(f"{slug}-rim")
    add_member(organization, rim, "ikt_rehber", permissions=MANAGE, level=88)

    outsider = make_user(f"{slug}-outsider")
    add_member(organization, outsider, "member", permissions=[], level=20)

    return {
        "organization": organization,
        "tree": tree,
        "other_tree": other,
        "units": units,
        "kinds": kinds,
        "student": student,
        "teacher": teacher,
        "staff": staff,
        "coordinator": coordinator,
        "other_coordinator": other_coordinator,
        "dean": dean,
        "chair_head": chair_head,
        "rim": rim,
        "outsider": outsider,
    }


def kind_of(world, code):
    return world["kinds"][code]


def unit_of(world, code):
    return world["units"][code]
