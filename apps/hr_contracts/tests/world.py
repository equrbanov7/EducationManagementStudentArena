"""«Əmək müqavilələri» testləri üçün kiçik universitet.

Struktur: Fakültə F1 → Kafedra A;  Fakültə F2 → İnzibati şöbə B.
Üzvlər: HR (`hr`, ORGANIZATION), «Fakültə kadr işçisi» (UNIT rolu, `hr.contracts_manage`, F1 əhatəsi),
müəllim t1 (Kafedra A), mühasib-üzv m1 (`member`, Şöbə B), tələbə s1, dekan (F1), qəyyum, rektor (``*``).
İkinci təşkilat — öz müəllimi ilə (tenant izolyasiyası).
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import Client

from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
PW = "HrContractPass123!"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def member(org, username, role_name, *, unit=None, title=""):
    user = User.objects.create_user(
        username, f"{username}@qku.edu.az", PW, first_name="Ad", last_name=username.split("_")[-1].title()
    )
    Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name=role_name),
        scope_unit=unit,
        title=title,
        is_primary=True,
        is_active=True,
    )
    return user


def _unit(org, name, unit_type, parent=None):
    return OrgUnit.objects.create(
        organization=org,
        name=name,
        slug=f"{org.slug}-{name}".lower().replace(" ", "-"),
        unit_type=unit_type,
        parent=parent,
    )


def build_world(slug: str) -> dict:
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", PW)
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        f1 = _unit(org, "Fakulte F1", OrgUnitType.FACULTY)
        chair_a = _unit(org, "Kafedra A", OrgUnitType.CHAIR, parent=f1)
        f2 = _unit(org, "Fakulte F2", OrgUnitType.FACULTY)
        office_b = _unit(org, "Sobe B", OrgUnitType.DEPARTMENT, parent=f2)
        Role.objects.create(
            organization=org,
            name="faculty_hr",
            display_name="Fakültə kadr işçisi",
            level=55,
            scope_type=RoleScopeType.UNIT,
            permissions=["hr.contracts_view", "hr.contracts_manage"],
            is_system=False,
            is_active=True,
        )
        world = {
            "org": org,
            "owner": owner,
            "f1": f1,
            "f2": f2,
            "chair_a": chair_a,
            "office_b": office_b,
            "hr": member(org, f"{slug}_hr", "hr"),
            "unit_hr": member(org, f"{slug}_unithr", "faculty_hr", unit=f1),
            "t1": member(org, f"{slug}_t1", "teacher", unit=chair_a, title="Baş müəllim"),
            "t2": member(org, f"{slug}_t2", "teacher", unit=chair_a),
            "m1": member(org, f"{slug}_m1", "member", unit=office_b, title="Mühasib"),
            "s1": member(org, f"{slug}_s1", "student"),
            "dean": member(org, f"{slug}_dean", "dean", unit=f1),
            "trustee": member(org, f"{slug}_trustee", "trustee"),
            "rector": member(org, f"{slug}_rector", "rector"),
        }
    return world


def client_for(org, user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


class Req:
    """Servis çağırışları üçün minimal request (audit + view-as bayrağı)."""

    def __init__(self, user, org, *, view_as=False):
        self.user = user
        self.organization = org
        self.META = {}
        self.is_view_as = view_as
        self.GET = {}


def actor(world, key, *, view_as=False):
    from apps.hr_contracts.services.access import actor_for

    return actor_for(world[key], world["org"], view_as=view_as)


def days(n: int) -> dt.date:
    from django.utils import timezone

    return timezone.localdate() + dt.timedelta(days=n)


def contract_data(employee, **overrides) -> dict:
    data = {
        "employee": str(employee.pk),
        "number": overrides.pop("number", f"EM-{employee.pk}-{overrides.get('suffix', 'A')}"),
        "contract_type": "fixed_term",
        "position": "Baş müəllim",
        "start_date": days(-300).isoformat(),
        "end_date": days(65).isoformat(),
    }
    overrides.pop("suffix", None)
    data.update({key: ("" if value is None else str(value)) for key, value in overrides.items()})
    return data


def make_contract(world, employee_key="t1", *, by="hr", files=None, **overrides):
    from apps.hr_contracts.services.contracts import save_contract

    with bypass_rls():
        contract, _created = save_contract(
            actor(world, by), contract_data(world[employee_key], **overrides), files or {}, request=None
        )
    return contract
