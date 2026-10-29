"""Sahib 2026-10-29: «Laborantlara bu hissəni aç, hər laborant özünə aid olan kafedranın yükləri görsün və
editləyə də bilsin».

Nəyi qoruyur (DEFOLT rol şablonu ilə — signal təşkilat yaradılanda əkir):

1. Laborant rolunda ``workload.manage`` + ``workload.distribute`` var (şablon + idempotent tətbiq).
2. «Yük bölgüsü» menyusu açılır, kafedra siyahısında YALNIZ öz kafedrası var.
3. Yazı qapısı (``scoping``) öz kafedrasını buraxır, başqa kafedranı rədd edir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.permissions_lab_workload import LAB_WORKLOAD_GRANTS, apply_lab_workload_grants
from apps.workload.services.scoping import can_distribute_chair, can_manage_chair, resolve_actor
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_template_grants_lab_assistant_workload_keys():
    role = next(role for role in UNIVERSITY_ROLES if role["name"] == "lab_assistant")
    for key in LAB_WORKLOAD_GRANTS:
        assert key in role["permissions"]
    before = list(role["permissions"])
    apply_lab_workload_grants(UNIVERSITY_ROLES)
    assert role["permissions"] == before  # idempotent


@pytest.fixture
def world():
    owner = User.objects.create_user("lw_owner", "lw_owner@x.test", "pw")
    laborant = User.objects.create_user("lw_lab", "lw_lab@x.test", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name="LW Univ", slug="lw-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        faculty = OrgUnit.objects.create(organization=org, name="Fakültə", slug="lw-f", unit_type=OrgUnitType.FACULTY)
        chair = OrgUnit.objects.create(
            organization=org, name="Marketinq", slug="lw-c1", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        other_chair = OrgUnit.objects.create(
            organization=org, name="Riyaziyyat", slug="lw-c2", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        Membership.objects.create(
            user=laborant,
            organization=org,
            role=org.roles.get(name="lab_assistant"),
            scope_unit=chair,
            is_primary=True,
            is_active=True,
        )
    profile = laborant.profile
    profile.role = "lab_assistant"
    profile.save(update_fields=["role"])
    return {"org": org, "chair": chair, "other_chair": other_chair, "laborant": laborant}


def test_lab_assistant_manages_only_own_chair(world):
    actor = resolve_actor(world["laborant"], world["org"])
    assert can_manage_chair(actor, world["chair"].pk)
    assert can_distribute_chair(actor, world["chair"].pk)
    assert not can_manage_chair(actor, world["other_chair"].pk)
    assert not can_distribute_chair(actor, world["other_chair"].pk)


def test_lab_assistant_sees_distribution_section_with_own_chair(world):
    client = Client()
    client.force_login(world["laborant"])
    response = client.get(reverse("accounts:profile"), {"section": "workload-distribution"})
    assert response.status_code == 200
    section = response.context["workload_distribution_section"]
    assert section["has_access"] is True
    assert [str(chair["id"]) for chair in section["chairs"]] == [str(world["chair"].pk)]
